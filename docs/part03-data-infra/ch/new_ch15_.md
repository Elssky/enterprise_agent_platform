# 第15章 元数据、血缘、契约与指标

---

DataAgent 要回答“这个数从哪来、口径是什么、能不能信”，不能靠模型根据字段名临场猜测。企业数据底座需要提前提供四类材料：**元数据说明资产是什么，血缘说明数据从哪里来，数据契约约束上游如何变化，指标体系定义业务到底怎么算。**

用户问“本月 GMV 为什么下降”，模型如果只看到 `sales_amount`、`paid_amount`、`net_revenue` 等物理字段，很容易选出一个看似合理但业务口径错误的字段。问题不一定是模型不会 SQL，而是平台没有把业务语义做成可查询、可验证的控制面。

**元数据在 Agent 平台里不再是后台文档，而是每次问数、分析、权限判断和审计都会调用的运行时基础设施。**

## 15.1 元数据控制面：让 Agent 知道“有什么、是什么、能不能用”

传统 BI 可以依靠固定看板和人工培训约束数据使用；DataAgent 面对的是开放自然语言问题，需要自动判断该用哪张表、哪个指标、哪些字段，以及当前用户能看到什么。

![图15-1：元数据控制面横跨数据基础设施层和 Agent 消费层](../../images/part3/ch/ch15-01.png)

*图15-1：元数据控制面横跨数据基础设施层和 Agent 消费层。来源：本书自绘。Alt text：中间一条贯穿的元数据控制面，向下连接采集、湖仓、编排等基础设施，向上连接 DataAgent、看板等消费方，表示元数据是连接两层的统一控制平面。*

元数据控制面不替代湖仓或 OLAP，它负责告诉上层：资产在哪里、状态如何、字段是什么意思、谁负责、质量是否通过、权限是否允许、变更会影响谁。

![图15-2：元数据如何进入 Agent 推理链路](../../images/part3/ch/ch15-02.png)

*图15-2：元数据如何进入 Agent 推理链路。来源：本书自绘。Alt text：Agent 处理问题时从元数据服务拉取表结构、口径、权限和血缘，注入推理上下文，箭头表示元数据作为运行时输入参与每次问数。*

### 数据目录不是表名搜索框

面向 Agent 的目录至少要同时提供技术、业务、运行和治理元数据。

*表15-1：技术元数据、业务元数据、操作元数据等概念的定义与区别。来源：本书整理。*

| 概念 | 定义 | 对 Agent 的价值 |
|---|---|---|
| 技术元数据 | 表名、字段、类型、分区、存储位置、刷新时间 | 说明如何访问和查询 |
| 业务元数据 | 业务含义、指标口径、Owner、适用/禁用场景 | 说明字段和指标代表什么 |
| 操作元数据 | 运行状态、质量、SLA、成本、访问频率 | 判断当前是否适合使用 |
| 治理元数据 | 分级、PII、权限、审计、保留期 | 约束谁能用、如何展示 |
| 资产画像 | 汇总上述信息形成的统一视图 | 支持搜索、推荐和影响分析 |

![图15-3：资产画像要服务消费行为](../../images/part3/ch/ch15-03.png)

*图15-3：资产画像要服务消费行为。来源：本书自绘。Alt text：资产画像（Owner、分级、质量、热度、口径）逐项连向具体消费行为（能否信任、能否使用、找谁问），强调画像服务于消费决策而非堆元数据。*

Owner 也不是装饰字段。字段有争议、质量失败、权限申请和指标变更时，平台必须知道谁能做业务裁定。没有 Owner 的资产，不适合进入高风险自动化问数。

## 15.2 血缘：从源系统一直追到 Agent 的自然语言结论

血缘要回答两个问题：数据从哪里来，以及某次变化会影响谁。传统表级血缘只能说明“表 A 生成表 B”；Agent 场景还需要知道某个指标依赖哪些字段、某次 SQL 访问了哪个快照、最终回答引用了哪个结果。

![图15-4：血缘要覆盖四层](../../images/part3/ch/ch15-04.png)

*图15-4：血缘要覆盖四层。来源：本书自绘。Alt text：血缘自上而下分四层，系统级、表级、字段级、指标级，箭头表示越往下定位越精细，说明完整血缘需覆盖四层而非只到表级。*

对核心 DataAgent 链路，血缘至少应覆盖：

1. 源系统 → 采集 → 湖仓；
2. 湖仓表 → 转换/指标；
3. 指标/表 → 查询 SQL 和执行快照；
4. 查询结果 → 报告、图表和自然语言结论。

**回答级血缘的价值，是让“这个结论从哪里来”成为可查询事实，而不是事故发生后靠人工拼日志。**

