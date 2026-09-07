# 第10章 数据采集与集成

---

数据采集层决定 Agent **能看到哪些事实、看到多新的事实，以及这些事实能否被追溯和重放**。运营负责人问“哪些门店今天可能缺货”，如果库存只在昨夜批处理后更新，模型即使推理正确，也会基于过期事实给出错误建议。这类问题不能靠换模型解决。

企业数据通常来自 OMS、WMS、ERP、CRM、SaaS、文件和事件流，不同来源的主键、删除语义、更新时间和权限边界并不一致。采集层的责任不是“把数据搬进来”，而是把源系统变化转换成平台可解释的数据事实：来源、位点、版本、新鲜度、质量和权限都要被记录。

**对 Agent 平台来说，采集成功的标准不是任务跑完，而是下游能够判断这批数据是否新鲜、完整、可恢复、可用于当前回答。**

## 10.1 数据采集层的边界：先定义事实，再选择工具

生产系统面向交易处理，Agent 平台面向分析、解释和自动化动作。让 Agent 直接查询业务库，会同时引入性能、Schema、权限和审计风险。更稳妥的边界是：源系统只向采集层暴露受控接口，湖仓、OLAP、语义层和 DataAgent 只消费带契约的数据副本。

![图10-1：数据采集层把源系统和 Agent 平台隔离开](../../images/part3/ch/ch10-01.png)

*图10-1：数据采集层把源系统和 Agent 平台隔离开。来源：本书自绘。Alt text：左侧是 ERP、CRM、文件、API 等异构源系统，中间是统一采集层，右侧是 Agent 平台数据底座，采集层作为缓冲使源系统变更不直接冲击下游。*

源系统记录进入平台后，至少要补齐五类语义：**来源、时间、版本、质量、权限**。只有这些语义稳定，Agent 才能知道数据来自哪里、截至何时、是否经过补数、能否被当前用户使用。

### 数据形态决定接入方式

企业常见数据可以分为表数据、事件、API 和文件。区别不在文件格式，而在“变化如何被识别”。

*表10-1：表数据、事件、文件等数据形态的来源、采集关注点与对 Agent 的意义。来源：本书整理。*

| 数据形态 | 典型来源 | 采集关注点 | 对 Agent 的意义 |
|---|---|---|---|
| 表数据 | OMS、WMS、ERP、CRM 数据库 | 主键、水印、删除、字段演化 | 提供订单、库存、客户、结算等结构化事实 |
| 事件数据 | 支付、风控、设备、用户行为 | 事件时间、事件 ID、幂等、重放 | 提供实时上下文和动作触发条件 |
| API 数据 | SaaS、广告、客服平台 | 分页、限流、增量游标、权限范围 | 扩展外部业务信息，但新鲜度受接口限制 |
| 文件数据 | 供应商、财务、历史归档 | 命名、分区、完整性、重复导入 | 支持低频批量导入和历史回填 |

![图10-2：源系统数据形态决定接入边界](../../images/part3/ch/ch10-02.png)

*图10-2：源系统数据形态决定接入边界。来源：本书自绘。Alt text：表数据、事件流、文件、API 四类数据形态分列，各自连向对应的采集方式与关注点（主键水印、乱序、解析、限流），说明形态不同接入边界也不同。*

接入前应先回答三个问题：平台需要当前状态还是变化过程；源系统是否有稳定的主键、时间或版本标识；下游要的是最新状态、历史回放还是低频归档。答案会直接决定目标表模型和恢复策略。

## 10.2 批处理、CDC、事件流与 API：按业务新鲜度选模式

采集模式应从业务动作出发，而不是从工具出发。月度结算更看重完整和可审计，批处理通常足够；库存预警需要分钟级变化，增量批或 CDC 更合适；支付风控依赖秒级动作，应采用事件流；外部 SaaS 常受接口限流影响，托管 ELT 或成熟连接器更现实。

