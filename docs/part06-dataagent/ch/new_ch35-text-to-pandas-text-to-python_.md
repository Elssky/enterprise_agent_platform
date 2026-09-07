# 第35章 Text-to-Pandas / Text-to-Python

---

第34章解决结构化取数。用户继续问“品类结构有没有关系”“价格还是销量导致”“排除新品以后还成立吗”，问题就进入二次分析。SQL 可以表达其中一部分，但复杂中间计算、临时列、统计检验和图表前处理往往更适合 Python。

这并不意味着给模型一个自由 Notebook。生产 DataAgent 中，Python 只能读取上游已授权、已裁剪的数据引用，在受限沙箱中执行，并输出可追溯 Artifact。需要重新取数时必须回到 `sql_executor`。

**Text-to-Python 不是给模型一个 Notebook，而是把灵活分析压进一个只能读取受控数据引用、受资源和依赖限制、输出可追溯 Artifact 的沙箱工具。**

## 35.1 SQL 与 Python：权威取数和二次分析分工

SQL 负责 Metric 聚合、Join、过滤和数据权限，Python 负责在已经授权的结果集上继续分析。

*表35-1：SQL 与 Python 的边界。来源：本书整理。*

| 任务 | 首选路径 | 原因 |
|---|---|---|
| 单指标聚合、Top-N | SQL | 口径明确、执行成本可控 |
| 多维过滤与排序 | SQL | 数据库擅长 |
| 品类贡献度 | SQL 取数 + Python | 中间计算和解释更清晰 |
| 量价分解、分布、统计检验 | Python | 多步公式/临时列较多 |
| 临时小文件探查 | Python 沙箱 | 数据未入仓，但必须限大小/权限 |
| 图表前处理 | Python + chart renderer | 生成结构化图表数据 |

“华东下滑”案例中，SQL 先返回 `sku_id`、`category`、两期 GMV 和差额；Python 再计算各品类对下滑的贡献比例。

自然语言入口不能改变物理计算边界。若任务要求数千万行明细进入 pandas，应改成数据库预聚合、异步离线任务或专用分析服务，而不是给沙箱加更多内存。

**Python 负责分析已经授权的数据，不负责重新发现它还能去哪里找更多数据。**

## 35.2 SQL → Python 的证据合同

Python 读取的不是聊天历史，而是上游 Tool Result：

```json
{
  "dataframe_ref": "artifact://run-1/sql-result-3.parquet",
  "content_hash": "sha256:...",
  "row_count": 1542,
  "columns": ["sku_id", "category", "gmv_last_week", "gmv_prior_week", "gmv_delta"],
  "metric_context": [
    {"metric_id": "gmv_ops", "version": "2025Q1"}
  ]
}
```

其中：

- `dataframe_ref`：明确读哪份数据；
- `content_hash`：防止输入在修复/恢复时被替换；
- `metric_context`：说明这些数字按什么口径产生。

这三项是 SQL 与 Python 之间最小证据合同。自修复可以改变代码，不能悄悄换输入；如果分析需要新增列，Planner 回到 SQL 重新生成新的 Artifact，再创建新的分析步骤。

![图35-2：分析 Tool 链时序](../../images/part6/ch/ch35-tool-chain-sequence.png)

*图35-2：分析 Tool 链时序。来源：本书自绘。Alt text：时序图展示 Planner 先用 SQL 取数、再调 Python Tool 做统计建模、最后生成图表产物，箭头表示 SQL 与 Python 工具在一次分析中接力协作。*

**分析链路可信的前提，是每个后续产物都能明确指出“我基于哪一份输入、哪一版 Metric、哪一段代码得到”。**

## 35.3 模型生成代码默认不可信：安全边界必须由沙箱实现

Prompt 里写“不要访问网络”“不要读取文件”不是安全机制。模型生成代码应像处理外部脚本一样默认不可信。

基础策略可以是：

```yaml
allowed_imports: [pandas, numpy, scipy, sklearn, matplotlib]
max_memory_mb: 512
max_cpu_seconds: 30
max_python_retries: 2
network: false
```

生产沙箱至少应满足：

- 无外网和内网横向访问；
- 不暴露数据库连接、Secret 和宿主环境变量；
- 每个 Run 独立临时目录，输入只读；
- CPU、内存、运行时长、磁盘和输出大小有硬限制；
- 依赖白名单、固定版本，禁止运行时 `pip install`；
- 禁止 `subprocess`、socket、任意文件路径、数据库连接；
- PII 在进入沙箱前由上游脱敏/裁剪；
- 运行完成按 TTL 清理临时文件。