血缘通常来自多种系统：编排提供任务依赖，SQL 解析提供表/字段关系，采集系统提供源到目标映射，查询网关提供真实访问记录，Agent Runtime 再补工具调用和结果引用。OpenLineage 可以承担事件标准，DataHub/OpenMetadata 等可以承载资产视图，但资产命名、Owner 和业务语义仍需企业自己治理。

## 15.3 Data Contract：Schema 兼容不等于业务语义兼容

数据契约是生产者和消费者之间对资产的正式约定。它不能只检查字段名称和类型，还应覆盖业务语义、SLA、质量、权限和变更策略。

![图15-5：Data Contract 把隐性约定显性化](../../images/part3/ch/ch15-05.png)

*图15-5：Data Contract 把隐性约定显性化。来源：本书自绘。Alt text：左侧"隐性约定"是生产者口头承诺的字段与口径，右侧"数据契约"把这些约定写成 schema、SLA、质量规则等可校验条款，对比约定从隐性到显性。*

最危险的变更往往不是类型报错，而是“技术兼容、语义不兼容”。例如 `delivered_at` 仍然是 timestamp，但含义从“客户实际签收时间”改成“系统确认时间”；Schema 校验全部通过，履约指标却已经换了口径。

```yaml
contract:
  id: contract.fulfillment_delay.v2
  asset_id: ads.fulfillment_delay_daily
  owner: fulfillment-data-team
  consumers: [DataAgent, operations_dashboard]

schema:
  fields:
    - name: delivered_at
      type: timestamp
      required: true
      meaning: actual_customer_receipt_time
    - name: delay_minutes
      type: integer
      rule: delivered_at - promised_at

semantics:
  metric_refs: [fulfillment_delay_rate]
  grain: order_id

slo:
  freshness: "08:00 Asia/Shanghai daily"

quality:
  hard_rules: [order_id_unique, delay_minutes_non_negative]

governance:
  classification: internal
  access_policy: region_level_aggregation_only

change_policy:
  compatible: [add_nullable_field]
  incompatible: [remove_field, change_business_meaning, tighten_access_policy]
```

**契约的目标不是增加文档，而是让上游变更在发布前就能触发兼容性判断、影响分析和下游回放。**

契约服务要识别 Schema、语义、SLA、权限和质量五类变化。删除字段、修改主键、变更指标含义、降低刷新频率或收紧权限，都可能改变 Agent 行为，必须进入不同的发布门禁。

## 15.4 指标与语义层：业务问题不应直接映射到物理字段

没有统一指标层时，DataAgent 只能在物理表上临时拼 SQL，容易产生同名不同义、分母不一致、时间粒度错误和权限绕过。

![图15-6：语义层把业务问题和物理存储解耦](../../images/part3/ch/ch15-06.png)

*图15-6：语义层把业务问题和物理存储解耦。来源：本书自绘。Alt text：上层业务问题（如"上月华东 GMV"）经语义层映射到下层物理表与字段，中间语义层隔离两侧，使业务口径变化不直接依赖物理表结构。*

生产指标定义至少要包含：唯一 ID、业务说明、计算公式、过滤条件、维度、时间粒度、时区、默认聚合、权限、Owner 和状态。

*表15-3：直接查物理表与经指标层两种问数方式的取舍。来源：本书整理。*

| 方案 | 优势 | 代价 | 适用场景 | 本书建议 |
|---|---|---|---|---|
| 直接查物理表 | 灵活、开发快 | 口径分散、权限难控 | 探索、一次性排查 | 不作为生产默认路径 |
| 指标宽表 | 查询快 | 维度扩展成本高 | 高频报表、稳定指标 | 作为服务层，但定义仍进语义层 |
| Headless BI / 语义层 | 口径统一、跨应用复用 | 建模治理成本高 | 多团队共享指标、DataAgent | 生产优先建设 |
| 特征平台 | 统一在线/离线特征 | 更偏 ML 生命周期 | 风控、推荐、调度 Agent | 与指标层协作，不替代经营指标 |

Cube、MetricFlow、dbt Semantic Layer 和 Feast 解决的对象也不同。

*表15-4：Cube、MetricFlow、dbt Semantic Layer 等语义层工具的优势与适用场景。来源：本书整理。*

| 方案 | 优势 | 适用场景 | 本书建议 |
|---|---|---|---|
| Cube | 指标 API、缓存和应用服务能力强 | 产品、看板、DataAgent 指标查询 | 核心指标服务化 |
| MetricFlow | 指标、维度、时间粒度建模清晰 | 分析工程团队 | 与 dbt 模型协同 |
| dbt Semantic Layer | 与 dbt 转换、测试结合紧密 | 已有 dbt 体系 | 模型和指标统一治理 |
| Feast | 在线/离线特征一致性 | 风控、推荐、实时特征 | 不替代经营指标层 |
| 自研语义层 | 可贴合特殊权限和审计 | 强监管、复杂组织 | 现有工具确实无法满足时采用 |