**实时并不是默认更好。真正的问题是：数据晚到会不会导致错误动作。** 如果只影响报表展示，可以标注延迟；如果会导致支付拦截、库存冻结或风险止付，就必须提高新鲜度保障。

*表10-2：批同步、流处理、CDC、API 同步四种采集模式的优势、代价与适用场景。来源：本书整理。*

| 模式 | 工作方式 | 优势 | 代价 | 适用场景 | 本书建议 |
|---|---|---|---|---|---|
| 批同步 | 定时全量或分区抽取 | 简单、便宜、易对账 | 延迟高，删除捕获弱 | 财务、历史回填、低频维表 | 默认保留 |
| 增量批 | 按水印或游标周期抽取 | 复杂度适中，新鲜度较好 | 水印可靠性决定正确性 | 门店库存、订单状态准实时同步 | mini-platform 默认可选 |
| CDC | 读取数据库日志传播行级变化 | 低侵入、保留变更语义 | 依赖日志、主键和 DDL 管理 | 订单、库存、工单关键事实表 | 关键表增强 |
| 托管 ELT | 连接器或服务周期同步 | 运维成本低，覆盖 SaaS 多 | 成本、合规和厂商绑定 | CRM、客服、营销平台 | 视组织能力选择 |
| 事件流 | 业务系统主动发送事件 | 低延迟、语义清晰 | 需要业务系统改造 | 支付、风控、设备告警 | 第13章展开 |

![图10-3：采集模式选择先看业务动作和新鲜度](../../images/part3/ch/ch10-03.png)

*图10-3：采集模式选择先看业务动作和新鲜度。来源：本书自绘。Alt text：决策流图从"业务对新鲜度的要求"出发分出秒级、分钟级、小时级、天级分支，分别指向 CDC/流、CDC、批同步等模式，体现按时效需求选模式。*

判断模式时至少同时看五个维度：新鲜度、完整性、删除语义、回放能力和源系统改造成本。CDC 解决“变化怎么来”，但不能替代文件回填、历史修复和跨系统对账；连接器解决“怎么接”，也不能替代权限、质量、血缘和指标治理。

## 10.3 CDC：快照、位点、Schema 与一致性

CDC 不是“更快的同步”，而是对状态变化过程的记录。典型链路先做初始快照，再从事务日志位点持续订阅插入、更新和删除。快照和增量之间必须无缝衔接，否则故障恢复时会出现漏数或重复。

![图10-4：CDC 生命周期从初始快照进入增量订阅](../../images/part3/ch/ch10-04.png)

*图10-4：CDC 生命周期从初始快照进入增量订阅。来源：本书自绘。Alt text：时间轴上先是一次性初始快照阶段，随后切换到持续的增量日志订阅阶段，中间标出位点交接点，说明 CDC 从快照平滑过渡到增量。*

**CDC 的生产可靠性主要取决于四件事：快照是否可控、位点是否可恢复、Schema 是否兼容、下游写入是否幂等。**

*表10-3：CDC 落地的典型挑战、表现与处理策略。来源：本书整理。*

| 挑战 | 表现 | 处理策略 |
|---|---|---|
| 初始快照压力 | 大表扫描拖慢业务库 | 使用只读副本、低峰执行、分片快照、限流 |
| 位点恢复 | Connector 故障后不知道从哪里继续 | offset 外部持久化，恢复前校验日志保留窗口 |
| Schema 演化 | 源表新增、删除、改类型 | 建立兼容性规则和变更审批，记录 schema version |
| 删除语义 | 下游只 append，无法反映 delete | 明确 tombstone、软删除或 merge-on-read 策略 |

采集层不应让下游理解每种连接器的 `offset`、`LSN`、`cursor` 或 checkpoint。它应把这些内部状态收敛为统一的数据契约。

*表10-4：采集链路各组件的职责、输入输出与失败模式。来源：本书整理。*