Docker/容器是较现实的通用方案；WASM/Pyodide 更轻，但科学计算生态有限；远程 Jupyter Kernel 适合开发，不应默认作为多租户生产执行面。

静态 AST 扫描是第一道门，容器/cgroup 等运行时隔离是第二道门。两者不能互相替代。

**代码是否由企业 Prompt 生成，与代码是否值得信任是两件事。真正的安全来自运行环境，即使生成了危险代码，它也只能失败在边界内。**

## 35.4 代码生成、静态审计、执行与自修复

一次 Python Tool 调用可以拆成：

1. Planner 提供分析目标、列摘要和 `dataframe_ref`；
2. Gateway 生成代码；
3. Tool 做 AST/依赖静态审计；
4. 沙箱加载受控数据并执行；
5. 回收结构化输出、Artifact、资源统计和错误；
6. Runtime 把 Observation 返回 Planner。

![图35-1：Python Tool 沙箱执行流程](../../images/part6/ch/ch35-sandbox-flow.png)

*图35-1：Python Tool 沙箱执行流程。来源：本书自绘。Alt text：流程从生成代码、静态审计、注入只读数据、在受限沙箱执行、回收产物与日志，到超时或越权即终止。*

生成 Prompt 不需要完整 DataFrame，只需要 schema、类型、统计摘要和极少量脱敏样例。完整数据在沙箱里通过引用读取。

允许自修复的错误包括：列名、类型转换、轻微语法和库 API 使用错误。比如 `KeyError: gmv_change`，Observation 可以提供合法列名列表，允许一次修正。

不允许让模型通过重试探索的错误包括：网络访问、非白名单 import、读宿主文件、读取 Secret、进程调用、越权数据和资源策略拒绝。

```json
{
  "code": "PYTHON_COLUMN_NOT_FOUND",
  "retryable": true,
  "available_columns": ["gmv_delta", "category"],
  "attempt": 1,
  "max_attempts": 2
}
```

自修复后仍使用同一 `dataframe_ref` 与 hash。**如果修复需要扩大数据范围，就已经不是代码修复，而是新的数据任务。**

## 35.5 输出必须结构化：不要让报告层从 stdout 里“抠数字”

Python 产物可以包含统计 JSON、DataFrame、图表数据、PNG 或 CSV 摘要，但关键分析结果应有结构化契约。

例如品类贡献度：

```python
import json
import pandas as pd

df = pd.read_parquet(inputs["dataframe_ref"])
by_cat = (
    df.groupby("category", as_index=False)["gmv_delta"]
      .sum()
      .assign(share_of_decline=lambda x: x["gmv_delta"] / x["gmv_delta"].sum())
      .sort_values("gmv_delta")
)

result = {
    "metric": "gmv_ops@2025Q1",
    "categories": by_cat.to_dict(orient="records"),
    "top3_share": float(
        by_cat.nsmallest(3, "gmv_delta")["gmv_delta"].sum()
        / by_cat["gmv_delta"].sum()
    )
}
print(json.dumps(result, ensure_ascii=False))
```

真实 Tool Result 更适合直接返回：

```json
{
  "artifact_ref": "artifact://run-1/category-contrib.json",
  "input_hash": "sha256:...",
  "code_hash": "sha256:...",
  "environment": "py-analysis-v3",
  "metrics": {"top3_share": 0.58},
  "warnings": [],
  "resource_usage": {"cpu_s": 1.8, "peak_mem_mb": 126}
}
```

第36章报告层引用 `top3_share=0.58`，不能让模型凭代码意图重新计算一个比例。

**Python 负责计算事实，LLM 负责解释事实；如果报告中的数字不在结构化 Python/SQL 产物里，就应视为无证据数字。**

## 35.6 数值校验：代码运行成功不等于分析正确

Text-to-Python 的错误很多不是语法错误，而是重复行、分母错、缺失值处理、类型转换、时区、采样和排序截断。

执行后至少可以做一组确定性检查：

- 关键字段/类型符合契约；
- 汇总值与上游 SQL 总量在容差内一致；
- 占比和概率在合法范围；
- 分组行数/时间窗口符合预期；
- 图表数据与分析 Artifact 同源；
- 截断/采样被明确标记；
- 含随机过程时固定 seed 和参数。

