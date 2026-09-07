# 第34章 NL2SQL 工程化

---

第33章已经把用户问题约束成 Linked Schema：指标是 `gmv_ops@2025Q1`，区域是 `EAST`，粒度是 SKU，当前用户只能访问 `sales_ops` View。第34章的任务，是在这组约束下生成和执行 SQL，并让失败可分类、可修复、可审计。

如果把 NL2SQL 简化成“让模型写一段 SQL”，真正危险的问题往往不会以语法错误出现。SQL 可以顺利执行，却使用了错误指标、漏掉租户过滤、扫描全库，或者返回了截断结果而模型仍然给出完整归因。

**NL2SQL 的生产目标不是“尽量一次生成正确 SQL”，而是让任何 SQL 都只能在已链接的语义、权限和资源边界内生成、校验、执行和修复。**

## 34.1 NL2SQL 是一条流水线，不是一轮 Prompt

一次 DataAgent 查询可以拆成四段：

1. **语义编译**：Metric、Dimension、过滤和时间由语义层编译成 Semantic Query/SQL；
2. **SQL 生成/补全**：模型在受限 schema 中补排序、Limit、方言等技术细节；
3. **执行治理**：`sql_executor` 做 AST、只读、Schema、Policy 和成本校验；
4. **结果解释**：Planner 基于真实结果、Metric context、新鲜度和截断状态生成回答。

![图34-1：NL2SQL 协作时序](../../images/part6/ch/ch34-nl2sql-sequence.png)

*图34-1：NL2SQL 协作时序。来源：本书自绘。Alt text：时序图展示 Planner、语义层、Registry、sql_executor、模型网关之间的调用顺序，从 Linked Schema 编译到 SQL 执行、Observation 反馈、结果解释。*

Metric 的公式、默认过滤和 Join 由语义层固定。Planner 可以调整 `ORDER BY`、Limit 或合法过滤，但不能为了“修好 SQL”把 `gmv_ops` 改成 `SUM(order_amount)`。

**SQL 自修复只能修技术实现，不能偷偷改变业务口径。需要改变 Metric、View 或默认过滤时，必须回到语义层重新 Linking。**

## 34.2 从 Linked Schema 到受约束 SQL

输入可以是：

```json
{
  "metrics": [
    {"metric_id": "gmv_ops", "version": "2025Q1", "title": "运营 GMV"}
  ],
  "dimensions": ["region_code", "sku"],
  "filters": [{"field": "region_code", "op": "eq", "value": "EAST"}],
  "time_range": {"start": "2025-06-09", "end": "2025-06-15"},
  "compare_to": {"start": "2025-06-02", "end": "2025-06-08"},
  "view": "sales_ops",
  "tenant_id": "demo-tenant"
}
```

简化 SQL 可能是：

```sql
SELECT
  o.sku_id AS sku,
  SUM(CASE WHEN o.order_week = '2025-W24' THEN o.amount_ops ELSE 0 END) AS gmv_last_week,
  SUM(CASE WHEN o.order_week = '2025-W23' THEN o.amount_ops ELSE 0 END) AS gmv_prior_week
FROM analytics.orders_fact AS o
WHERE o.tenant_id = 'demo-tenant'
  AND o.region_code = 'EAST'
  AND o.order_week IN ('2025-W23', '2025-W24')
  AND o.is_internal = false
GROUP BY o.sku_id
ORDER BY (gmv_last_week - gmv_prior_week) ASC
LIMIT 50;
```

这里 `amount_ops` 和 `is_internal=false` 来自 Metric 定义，区域和时间来自 Frame，`tenant_id` 则由身份/Policy 强制。模型即使生成了类似 SQL，也不能被当成这些约束的事实来源。

大仓库还需要 schema pruning。Prompt 中只放当前 View 和问题相关的表列，不要把数千列 DDL 全部交给模型。剪枝结果也应进 Trace，因为“模型没看到哪张表”同样可能解释查询为何走错路径。

历史 Question-SQL 可以作为示例，但要先校验 Metric 版本、View、方言和权限。**历史成功 SQL 是参考样本，不是永远合法的生产查询。**

## 34.3 生成路线：模型能力强弱不是唯一变量

常见路线可以组合使用：

*表34-1：NL2SQL 生成路线。来源：本书整理。*

| 路线 | 做法 | 更适合 |
|---|---|---|
| 语义编译优先 | Metric/View 先编译，模型只补技术细节 | 核心经营指标 |
| 示例驱动 | 检索相似问题和历史 SQL | 有大量高质量历史样本 |
| 分步拆解 | Linking → 生成 → 校验 → 修复 | schema 复杂、需要解释 |
| 大库剪枝 | 先检索/过滤表列再生成 | 上千列、多主题仓库 |
| 本地 SQL 模型 | 专用模型生成/修复 | 私有化、成本敏感场景 |