| 组件 | 职责 | 输入 | 输出 | 失败模式 |
|---|---|---|---|---|
| Source Connector | 连接源系统并抽取数据 | 数据库日志、API、文件、事件 | 规范化记录或事件 | 权限不足、限流、日志过期 |
| Offset Store | 保存读取进度 | connector checkpoint | offset、LSN、cursor | 位点丢失、重复消费 |
| Schema Manager | 管理字段结构变化 | DDL、schema registry | schema version | 字段漂移、类型不兼容 |
| Buffer / Queue | 缓冲变更事件 | CDC event、业务事件 | topic、partition event | 积压、乱序、重复 |
| Sink Writer | 写入目标表 | 规范化事件 | 湖仓表、OLAP 表 | 幂等失败、写入冲突 |
| Audit Logger | 记录运行过程 | run state、metrics | 审计日志、血缘事件 | 无法追责 |

```json
{
  "pipeline_id": "orders-postgres-to-iceberg",
  "source": {"type": "postgres", "database": "oms", "table": "public.orders"},
  "destination": {"type": "iceberg", "table": "dwd.orders"},
  "mode": "cdc",
  "primary_key": ["order_id"],
  "freshness_slo_seconds": 60,
  "expose_to_data_agent": true,
  "quality_checks": [
    "row_count_reconciliation",
    "primary_key_uniqueness",
    "freshness_slo",
    "schema_compatibility"
  ]
}
```

![图10-5：采集契约把工具状态收敛为平台字段](../../images/part3/ch/ch10-05.png)

*图10-5：采集契约把工具状态收敛为平台字段。来源：本书自绘。Alt text：左侧多个连接器输出格式各异的原始记录，经过采集契约层映射，右侧收敛为统一的平台标准字段，体现契约层做规范化。*

这份契约同时被湖仓写入器、元数据系统和 DataAgent 使用。DataAgent 关心的不是 Connector 是否“绿灯”，而是这张表的主键、新鲜度、质量和可用状态是否满足当前任务。

## 10.4 连接器选型与恢复：工具必须服从组织能力

Debezium 更适合数据库日志 CDC；Airbyte 更像自建连接器平台；Fivetran 更适合低运维的 SaaS ELT；Flink CDC 适合 CDC 后立即进入实时转换和多 Sink 的链路。工具选型应结合已有 Kafka/Flink 能力、合规边界和源系统类型，而不是做产品排名。

*表10-5：Debezium、Flink CDC 等采集工具的适用与不适用场景。来源：本书整理。*

| 工具 | 为什么用 | 不适合什么场景 | 替代方案 | 本书建议 |
|---|---|---|---|---|
| Debezium | 数据库日志捕获成熟，适合核心表 CDC | 大量 SaaS API 和低频文件 | Flink CDC、数据库原生复制 | 用于订单、库存等关键事实表 |
| Airbyte | 连接器覆盖广，自建可控 | 连接器质量和运维需平台补强 | Fivetran、Meltano、批脚本 | 用于多源快速接入 |
| Fivetran | 托管体验好，减少连接器维护 | 成本、合规和厂商绑定 | Airbyte、自研批同步 | 用于外部 SaaS 和低运维团队 |
| Flink CDC | CDC 后可直接实时转换和多 Sink | 没有 Flink 运维能力时成本高 | Debezium + Sink、Spark 微批 | 用于实时数据管道 |

![图10-6：连接器工具应按组织能力和链路职责选择](../../images/part3/ch/ch10-06.png)

*图10-6：连接器工具应按组织能力和链路职责选择。来源：本书自绘。Alt text：二维矩阵以"组织工程能力"和"链路关键程度"为轴，把 Debezium、Flink CDC、SaaS 连接器、自建连接器分别落入不同象限，给出选型指引。*

批同步和 CDC 的差异，本质是恢复复杂度与新鲜度的交换；自建和托管 ELT 的差异，则是控制力与运维成本的交换。

