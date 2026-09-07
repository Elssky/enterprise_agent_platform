# 第12章 湖仓引擎与 OLAP

---

湖仓把数据保存成可治理表，并不意味着查询链路已经可靠。一个经营分析 Agent 生成跨三年明细的 Join，若直接进入交互式资源池，就可能把财务看板和运营查询一起拖慢。SQL 语法正确，系统仍然可能失败，因为**执行路径、权限、扫描预算和资源隔离没有被控制**。

OLAP 层的职责，是把自然语言生成的 SQL 变成受控执行：按工作负载选择引擎，限制扫描和返回规模，应用权限与脱敏，管理超时和队列，并把结构化失败反馈给 Planner。

**DataAgent 可以提出查询意图，但不能拥有绕过平台控制直接访问任意数据库的执行权。**

## 12.1 从湖仓到数据服务：先按工作负载分类

OLAP（Online Analytical Processing）面向大范围扫描、过滤、聚合、Join 和窗口函数；OLTP 则面向短事务、点查和高并发写入。Agent 平台如果直接把复杂分析压到交易库，会影响生产；如果把所有分析都塞进同一个 OLAP 引擎，又会在延迟、成本和治理上失衡。

![图12-1：OLAP 引擎把湖仓数据变成可消费的数据服务](../../images/part3/ch/ch12-01.png)

*图12-1：OLAP 引擎把湖仓数据变成可消费的数据服务。来源：本书自绘。Alt text：底层湖仓表经 OLAP 引擎查询后，向上提供给看板、API、DataAgent 等消费方，引擎位于"存储"与"消费"之间作为查询服务层。*

引擎选型的第一步不是列产品，而是识别负载。

*表12-1：即席查询、报表、明细检索等分析负载的延迟目标与适配引擎。来源：本书整理。*

| 负载 | 典型问题 | 延迟目标 | 更自然的引擎方向 |
|---|---|---:|---|
| 即席查询 | “这个异常门店还能关联哪些供应商？” | 秒到分钟 | Trino、Databricks、Snowflake |
| 仪表盘 | “今日门店销售额按城市刷新” | 亚秒到数秒 | StarRocks、Doris、ClickHouse、Snowflake |
| 指标查询 | “同店同比、复购率、支付成功率” | 稳定秒级 | 物化视图、指标层、实时 OLAP |
| 联邦查询 | “湖仓订单 join MySQL 促销配置” | 秒到分钟 | Trino、Databricks federation |
| 本地探索 | “抽样 Parquet 验证口径” | 单机交互式 | DuckDB |
| 事件分析 | “最近 5 分钟点击流异常” | 秒级 | ClickHouse、StarRocks、Doris |

![图12-2：企业分析负载决定引擎候选项](../../images/part3/ch/ch12-02.png)

*图12-2：企业分析负载决定引擎候选项。来源：本书自绘。Alt text：左侧列出即席查询、固定报表、明细点查、实时大屏等负载，箭头分别指向更合适的引擎类型，说明先看负载特征再定引擎。*

统一平台不等于单一引擎。更合理的目标是**统一 Catalog、权限、审计和成本控制，允许执行层按负载分化**。

## 12.2 OLAP 为什么快：执行机制与数据布局共同决定成本

现代 OLAP 常依赖列式存储、编码压缩、向量化执行、MPP、成本优化器、缓存和物化视图。它们共同解决一个问题：在可接受成本下扫描大量数据并快速得到聚合结果。

![图12-3：现代 OLAP 查询执行链路](../../images/part3/ch/ch12-03.png)

*图12-3：现代 OLAP 查询执行链路。来源：本书自绘。Alt text：横向链路依次为 SQL 解析、逻辑计划、优化器、分布式执行、结果返回，各阶段标注关键动作，体现一条查询从文本到结果的处理过程。*

性能问题不能只归因于引擎。没有统计信息时，优化器可能选择错误 Join 顺序；分区和排序键不匹配查询条件时，再强的向量化也会退化为大扫描；高频查询如果没有预聚合和物化视图，会重复消耗计算资源。