选择路线时避免两个极端：把所有问题塞进一个巨大 Prompt，或把简单查数拆成十几轮模型调用。早期通常可以从“语义层编译优先 + 一次模型补全 + 强执行校验”开始，再根据真实失败样本增加复杂度。

方言需要显式传入。Postgres、DuckDB、Trino、Snowflake、BigQuery 的日期、JSON 和标识符规则都不同；生成、AST 校验、EXPLAIN 和执行必须使用同一 dialect 配置。

## 34.4 执行前五道校验

SQL 进入 OLAP 前至少经过：

*表34-2：SQL 执行前校验。来源：本书整理。*

| 层 | 校验内容 | 失败动作 |
|---|---|---|
| 语法/方言 | AST 合法、函数存在 | 可修复则返回 Planner |
| 只读 | 禁止 DDL/DML/导出/危险函数 | 直接拒绝 |
| Schema | 表列属于 Linked Schema/View | 回 Linking 或修字段 |
| 成本 | 分区、扫描量、Join 宽度、结果体积 | 缩小范围/转异步 |
| Policy | tenant、行列权限、敏感字段 | 拒绝或 HITL，不让模型绕过 |

只读检查应基于 parser/AST，而不是 `sql.startswith("SELECT")`。CTE、子查询和函数都可能藏有不允许的行为。

资源保护的一个基础配置可以是：

```yaml
allow_statements: [SELECT]
max_rows: 10000
max_bytes: 5MB
statement_timeout_ms: 30000
require_tenant_predicate: true
deny_tables: [raw_pii, admin]
```

执行账号本身也应是只读账号，最好访问只读副本。安全不能只依赖 Agent 层逻辑。

**自然语言入口降低了查询门槛，也会放大昂贵查询的概率；DataAgent 不应成为绕过数据平台资源治理的快捷入口。**

## 34.5 错误分类与自修复：只有可合法修复的错误才重试

模型适合修复列名、方言函数、别名、格式等技术问题；不适合“修复”权限拒绝、禁表、跨租户和高风险写操作。

```json
{
  "status": "error",
  "code": "TOOL_EXECUTION_ERROR",
  "message": "column 'sku' not found",
  "hint": "linked_columns contains sku_id",
  "sql_hash": "a3f8c2",
  "retry_count": 1,
  "max_sql_retries": 2
}
```

Observation 最好同时给出错误类别、可用列、当前 dialect、失败阶段和 `retryable`。Planner 需要结构化修复信号，用户则只需要业务化说明，不能把内部 schema 和敏感信息原样抛到前端。

可修复示例：
- 列名或别名错误；
- 方言函数不兼容；
- 排序/Limit 语法；
- 类型转换或可解释的空字段。

不可通过模型反复尝试的示例：
- `POLICY_DENIED`；
- 租户条件不满足；
- 访问禁表/PII；
- 估算扫描超限且用户未缩小范围；
- 任何写入意图。

重试需要独立预算。连续两次同类错误仍失败，应结束、澄清或转人工，而不是让 ReAct 一直修改 SQL。

## 34.6 结果不是一段文本：摘要、Artifact、截断和新鲜度都要返回

完整结果集不应直接塞进模型上下文。`sql_executor` 可以返回：

```json
{
  "rows": [
    {"sku": "SKU-A", "gmv_last_week": 1200000, "gmv_prior_week": 2100000},
    {"sku": "SKU-B", "gmv_last_week": 980000, "gmv_prior_week": 1100000}
  ],
  "row_count": 50,
  "total_row_count": 1204,
  "truncated": true,
  "result_ref": "artifact://run-1/sql-result-3",
  "sql_hash": "b7e2a1",
  "metric_context": [
    {"metric_id": "gmv_ops", "version": "2025Q1", "title": "运营 GMV"}
  ],
  "freshness": {"orders_fact": "2025-06-14T06:00:00Z"}
}
```

Planner 必须知道自己看到的是 Top-50、采样还是完整结果。否则“Top 50 中没有异常”很容易被写成“所有 SKU 都没有异常”。

对外回答应包含关键口径和数据时间，SQL 原文可以放在展开区/审计面板。用户追问复杂归因时，完整数据通过 `result_ref` 交给第35章 Python 工具，而不是再把所有明细复制到 Prompt。

空结果也必须分类：业务真为零、权限过滤为空、时间错误、数据未刷新、默认过滤排除了数据，含义完全不同。