高风险分析应保留关键中间结果，而不是只保存最终一句“下降主要来自某品类”。

统计模型、聚类和异常检测还要记录方法、参数、环境和限制。一次沙箱分析可以用于探索，但长期预测/评分模型应进入正式模型治理，而不是一直由临时代码承担。

## 35.7 高频分析应从生成代码沉淀成版本化 Tool/Playbook

Text-to-Python 适合长尾和探索任务，不代表每次都应该重新生成代码。

若“量价分解”“贡献度 waterfall”“留存 cohort”“异常检测”每周重复出现，更合适的演进是：

```text
一次性沙箱代码
→ 人工复核
→ 固化计算函数/模板
→ 定义 input/output schema
→ 单元测试 + Eval
→ 注册为 versioned Tool / Playbook
```

模型只负责选择模板和参数，稳定算法由平台实现。这样可解释性、性能和测试都会提高。

反过来，高频 Tool 也应允许退役。上游 Metric 变化、业务规则失效、失败率上升或长期无人使用，都需要重新验证或下线。

**一个成熟的 DataAgent 不会让生成代码越来越多；它会把高价值、反复出现的临时代码逐渐沉淀成可治理能力。**

## 35.8 Artifact 生命周期、权限和回放

Python Artifact 的可信范围只覆盖当次输入、Metric、代码和环境。它不是长期事实表。

关键 provenance 至少包含：

```text
run_id
input dataframe_ref + hash
metric_context
code_hash
python/environment version
library versions
random seed (if any)
resource limit + actual usage
outputs / artifact hashes
created_at
```

报告发布后，如果上游数据回补或代码发现错误，应能定位所有引用旧 Artifact 的报告并生成新版本；旧产物可以冻结/撤回，但审计证据不应静默覆盖。

查看历史 Artifact 仍要按**当前用户权限**重新授权。历史执行者当时有权读取明细，不代表所有复盘人员今天都能打开底层 Parquet。

中间文件也需要 TTL。交互式临时结果可以短期清理，正式报告引用的产物跟随报告生命周期，高风险审计只保留必要证据。对象存储不是“所有 notebook 文件永久保存”的垃圾场。

## 35.9 `python_sandbox` 与生产验收

推荐作为 Registry Tool：

```text
mini-platform/tools/python_sandbox/
├── handler.py
├── runner/docker_runner.py
├── static_scan.py
└── policy.yaml
```

Planner 传入代码和数据引用，Tool 返回结构化结果、Artifact、资源统计和错误。业务前端只显示“正在做品类贡献度分析”，技术细节放在 Evidence/Trace 中。

上线前至少测试：

- 正确贡献度/分组/统计结果；
- 缺列、空数据、单位变化；
- SQL 总量与 Python 汇总不一致；
- 非白名单 import、网络、文件、进程访问；
- CPU/内存/输出超限；
- 修复时输入 hash 不变化；
- 多输入 Artifact 的来源/权限；
- 失败产物不会进入报告；
- 用户权限变化后历史 Artifact 不能越权查看。

运营上观察重试率、超时率、内存失败率、Artifact 体积和“SQL/Python 汇总不一致率”。某类任务持续失败时，优先考虑预聚合或固化 Tool，而不是不断给沙箱更多自由度。

## 本章小结

SQL 是 DataAgent 的权威取数层，Python 是已授权结果集上的受控分析层。`dataframe_ref`、`content_hash` 和 `metric_context` 把两者连成证据链；模型生成代码经过静态审计和隔离环境执行，不能访问网络、数据库和宿主 Secret。

代码运行成功仍需数值校验；输出应结构化为可追溯 Artifact，报告只引用这些事实。高频稳定分析则应从临时代码升级为版本化 Tool/Playbook。

**Text-to-Python 的成熟度不看模型能写多复杂的 pandas，而看代码即使出错或被恶意诱导，也不会越过数据边界，并且每个最终数字都能复现到确定输入、代码和环境。**

## 参考文献

Tang, Z., et al. (2025). *LLM/Agent-as-Data-Analyst: A survey*.

OpenAI. (2023). *Introducing ChatGPT Code Interpreter*.

PandasAI. (2024). *PandasAI documentation*.

WebAssembly Community. (2024). *WebAssembly System Interface (WASI)*.

Jupyter Development Team. (2024). *Jupyter Kernel Gateway*.

Li, J., et al. (2023). *Chain-of-code: Reasoning with language model-generated programs*.