**性能工程的第一原则不是扩容，而是识别哪些查询应预计算、哪些可以缓存、哪些只能受控探索。**

![图12-6：性能工程把负载分流到预计算、缓存和探索路径](../../images/part3/ch/ch12-06.png)

*图12-6：性能工程把负载分流到预计算、缓存和探索路径。来源：本书自绘。Alt text：查询按特征分流，高频固定查询走物化视图/Rollup 预计算，重复查询走缓存，低频探索走联邦/直查，三条路径分别标注收益。*

*表12-4：单引擎统一与多引擎路由两种架构的取舍。来源：本书整理。*

| 方案 | 优势 | 代价 | 适用场景 | mini-platform 选择 |
|---|---|---|---|---|
| 单引擎统一 | 治理简单、运维集中 | 特定负载性能或成本不优 | 组织早期、负载单一 | 可作为初始策略 |
| 多引擎协同 | 按负载选择成本和性能最优解 | 路由、权限、审计和一致性复杂 | 多团队、多负载、既有系统复杂 | 默认建模方式 |

*表12-5：物化视图、联邦查询等查询加速手段的优势与代价。来源：本书整理。*

| 方案 | 优势 | 代价 | 适用场景 | mini-platform 选择 |
|---|---|---|---|---|
| 联邦查询 | 快速跨源探索，不必先搬数 | 跨源 Join 成本和稳定性难预测 | 临时分析、数据发现 | `federated_query` 路由到 Trino |
| 预建数据集 | 延迟稳定、成本可控、权限清晰 | 需要建模、调度和维护 | 高频报表、DataAgent 常用指标 | 生产路径优先 |

当某个联邦查询变成高频路径时，应沉淀为预建数据集、物化视图或指标层，而不是长期依赖跨源 Join。

## 12.3 多引擎生态：产品边界比排行榜更重要

不同引擎解决的问题并不相同。

*表12-2：平台型湖仓、MPP、实时 OLAP 等引擎类型的代表产品与适用场景。来源：本书整理。*

| 类型 | 代表产品 | 为什么用 | 不适合什么场景 | 替代方案 |
|---|---|---|---|---|
| 平台型湖仓 | Databricks | 数据工程、SQL、机器学习和治理一体化 | 单一低延迟看板时成本较高 | Snowflake、Doris/StarRocks + Spark |
| 云原生数仓 | Snowflake | SQL 数仓、弹性 warehouse、低运维 | 极低延迟事件分析或强本地化 | Databricks、ClickHouse、Doris |
| 实时 OLAP | Doris、StarRocks | 高并发报表、物化视图、MySQL 生态 | 任意跨源探索和重型工程 | Trino、Databricks、Snowflake |
| 事件分析 | ClickHouse | 日志、事件、时序和宽表聚合 | 频繁更新的强事务表 | StarRocks、Doris |
| 联邦查询 | Trino | 多源连接、开放湖仓入口 | 高频固定报表和高成本跨源 Join | 预建数据集、物化视图 |
| 嵌入式分析 | DuckDB | 本地文件、Notebook、轻量 ETL | 多租户、高并发、集群治理 | Trino、Spark |

![图12-5：七类湖仓与 OLAP 引擎的系统边界不同](../../images/part3/ch/ch12-05.png)

*图12-5：七类湖仓与 OLAP 引擎的系统边界不同。来源：本书自绘。Alt text：七种引擎类型并排，各自标出存储耦合度、延迟特征、并发能力和适用负载，对比它们的系统边界差异。*

Databricks/Snowflake 偏平台或托管数仓；Doris/StarRocks/ClickHouse 偏低延迟服务；Trino 偏开放连接和联邦查询；DuckDB 偏本地探索。**选型应围绕真实 SQL、数据分布、并发、权限、成本和运维能力，而不是标准 Benchmark 排名。**

多引擎协同时，要额外治理 SQL 方言、时区、JSON 函数、近似聚合、权限和资源组差异。同一个查询在两个引擎“都能运行”，不代表业务语义完全一致。