![图15-7：经营查数与在线决策的数据服务边界](../../images/part3/ch/ch15-07.png)

*图15-7：经营查数与在线决策的数据服务边界。来源：本书自绘。Alt text：左侧"经营查数"走指标层、容忍秒级延迟，右侧"在线决策"走实时特征、要求毫秒级，对比两类数据服务在延迟与一致性上的不同边界。*

经营查数更需要指标、维度和口径；在线决策更依赖实时特征。二者可以共享底层事实与元数据，但不能强行用同一抽象。

## 15.5 元数据进入运行时：Schema Linking、权限、质量与血缘一起返回

Schema Linking 不应只是语义相似度搜索。自然语言里的“华东区”“履约延迟”“昨日”“门店”需要映射到候选指标、维度和资产，同时受用户权限、资产状态、质量和新鲜度约束。

![图15-8：元数据进入 Agent 运行时](../../images/part3/ch/ch15-08.png)

*图15-8：元数据进入 Agent 运行时。来源：本书自绘。Alt text：左侧"离线文档"是静态 wiki，右侧"运行时元数据"被 Agent 在每次问数时实时查询调用，对比元数据从文档变为在线服务。*

一个合理的运行时接口不是只返回字段列表，而是同时返回“应该查什么、能不能查、当前是否可信”。

```json
{
  "request_id": "req_20260611_0001",
  "user_context": {
    "user_id": "user_demo",
    "roles": ["regional_ops"],
    "region_scope": ["east"]
  },
  "question": "华东区昨日履约延迟为何上升？",
  "intent": "metric_explanation",
  "required_capabilities": [
    "asset_search",
    "metric_resolution",
    "policy_filter",
    "lineage_trace"
  ]
}
```

响应可以同时返回指标、资产、质量、权限和血缘：

```json
{
  "resolved_metrics": [
    {
      "metric_id": "fulfillment_delay_rate",
      "definition": "延迟订单数 / 已履约订单数",
      "grain": "day, region"
    }
  ],
  "authorized_assets": [
    {
      "asset_id": "ads.fulfillment_delay_daily",
      "partition": "dt=2026-06-10",
      "quality_status": "passed",
      "freshness": "2026-06-11T07:10:00+08:00"
    }
  ],
  "policy": {
    "row_filter": "region = 'east'",
    "masking": ["customer_id"],
    "allowed_actions": ["query", "explain"]
  },
  "lineage_hint": {
    "upstream_assets": ["dwd.orders_daily", "dwd.delivery_events_daily"],
    "contract": "contract.fulfillment_delay.v2"
  }
}
```

**模型不应该自己猜“哪个候选更可信”；可用性、权限和质量应由控制面先过滤。**

自然语言查询的权限也不能只靠数据库。用户可能无权看客户明细，却能通过“列出最严重的客户”绕到细粒度输出。权限必须贯穿资产发现、指标选择、SQL、结果脱敏和回答层。

![图15-9：数据治理闭环](../../images/part3/ch/ch15-09.png)

*图15-9：数据治理闭环。来源：本书自绘。Alt text：环形流程，权限过滤、脱敏、审计、合规留痕四个环节首尾相连，箭头表示每次数据访问都留痕并反馈到策略，构成持续治理闭环。*

*表15-5：仅数据库授权与多层治理两种权限脱敏策略的取舍。来源：本书整理。*

| 方案 | 优势 | 局限 | 本书建议 |
|---|---|---|---|
| 只在数据库授权 | 利用现有权限体系 | 语义层和输出仍可能泄露 | 只能作为底层防线 |
| 语义层权限 | 按指标、维度、动作控制 | 要维护策略一致性 | 生产默认控制点 |
| 结果级脱敏 | 控制最终展示 | 无法阻止中间过度访问 | 与查询前授权配合 |
| 全链路审计 | 可追责、可复盘 | 日志成本增加 | 核心 Agent 必须具备 |

## 15.6 元数据平台与发布门禁：让变更在上线前被解释

一个可落地的数据控制面至少包括元数据采集、目录、血缘、契约、指标和审计服务。

*表15-2：元数据采集器、血缘解析等组件的职责、输入输出与失败模式。来源：本书整理。*

| 组件 | 职责 | 主要输出 | 典型失败 |
|---|---|---|---|
| 元数据采集器 | 汇总湖仓、编排、质量、查询和 Agent 元数据 | 统一资产事件 | 延迟、字段缺失、重复资产 |
| 数据目录 | 搜索、标签、Owner、质量和画像 | 资产详情、推荐 | 目录失真、Owner 缺失 |
| 血缘服务 | 表/字段/查询/回答级依赖 | 血缘图、影响分析 | 动态 SQL 断点 |
| 契约服务 | Schema、语义、SLA、质量、权限 | 兼容性和审批 | 只校验 Schema |
| 指标服务 | 指标、维度、粒度和查询接口 | 指标结果、查询计划 | 同名异义、权限绕过 |
| 审计服务 | 记录访问、变更、授权和回答引用 | 审计与合规证据 | 日志缺失、身份不一致 |