**执行成功只证明数据库接受了 SQL，不证明 DataAgent 已完成业务任务。结果解释还必须理解 Metric、截断、新鲜度和证据范围。**

## 34.7 SQL 与业务解释的边界：查到了“什么”，不等于证明“为什么”

Top SKU 查询可以告诉用户哪些 SKU 下滑最多，却不能直接证明原因。用户问“是不是价格导致”“是不是促销结束”，应进入额外数据和 Python/分析链路。

可信回答可以写：

> 华东上周运营 GMV（`gmv_ops@2025Q1`）较前周下降 12.3%。下滑差额最大的三个 SKU 为……。当前查询只能定位贡献项，若要判断价格、促销或品类结构原因，需要继续分析。数据截至 2025-06-14 06:00。

这种回答比模型根据排名直接给因果结论更有价值。**NL2SQL 负责把数据取准，不负责把相关关系自动升级成因果解释。**

多轮追问也应修改 Question Frame 后重新编译。例如“那华北呢”只改 region，“按品类看”增加 Dimension，“去年同期呢”调整时间。不要把上一轮 SQL 文本当成后续任务的唯一上下文。

## 34.8 `sql_executor`：把生成和执行彻底分开

推荐目录边界：

```text
mini-platform/agents/data_agent/
  # Frame、Linking 协调、SQL 生成提示、解释

mini-platform/infra/semantic_layer/
  # Metric/View/compile_query

mini-platform/tools/sql_executor/
├── handler.py
├── validate.py
├── runner.py
└── policy.yaml
```

`sql_executor` 是 Registry Tool。Planner 只能通过 Tool Call 使用它，不拥有数据库连接。

生产日志至少保存：规范化 SQL/hash、参数、用户/租户、Metric/View、执行时间、扫描量、返回行数、截断状态和 result artifact。这样 Trace、成本治理和报告层可以复用同一事实。

缓存也必须包含 tenant、View、Metric version、时间、过滤、权限和 freshness。缓存 key 少一个维度，就可能把性能优化变成权限或口径事故。

## 34.9 发布、评测与降级：正确行为不总是“返回一个 SQL 结果”

NL2SQL 发布应同时回归：

- 正常高频问数；
- 多口径需要澄清；
- 权限拒绝；
- 空结果；
- 高成本查询；
- 列名/方言可修复错误；
- 截断与 Top-N；
- 多轮 Frame diff；
- SQL 正确但业务解释错误的样本。

公开 Text-to-SQL benchmark 用于技术能力下限，企业金标准集必须覆盖真实 Metric、角色和失败路径。灰度时比较旧/新 Frame、Linked Schema、SQL、EXPLAIN、结果和解释，而不只比较最终文本。

能力也可以分层开放：先单指标只读查询，再多维对比，再复杂多表/诊断。某数据域出现高频越权、成本超限或人工退回，应允许退回上一层，而不是继续扩大模型自由度。

失败后的产品动作要明确：歧义 → 澄清；权限不足 → 可用聚合层级/申请入口；资源超限 → 缩小范围/转异步；数据延迟 → 等待或接受限制；部分数据成功 → 展示已有证据和缺失项。

**NL2SQL 的成熟度，不是 SQL 覆盖越来越广，而是更多真实问题能够在明确口径和资源边界内被正确完成，不能完成的问题也有确定的退出路径。**

## 本章小结

NL2SQL 在 DataAgent 中是一条由语义层、Planner、Registry 和只读执行器共同组成的查询链。生成 SQL 之前先确定 Linked Schema，执行前进行 AST、Schema、成本和 Policy 校验，执行后返回带 Metric、freshness、truncated 和 Artifact 的结构化结果。

自修复只处理技术性、可合法修复错误；任何口径变化和权限扩大都要回到更上层重新确认。SQL 能成功运行也不等于业务解释成立，排名和差异只能作为后续分析的证据。

**可信 NL2SQL 的核心不是让模型更自由地写 SQL，而是让 SQL 始终成为一件可检查、可拒绝、可重放的中间产物。**

## 参考文献

Liu, X., et al. (2025). A survey of Text-to-SQL in the era of LLMs. *IEEE TKDE*.

Tang, Z., et al. (2025). *LLM/Agent-as-Data-Analyst: A survey*.

Lei, F., et al. (2024). *Spider 2.0*. ICLR 2025.

Gao, D., et al. (2023). *Text-to-SQL empowered by large language models: A benchmark evaluation*. VLDB.

Pourreza, M., & Rafiei, D. (2023). *DIN-SQL*. NeurIPS.

Talaei, S., et al. (2024). *CHESS*.

Li, H., et al. (2024). *CodeS: Towards building open-source language models for text-to-SQL*. SIGMOD.