## 12.4 受控查询：先过路由、策略和 Catalog，再进入引擎

一次生产查询应先经过统一控制入口：DataAgent 提交意图，路由器选择引擎，策略层检查权限和预算，Catalog 解析表与快照，最后由执行适配器提交。

![图12-4：受控湖仓查询先过路由、策略和 Catalog](../../images/part3/ch/ch12-04.png)

*图12-4：受控湖仓查询先过路由、策略和 Catalog。来源：本书自绘。Alt text：查询进入后依次经过查询路由器、策略引擎（权限/限额）、Catalog（元数据/行列权限），三道关卡通过后才提交引擎执行。*

*表12-3：查询路由器、策略引擎等组件的职责、输入输出与失败模式。来源：本书整理。*

| 组件 | 职责 | 输入 | 输出 | 失败模式 |
|---|---|---|---|---|
| 查询路由器 | 按工作负载、数据位置、延迟和预算选引擎 | 查询意图、SQL、用户、标签 | 引擎和提交请求 | 规则过期、误路由 |
| Catalog 适配器 | 映射平台资产到各引擎 | 元数据、权限、快照 | 数据源定义 | 元数据漂移、凭证失效 |
| 策略控制器 | 权限、行列级策略、预算和并发限制 | 用户、角色、分级、预算 | 允许、拒绝或降级 | 权限漏放、预算失控 |
| 执行适配器 | 适配不同引擎协议 | 查询、连接、超时 | 状态、结果句柄 | 连接池耗尽、引擎不可用 |
| 可观测采集器 | 记录耗时、扫描量、费用、错误和血缘 | 查询生命周期事件 | Trace、Metrics、审计 | 日志缺失、成本归因失败 |

```text
POST /api/lakehouse/query
Request:
{
  "principal": "user:finance_analyst_01",
  "workload": "realtime_bi",
  "sql": "select city, sum(amount) from mart.sales group by city",
  "latency_budget_ms": 3000,
  "cost_budget": "low",
  "result_mode": "preview"
}

Response:
{
  "query_id": "q_20260611_001",
  "engine": "StarRocks",
  "state": "submitted",
  "result_ref": "lakehouse-results/q_20260611_001"
}
```

错误码需要区分 `POLICY_DENIED`、`ENGINE_UNAVAILABLE`、`QUERY_TIMEOUT` 和 `COST_BUDGET_EXCEEDED`。只有这样 Planner 才知道该停止、缩小范围、切换路径还是重试。

## 12.5 Agent 查询安全：只读只是第一道防线

一个合法 `SELECT` 也可能扫描三年明细、执行巨型跨源 Join、返回敏感客户清单或占满交互队列。因此查询安全至少同时包含：只读校验、危险语句拦截、扫描预算、超时、返回行数、脱敏和审计。

![图12-7：Agent 查询安全边界在引擎提交前生效](../../images/part3/ch/ch12-07.png)

*图12-7：Agent 查询安全边界在引擎提交前生效。来源：本书自绘。Alt text：在 SQL 提交到引擎之前设置只读校验、超时、行数限额、结果脱敏四道关卡，箭头表示任一不通过即拦截，体现安全前置。*

查询执行还需要明确状态机，以支持取消、降级和可解释失败。

*表12-6：Agent 查询从提交到完成各状态的进入条件与失败处理。来源：本书整理。*

| 状态 | 进入条件 | 下一步 | 失败处理 |
|---|---|---|---|
| Submitted | 用户或 Agent 提交请求 | Planned 或 Rejected | 权限和预算不通过则拒绝 |
| Planned | 路由和策略通过 | Running 或 Failed | 引擎连接失败返回结构化错误 |
| Running | 引擎接受查询 | Succeeded、TimedOut、Cancelled、Failed | 超时取消，避免无限重试 |
| Succeeded | 结果完成 | 审计并返回 result_ref | 大结果分页或落对象存储 |
| TimedOut | 超过预算 | Retried 或 Failed | 改写、加过滤或走物化视图 |
| Cancelled | 用户或策略取消 | 终止 | 释放资源并记录原因 |

