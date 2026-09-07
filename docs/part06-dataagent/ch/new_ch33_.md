# 第33章 语义层工程

---

用户问“上周华东销售为什么下滑”，数据库可以返回很多合法数字，但业务只接受当前组织认可的那一个。这里的难点不是 SQL 语法，而是“销售”“华东”“上周”分别代表什么：运营 GMV 还是财务收入，销售区域还是履约区域，自然周还是财务周。

语义层位于物理数据与 DataAgent 之间，把 Metric、Dimension、Join、默认过滤、View、权限、版本和业务词汇变成可执行模型。模型负责理解自然语言和选择候选，最终口径则来自语义层。

**语义层的任务不是给字段加中文注释，而是把业务口径、可见范围和数据可信状态变成模型不能随意改写的执行约束。**

## 33.1 为什么 DataAgent 必须先经过语义层

没有语义层时，模型需要同时猜三件事：指标怎么算、表怎么 Join、用户能看到什么。最危险的结果往往不是 SQL 报错，而是 SQL 正常执行、数字却不被业务承认。

*表33-1：无语义层时的风险与语义层约束。来源：本书整理。*

| 问题 | 无语义层 | 语义层提供 |
|---|---|---|
| 指标口径 | 模型根据列名猜 GMV | Metric 定义、默认过滤、版本 |
| Join | 物理表自由组合 | 建模关系、合法 Join 路径 |
| 权限 | 全库 schema 进入上下文 | 角色/租户 View 与行列权限 |
| 时间语义 | 模型临时解释“上周” | 业务时间维、财务周期 |
| 可信度 | 不知道数据是否及时/可靠 | 新鲜度、质量、血缘 |

中文字段注释只能帮助理解列名，无法表达“含不含退货”“何时生效”“谁可以看”“数据更新到几点”。Memory 也不能承担 Metric 数学定义：用户偏好可以记住，正式指标必须跟随组织版本。

**DataAgent 可以拥有自己的交互策略，但不应拥有一套与 BI、报表和数据平台不同的指标数学定义。**

## 33.2 Metric、Dimension、View 与 Glossary

DataAgent 最常消费四类语义对象。

*表33-2：语义层核心对象。来源：本书整理。*

| 对象 | 负责什么 | DataAgent 如何使用 |
|---|---|---|
| Metric | 公式、过滤、聚合、版本、owner | 绑定问题中的指标 |
| Dimension | 时间、区域、SKU、渠道等切片 | 过滤、分组和下钻 |
| View | 某角色/场景允许看到的对象集合 | 裁剪 Planner 可见 schema |
| Glossary | 业务词、别名、缩写与候选 Metric | 把口语映射到语义对象 |

Metric 至少需要稳定 ID、业务标题、精确定义、版本、生效期、owner 和默认过滤。例如用户最终看到“运营 GMV `gmv_ops@2025Q1`”，比只写“GMV”更容易复核。

View 应按角色和场景设计，而不是照搬数据库 schema：

```yaml
view: sales_ops
metrics:
  - gmv_ops
  - gmv_tax_excluded
  - order_count
dimensions:
  - region_code
  - category
  - sku
  - week
```

运营负责人和财务 Controller 可以拥有不同 View；门店经理可能只能访问自己门店。Planner 不需要知道所有底层表，只需要知道当前任务允许使用哪些业务对象。

Glossary 则持续吸收“销售额”“流水”“GMV”“营收”等真实语言，并记录适用范围和歧义关系。它不能只做同义词替换；同一个词在不同角色下可能合法指向不同 Metric。

## 33.3 Schema Linking：先过滤，再召回，再消歧

Schema Linking 将 Question Frame 中的口语槽位绑定到当前可用的 Metric、Dimension 和 View。

![图33-1：Schema Linking 模式链接流程](../../images/part6/ch/ch33-schema-linking-flow.png)

*图33-1：Schema Linking 模式链接流程。来源：本书自绘。Alt text：流程从用户问题出发，经术语识别、候选字段召回、按信号打分、消歧确认，输出绑定到具体 Metric 与字段的 Linked Schema。*