*表10-6：批同步与 CDC 在新鲜度、成本、可靠性上的取舍。来源：本书整理。*

| 方案 | 优势 | 代价 | 适用场景 | 本书建议 |
|---|---|---|---|---|
| 批同步 | 成本低、对账简单、故障恢复直观 | 新鲜度差，删除捕获弱 | 财务、维表、历史回填 | 作为默认基础能力 |
| CDC | 新鲜度好，保留 insert/update/delete 语义 | 依赖日志、主键、Schema 管理和值班 | 订单、库存、工单关键事实表 | 只给高价值表启用 |

*表10-7：采购连接器与自建连接器的取舍。来源：本书整理。*

| 方案 | 优势 | 代价 | 适用场景 | 本书建议 |
|---|---|---|---|---|
| 自建连接器 | 可控、可审计、贴合内部治理 | 需要维护连接器、调度和告警 | 核心系统、敏感数据、复杂权限 | 平台团队掌握核心链路 |
| 托管 ELT | 接入快、运维少、SaaS 支持多 | 成本、合规和厂商锁定 | 外部系统、低敏数据、标准化场景 | 作为补充路径 |

![图10-7：数据采集技术取舍同时看新鲜度、成本和恢复](../../images/part3/ch/ch10-07.png)

*图10-7：数据采集技术取舍同时看新鲜度、成本和恢复。来源：本书自绘。Alt text：以新鲜度、成本、恢复难度为三轴的雷达图，批同步、CDC、流处理三种方案各画一条曲线，直观对比它们在三个维度上的强弱。*

故障恢复必须覆盖日志过期、重复、乱序、字段漂移和历史回填。只监控“任务成功”无法发现任务成功但数据错误的事故。

*表10-8：重复、乱序、字段漂移等采集失败模式的检测与恢复策略。来源：本书整理。*

| 失败模式 | 触发条件 | 影响 | 检测方式 | 恢复策略 |
|---|---|---|---|---|
| 日志过期 | Connector 停止超过日志保留 | 无法从原位点恢复 | 复制槽积压、binlog/WAL 保留 | 重新快照并对账 |
| 重复消费 | at-least-once 或恢复重放 | 指标偏高、重复记录 | 主键唯一性、事件版本 | sink 端幂等 merge |
| 乱序到达 | 网络、跨分区、大事务 | 旧事件覆盖当前状态 | 事件时间、版本监控 | 按版本或 source position 更新 |
| 字段漂移 | 新增、删除、改类型 | 写入失败或字段错位 | Schema diff | 新增自动兼容，破坏性变更审批 |
| 回填覆盖实时 | 历史和 CDC 同写 current | 最新状态被旧数据覆盖 | 批次审计、更新时间 | staging + 按版本原子合并 |

![图10-8：采集失败恢复要同时保留 changelog 和 current 表](../../images/part3/ch/ch10-08.png)

*图10-8：采集失败恢复要同时保留 changelog 和 current 表。来源：本书自绘。Alt text：图中并列两张表，记录每次变更的 changelog 表和保存最新状态的 current 表，箭头表示故障时可用 changelog 重放重建 current 表，说明两者须并存。*

**关键事实表最好同时保留 changelog 与 current：前者解释过去并支持回放，后者服务当前查询。**

## 10.5 mini-platform：把采集决策固化成契约

mini-platform 不直接连接真实数据库或 Kafka，而是先把“源类型、新鲜度、主键、水印和 Agent 暴露策略”固化成可测试规则。

- 入口：`mini-platform/infra/ingestion/__init__.py`
- 核心实现：`mini-platform/infra/ingestion/pipeline_contract.py`
- 测试：`mini-platform/tests/test_ingestion_pipeline_contract.py`
- 实战项目：`mini-platform/projects/10-ingestion-pipeline/run.py`