![图12-8：湖仓查询状态机支撑超时、取消和可解释失败](../../images/part3/ch/ch12-08.png)

*图12-8：湖仓查询状态机支撑超时、取消和可解释失败。来源：本书自绘。Alt text：状态机含 Submitted、Planned、Running、Succeeded、Failed、Cancelled 等节点，标出超时和取消的转移边，说明每次失败都有明确状态可解释。*

**失败不能统一处理成“重试”。权限拒绝应停止，扫描超限应缩小范围，引擎不可用才考虑备用路径。**

## 12.6 mini-platform：把负载路由与预算显式化

mini-platform 不直接连接真实引擎，而是先定义工作负载到候选引擎的规则。

- 核心实现：`mini-platform/infra/lakehouse/engine_selector.py`
- 测试：`mini-platform/tests/test_lakehouse_engine_selector.py`
- 实战项目：`mini-platform/projects/12-lakehouse-engine/run.py`

![图12-9：mini-platform 用工作负载标签生成引擎路由决策](../../images/part3/ch/ch12-09.png)

*图12-9：mini-platform 用工作负载标签生成引擎路由决策。来源：本书自绘。Alt text：查询带上工作负载标签（如 adhoc、report、realtime）进入路由器，路由器据标签和数据位置输出目标引擎，体现标签驱动路由。*

```python
class Workload(str, Enum):
    PLATFORM = "platform"
    CLOUD_WAREHOUSE = "cloud_warehouse"
    REALTIME_BI = "realtime_bi"
    FEDERATED_QUERY = "federated_query"
    EVENT_ANALYTICS = "event_analytics"
    LOCAL_ANALYTICS = "local_analytics"
```

```python
_RULES: dict[Workload, EngineChoice] = {
    Workload.REALTIME_BI: EngineChoice(
        primary="StarRocks",
        alternatives=("Apache Doris", "ClickHouse"),
        reason="高并发看板、低延迟聚合、物化视图和 MySQL 协议生态。",
        latency_budget_ms=3000,
        max_scan_gb=200,
    ),
    Workload.FEDERATED_QUERY: EngineChoice(
        primary="Trino",
        alternatives=("Apache Doris", "Databricks Lakehouse Federation"),
        reason="以连接器访问多源数据，适合作为开放湖仓 SQL 入口。",
        latency_budget_ms=30000,
        max_scan_gb=1024,
    ),
}
```

`route_query` 还要检查调用方延迟预算是否可行。目标不是让规则永远选对，而是让“为什么选择这个执行路径”成为可解释、可版本化的控制面。

生产上线时，查询接口至少要记录用户、SQL 摘要、引擎、数据集、快照、扫描量、耗时、错误码和结果去向。缓存也必须绑定语义层版本、数据快照、租户与权限上下文；否则命中越快，返回旧口径的风险越大。

OLAP 策略、物化视图或引擎迁移时，应回放一组高频业务问题，比较最终业务答案，而不是只比较 SQL 是否成功。函数、时区、空值和近似聚合差异都可能造成“执行成功但答案变化”。

## 本章小结

湖仓表格式解决**数据资产如何一致地被读取**，OLAP 层解决**查询如何以合适的延迟、成本和权限被执行**。两者不能互相替代。

多引擎协同的重点不是引擎数量，而是统一 Catalog、策略、状态、审计和证据。DataAgent 生成 SQL 后，必须经过路由、权限、预算、扫描量、超时和结果控制。**模型越会生成查询，执行层越需要把不确定性压回到可管理的资源与安全边界。**

## 参考文献

DuckDB. (n.d.). [Documentation](https://duckdb.org/docs/).

Trino. (n.d.). [Documentation](https://trino.io/docs/current/).

ClickHouse. (n.d.). [Documentation](https://clickhouse.com/docs/).

Apache Doris. (n.d.). [Documentation](https://doris.apache.org/docs/).