推荐顺序是：

1. **Glossary** 生成业务候选；
2. **View/权限** 先移除当前用户不可见对象；
3. 在允许范围内用向量检索、元数据和历史成功样本召回；
4. 规则/模型 rerank；
5. 仍然歧义则澄清。

*表33-3：Linking 信号优先级。来源：本书整理。*

| 信号 | 优先级 | 说明 |
|---|---|---|
| Glossary | 高 | 正式业务术语映射 |
| View / Policy | 高 | 先确定合法候选空间 |
| 向量检索 | 中 | 在合法空间内召回相似对象 |
| 历史成功 Run | 中 | 只能作为候选，必须重新检查版本 |
| 模型自由推断 | 低 | 需被 schema 和策略校验 |

**权限过滤应该发生在模型看到 schema 之前。执行前再拦截一次是必要的二次防线，但不能先把敏感字段完整暴露给 Planner。**

“华东销售”最终可以得到：

```json
{
  "metrics": [
    {"metric_id": "gmv_ops", "version": "2025Q1", "title": "运营 GMV"}
  ],
  "dimensions": ["region_code", "sku"],
  "filters": [
    {"field": "region_code", "op": "eq", "value": "EAST"}
  ],
  "time_range": {"grain": "week", "range": "last_week"},
  "view": "sales_ops"
}
```

候选、过滤原因、最终选择和版本都应进入 Trace。否则一次“SQL 正确、数字错误”的争议无法判断是 Glossary、View、Linker 还是模型选择出了问题。

## 33.4 多口径与版本：不能为了体验简单把冲突藏起来

企业存在多个合法口径很正常：运营 GMV、财务不含税收入、集团口径、区域口径，以及不同生效期版本。

![图33-2：Glossary 多 Metric 消歧流程](../../images/part6/ch/ch33-glossary-metric-flow.png)

*图33-2：Glossary 多 Metric 消歧流程。来源：本书自绘。Alt text：当一个术语匹配多个 Metric 时，流程按视图作用域、用户角色、历史偏好逐步缩小候选，必要时向用户追问。*

*表33-4：多 Metric 冲突处理。来源：本书整理。*

| 情况 | 处理 |
|---|---|
| View 过滤后唯一 | 自动绑定，并展示 title/version |
| 同一 View 仍多个 | 使用明确组织默认或追问 |
| 跨时间版本 | 按问题时间匹配有效版本 |
| 无安全匹配 | 拒答/转人工，不临时猜字段 |

组织默认必须来自策略，而不是模型偏好。例如运营负责人默认使用 `gmv_ops`，财务角色默认使用财务口径；这个差异要在 Trace 中可解释。

指标升级也不能覆盖旧版本。历史报告应继续指向当时的 Metric，未完成 Run 也要 pin 原版本。若跨版本比较会改变口径，应在回答和报告中明确提示。

**多口径不是问题；“后台多口径并存，前台假装只有一个销售额”才是问题。**

## 33.5 可信上下文：权限、血缘、质量与新鲜度会改变回答强度

Metric 解决“怎么算”，可信上下文还要回答：谁能看、来自哪里、质量怎样、更新到什么时候。

*表33-5：可信上下文。来源：本书整理。*

| 维度 | 来源 | 对 DataAgent 的影响 |
|---|---|---|
| 权限 | IAM、View、Policy | 决定候选和执行范围 |
| 血缘 | OpenLineage / 元数据 | 说明来源、模型版本和依赖 |
| 质量 | dbt tests / 质量服务 | 异常时降级或阻断结论 |
| 新鲜度 | 分区/同步任务 | 标注数据截止时间或等待刷新 |

例如：订单数据截至 06:00、退货数据截至 04:00，DataAgent 不能只展示较新的时间；跨源分析要以最弱环节解释可用性。