![图15-10：元数据平台、血缘与指标服务的最小架构](../../images/part3/ch/ch15-10.png)

*图15-10：元数据平台、血缘与指标服务的最小架构。来源：本书自绘。Alt text：架构图含元数据存储、采集器、血缘图谱、指标服务、查询 API 五个组件，箭头标出采集、解析、对外服务的数据流向。*

一个指标定义应成为可发布对象，而不是散落在看板 SQL 里的计算片段：

```yaml
metric:
  id: fulfillment_delay_rate
  display_name: 履约延迟率
  owner: fulfillment-data-team
  status: active

calculation:
  numerator: count_orders(where: delay_minutes > 0)
  denominator: count_orders(where: delivered_at is not null)
  expression: numerator / denominator
  default_time_grain: day
  timezone: Asia/Shanghai

source:
  asset_id: ads.fulfillment_delay_daily
  required_quality_status: passed
  contract: contract.fulfillment_delay.v2

governance:
  access_policy: region_scoped
  minimum_aggregation_level: region
```

DataAgent 查询前的控制链可以抽象为：

```python
def prepare_query_context(user, question):
    candidates = metadata.search_assets_and_metrics(question)
    authorized = policy.filter(user=user, candidates=candidates)
    if not authorized:
        return deny("no_authorized_asset")

    selected = semantic_layer.resolve_metric(question, authorized)
    quality = quality_service.get_status(selected.source_asset)
    if quality.status == "blocked":
        return degrade_with_reason(selected, quality)

    lineage = lineage_service.trace(selected.source_asset)
    audit.record_intent(user=user, question=question, selected=selected)
    return {"metric": selected, "quality": quality, "lineage": lineage}
```

变更应在发布前触发影响分析，而不是上线后救火。

![图15-11：把变更前置到发布之前](../../images/part3/ch/ch15-11.png)

*图15-11：把变更前置到发布之前。来源：本书自绘。Alt text：流程显示 schema 或口径变更先经契约校验和影响分析，确认下游无碍后才发布，箭头表示变更检查前置而非上线后救火。*

元数据发布给 Agent 前，可以压缩为六类门禁：资产登记、血缘可查、契约完整、质量达标、权限/脱敏明确、指标口径统一。

![图15-12：将上线标准压缩为六个门禁](../../images/part3/ch/ch15-12.png)

*图15-12：将上线标准压缩为六个门禁。来源：本书自绘。Alt text：纵向列出六个上线门禁，元数据登记、血缘可查、契约就位、质量达标、权限脱敏、口径统一，每项标注通过条件，构成数据资产发布前的检查项。*

### 元数据与语义层的分工

两者经常被混用，但职责不同：

- **元数据控制面**回答“有哪些资产、谁负责、状态如何、从哪里来、能否访问”；
- **语义层**回答“业务问题应该用哪个指标、哪个维度、哪个粒度和口径”。

字段下线、表迁移、质量阻断属于资产/契约变化；指标公式、别名和默认粒度属于语义变化。Trace 最好同时记录资产版本和语义版本，这样才能判断一次回答变化究竟发生在哪一层。

生产运营还要治理元数据自身的质量：字段描述为空、血缘长期不更新、Owner 离职、指标定义与代码不一致，都可能让 Agent 使用错误控制信息。**元数据一旦进入运行时，它自己也需要 SLO、版本和质量治理。**

## 本章小结

元数据、血缘、数据契约和指标体系共同构成 Agent 平台的数据控制面。它们解决的不是“文档是否齐全”，而是让每次问数都能明确**查什么、按什么口径查、当前能不能查、结果从哪里来**。

Data Contract 必须覆盖技术 Schema 之外的业务语义、SLA、权限和质量；血缘要从源系统延伸到最终回答；指标和语义层要把业务概念与物理表解耦；权限、质量和新鲜度则必须进入运行时过滤。

**模型能力越强，越不能让它用猜测替代数据控制面。结构化、可版本化的企业语义才是 DataAgent 稳定查数的基础。**

## 参考文献

OpenLineage. (n.d.). [Documentation](https://openlineage.io/docs/).

DataHub. (n.d.). [Documentation](https://datahubproject.io/docs/).

Marquez. (n.d.). [Documentation](https://marquezproject.ai/docs/).

dbt Labs. (n.d.). [MetricFlow documentation](https://docs.getdbt.com/docs/build/metricflow-time-spine).

Cube. (n.d.). [Semantic layer documentation](https://cube.dev/docs/product/semantic-layer).