![图10-9：mini-platform 用规则模型生成采集契约](../../images/part3/ch/ch10-09.png)

*图10-9：mini-platform 用规则模型生成采集契约。来源：本书自绘。Alt text：流程图显示源 schema 经规则模型分析后自动生成采集契约（字段、类型、水印、主键），再下发给连接器，体现契约的半自动生成。*

```python
class SourceKind(str, Enum):
    DATABASE = "database"
    SAAS_API = "saas_api"
    FILE = "file"
    EVENT_STREAM = "event_stream"

class IngestionMode(str, Enum):
    BATCH = "batch"
    INCREMENTAL_BATCH = "incremental_batch"
    CDC = "cdc"
    MANAGED_ELT = "managed_elt"
    EVENT_STREAM = "event_stream"
```

核心决策逻辑根据源类型、新鲜度和主键选择模式：

```python
def plan_ingestion_pipeline(request: dict[str, Any]) -> PipelineDecision:
    source_kind = SourceKind(request["source_kind"])
    freshness = int(request.get("freshness_slo_seconds", 86_400))
    has_primary_key = bool(request.get("has_primary_key", False))

    if source_kind is SourceKind.DATABASE and freshness <= 300 and has_primary_key:
        return PipelineDecision(
            mode=IngestionMode.CDC,
            tool="Debezium",
            reason="数据库关键事实表需要分钟级新鲜度，且具备稳定主键。",
            freshness_slo_seconds=freshness,
            requires_primary_key=True,
            requires_watermark=False,
        )
```

`build_pipeline_contract` 再把模式转换为可被下游消费的契约，统一挂上主键、新鲜度和质量检查。

## 10.6 生产准入：让数据可用状态进入 Agent 证据链

采集数据进入 Agent 链路前，至少要验证四类证据：访问权限、恢复位点、质量状态和运营监控。核心要求包括：凭证进入 Secret 管理；同步表采用 allowlist；敏感字段在落地时标记；offset/LSN/cursor 可恢复；关键表定义 freshness SLO；重复、空值、Schema 和行数检查自动运行；延迟和积压进入告警。

**“数据存在”不等于“数据适合回答”。** 刚完成快照但增量未追平、正在历史回填、关键字段缺失或质量门禁失败的资产，都应有显式状态。可以将资产状态划分为可查询、观察、阻断和废弃，Agent 据此选择继续、降级、澄清或拒答。

用户不需要看到 Kafka offset，但应看到业务可理解的边界：数据截止时间、延迟范围、受影响区域以及是否正在修复。对于低风险查询，可以返回上一版数据并标注时间；对于正式报告和高风险动作，数据超出新鲜度或质量边界时应暂停。

采集变更也要做回放。新增连接器、修改主键、切换删除语义或历史回填，都应对核心问数样本执行前后对比，检查行数、主键、时间、删除记录、SQL 结果和最终回答。这样才能把数据变更和 Agent 回归真正接起来。

## 本章小结

**采集层是 Agent 的事实入口，而不是后台搬运工具。** 批同步、增量批、CDC、托管 ELT 和事件流应按业务新鲜度、完整性、删除语义和恢复要求选择；CDC 的关键不在“快”，而在快照、位点、Schema 和幂等写入是否可控。

生产链路必须把连接器内部状态转换成统一的数据契约，并让新鲜度、质量和回填状态进入元数据与 Trace。Agent 能否安全使用数据，取决于它是否知道这批数据**来自哪里、截至何时、是否完整，以及出了问题能否重放和解释**。

## 参考文献

Debezium. (n.d.). [Documentation](https://debezium.io/documentation/).

Airbyte. (n.d.). [Documentation](https://docs.airbyte.com/).

Apache Flink. (n.d.). [Flink CDC documentation](https://nightlies.apache.org/flink/flink-cdc-docs-stable/).

Apache Kafka. (n.d.). [Documentation](https://kafka.apache.org/documentation/).