质量信号也不能只留在后台。SKU 空值率偏高时可以继续做品类级分析，但弱化 SKU 排名；事实表延迟超过 SLA 时，不应生成“最新经营结论”；正式报告遇到严重质量问题应进入人工复核或等待刷新。

普通用户不需要看到完整血缘图，但至少应能看到：指标标题/版本、数据时间和重要质量限制；完整来源则放在 Evidence/Trace 中。

**DataAgent 的可信度不是“总能给出一个数”，而是在数据证据变弱时，回答强度和自动化程度也会随之降低。**

## 33.6 接口设计：DataAgent 消费语义层，而不是复制语义层

一个稳定的消费接口可以围绕三类能力：

```text
resolve_metric(question, view, identity)
compile_query(linked_schema)
trusted_context(linked_schema)
```

- `resolve_metric()`：返回候选 Metric、版本和消歧信息；
- `compile_query()`：根据 Metric、Dimension、过滤和时间生成结构化查询/Semantic SQL；
- `trusted_context()`：返回权限、血缘、质量和新鲜度。

目录可以保持清晰依赖：

```text
mini-platform/infra/semantic_layer/
├── client.py
└── models/

mini-platform/agents/data_agent/
└── linker.py
```

DataAgent Planner 可以选择业务对象，却不允许改写 Metric 聚合逻辑。底层实现可以从简单 YAML 起步，未来换成 Cube、MetricFlow 或其它引擎，只要消费接口稳定。

生产查询应尽量经 View/语义层，而不是在语义层超时后“降级”为模型直连物理表。**可信路径不可用时，正确降级通常是等待、拒答或转人工，而不是绕过可信路径。**

## 33.7 变更、回归与运营：语义层是一项发布资产

新增 Metric、改公式、调整默认过滤、废弃别名、修改组织映射或收紧 View，都可能改变 DataAgent 的答案，因此应按软件变更管理。

发布至少包括：

1. 静态校验：字段、聚合、权限、时间粒度；
2. 样本回放：高频问题、口径争议、事故问题；
3. 影响分析：受影响 Agent、报告、Eval、用户；
4. 灰度：比较旧/新 Linking、SQL 和解释；
5. 用户沟通：关键 Metric 口径变化明确生效时间；
6. 历史保留：旧 Run 继续按旧版本解释。

样本池建议分为基础覆盖、业务争议、事故样本和发布样本。每条样本不仅保存最终答案，还保存候选 Metric、View、Linked Schema、SQL 和 EvidenceRef，这样失败才能定位到具体责任层。

用户投诉也应分类：术语未覆盖 → Glossary；指标定义冲突 → Metric/owner；权限候选缺失 → View/Policy；数据延迟 → quality/freshness；模型从合法候选中选错 → Linker/Planner。

**语义层运营的成熟度，不在 YAML 写了多少指标，而在口径变化、业务争议和历史报告都能被版本化解释。**

## 本章小结

语义层是 DataAgent 从业务语言进入可信数据的边界。Metric 定义口径，Dimension 定义切片，View 定义可见范围，Glossary 处理真实业务语言；Schema Linking 在这些受治理对象中完成候选过滤和消歧。

多口径可以并存，但选择过程和版本必须显性；权限应在模型看 schema 之前就参与裁剪；质量、新鲜度和血缘不仅用于后台治理，也会决定 DataAgent 是否回答以及如何表达。

**当用户质疑“这个数字到底怎么算、为什么我能看到、数据更新到什么时候”时，如果系统能直接从本次 Run 中回答，语义层才真正成为 DataAgent 的可信地基。**

## 参考文献

Cube. (2025). *Introduction: Cube semantic layer*.

dbt Labs. (2024). *About MetricFlow*.

Liu, X., et al. (2025). A survey of Text-to-SQL in the era of LLMs. *IEEE TKDE*, 37(10), 5735-5754.

Lei, F., et al. (2024). *Spider 2.0*. ICLR 2025.

Talaei, S., et al. (2024). *CHESS: Contextual harnessing for efficient SQL synthesis*.

OpenLineage. (2024). *OpenLineage documentation*.
