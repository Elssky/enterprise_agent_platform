# 第52章 合规与法规

---

合规不是上线前填一张表。企业 Agent 会处理数据、调用模型与工具、生成内容、影响业务流程，还可能跨地区、跨租户和跨供应商运行。真正进入审计时，问题都非常具体：这个 Agent 用于什么场景，处理了哪些数据，调用了哪个模型，输出影响谁，谁做过人工复核，事故发生后能否还原证据。

NIST AI RMF 用 Govern、Map、Measure、Manage 组织 AI 风险管理；NIST AI 600-1 进一步讨论生成式 AI 风险；EU AI Act 采用风险分级，并对不同系统和通用 AI 模型提出差异化要求；中国生成式 AI、深度合成与生成合成内容标识等规则，则涉及内容安全、数据来源、个人信息、标识和服务责任。C2PA/Content Credentials 进一步提供内容来源和编辑历史的技术证明路径。

**合规工程化的核心不是把法规条文翻译成更多文档，而是把“用途、数据、模型、输出、人工监督和事故”变成系统能够持续留下的证据。** 具体法规是否适用、组织承担何种法律角色，应由法务和合规团队判断；平台工程的责任是让这种判断有稳定对象、有运行证据、能在系统变化后重新评估。

---

## 52.1 控制矩阵：把要求连接到平台对象和证据

合规团队和工程团队最容易失去共同语言。合规说“需要人工监督、数据可追溯、内容有标识”，工程团队则需要知道具体落在哪个模块、哪个字段、哪个运行事件。

*表52-1：Agent 合规工程化框架。来源：本书整理。*

| 合规对象 | 工程问题 | 证据形态 |
|---|---|---|
| 用途和风险 | 用于什么业务，影响哪些个人/组织权益 | use case registry、risk tier、owner |
| 数据来源 | 训练、检索、工具数据是否可追溯、可删除 | lineage、license/consent、ACL、retention |
| 模型和供应商 | 哪个模型、版本、区域、供应商 | model card、provider、region、version |
| 输出控制 | 内容是否安全、标识、可复核 | guardrail log、citation、provenance |
| 人工监督 | 谁复核、能否纠正/撤销 | approval、appeal、review record |
| 监控和事故 | 是否持续评估、可定位事故 | Trace、Eval、incident record |

![图52-1：合规控制矩阵在平台中的位置](../../images/part10/ch/ch52-01-compliance-control-matrix.svg)

*图52-1：合规控制矩阵在平台中的位置。来源：本书自绘。Alt text：控制矩阵位于 Agent 平台中间层，左侧连接法规要求（EU AI Act、NIST、国内法规），右侧连接平台各模块（Guardrails、Trace、审批、发布验收），矩阵格表示哪条法规要求对应哪个平台控制。*

**控制矩阵不是离线 Excel，而是法规/制度义务与运行系统之间的映射层。** 每个控制项至少要有：

```text
control_id
framework / internal_policy
applicability
platform_control
owner
evidence_source
release_gate
last_reviewed_at
```

比如“人工监督”不能只写“重要结果需人工复核”，而要找到具体 `approval_id`、reviewer、所见证据、可选动作和结果；“数据来源可追溯”要能回到 Data Lineage、SQL、RAG chunk、Tool Result 和数据快照。

### 风险变化要触发重新评估

一个内部经营问答 Agent 接入客户画像、增加导出、开放外部用户或改变模型供应商后，原风险判断可能已经失效。以下变化应进入合规变更队列：

- 新增数据域或个人信息；
- 新增高风险 Tool/自动写操作；
- 用户从内部扩展到客户/公众；
- 输出从内部草稿变成正式业务材料；
- 模型供应商、部署区域或数据流变化；
- 增加跨境/外部处理路径；
- 人工监督和申诉机制变化。

平台可以自动发现一部分变化，法务/合规负责判断适用性。**工程系统的任务不是替法律团队下结论，而是让“需要重新判断”的变化不会静默发生。**

---

## 52.2 风险管理框架：NIST AI RMF 与风险分级

NIST AI RMF 的价值，不在于多一个审计模板，而在于把风险治理放进完整生命周期。

*表52-2：NIST AI RMF 到 Agent 平台动作的映射。来源：本书整理。*

| 功能 | 平台动作 | 典型证据 |
|---|---|---|
| Govern | owner、风险分级、审批、例外 | registry、policy、approval |
| Map | 场景、用户、数据、模型、Tool、影响对象 | system card、data flow、threat model |
| Measure | 质量、安全、隐私、鲁棒性、解释性 | Eval、Red Team、bias/privacy check |
| Manage | 门禁、监控、事故、持续修复 | release gate、alert、incident |

![图52-2：NIST AI RMF 生命周期闭环](../../images/part10/ch/ch52-02-ai-rmf-lifecycle.svg)

*图52-2：NIST AI RMF 生命周期闭环。来源：本书自绘。Alt text：环形闭环含 GOVERN、MAP、MEASURE、MANAGE 四个核心功能，箭头表示风险治理贯穿 AI 系统全生命周期，标注每个功能对应的典型活动（如 MAP 阶段的风险识别与分类）。*

反馈路径尤其重要。模型、Prompt、Tool、数据源和业务用途持续变化，如果风险评估只发生在立项，后续的 Measure 与 Manage 都会基于过时假设。

### EU AI Act：平台要支持按 use case 分级，而不是全平台一个等级

*表52-3：EU AI Act 风险分级的工程含义。来源：本书整理。*

| 风险层级/对象 | 工程关注 | 平台动作示例 |
|---|---|---|
| 禁止性风险 | 是否属于被禁止用途 | 用例阶段阻断并升级法务判断 |
| 高风险 | 是否影响就业、教育、信贷等重要权益 | 更强风险管理、日志、人工监督和安全控制 |
| 有限风险 | 用户是否需要知道正在与 AI 交互/内容由 AI 生成 | 告知、标识、解释 |
| 低风险 | 低影响内部辅助 | 基础安全、Trace、反馈与撤销 |
| 通用 AI 模型相关 | 外部/自研基础模型责任与文档 | 供应商、版本、部署区域和评估证据 |

同一个平台可以同时承载低风险制度问答、高风险招聘辅助和外部客户服务。**风险等级属于具体 use case，不属于“这个平台整体”。** 数据、工具和用途组合一变，等级和控制也可能变化。

---

## 52.3 中国生成式 AI 合规：先识别服务与数据边界，再落实平台控制

中国生成式 AI 相关合规通常会同时涉及内容安全、数据来源、个人信息、生成合成内容标识、服务责任，以及在具体场景下可能涉及的备案、安全评估等要求。具体是否适用，需要结合服务对象、开放范围和业务属性由法务/合规判断。

*表52-4：中国生成式 AI 合规关注点与平台控制。来源：本书整理。*

| 关注点 | 工程控制 | 证据 |
|---|---|---|
| 内容安全 | 输入/输出分类、Guardrails、人工复核 | policy/guardrail log |
| 数据来源 | 训练、RAG、上传、Tool 数据可追溯 | lineage、license/consent、retention |
| 个人信息 | 最小化、脱敏、ACL、删除/更正 | PII policy、access/deletion record |
| 生成内容标识 | 按适用场景做显式/隐式标识 | label、metadata、watermark/provenance |
| 服务责任 | 用户告知、投诉、风险处置、留痕 | terms、appeal、incident |
| 评估/备案相关 | 按实际服务类型准备系统材料 | system/model/data/eval report |

这里最容易忽略的是**旁路数据**：调试截图、Trace、失败样本、人工标注、导出 CSV、IM 转发、报告附件。这些内容在语言上可能完全正常，却可能包含个人信息、商业秘密或未公开经营数据。

因此数据治理至少要回答四个问题：

```text
哪些数据可以进入模型？
哪些数据可以进入 Trace / Eval？
哪些数据可以展示给用户？
哪些数据可以导出或传播？
```

四个答案并不相同。

DataAgent 的聚合报告也不能因为“只是摘要”就降低权限要求。摘要更容易被转发，反而更需要 Evidence、输出等级、分享范围和审计。

---

## 52.4 内容溯源：AI 标识只是第一层，业务证据链更重要

C2PA 的核心是为数字内容附加可验证 provenance，记录内容创建、编辑和签名等信息。企业可以从显式标识和元数据起步，再对高风险对外内容使用更强签名证明。

*表52-5：内容溯源能力层次。来源：本书整理。*

| 层次 | 能力 | 适用 |
|---|---|---|
| 显式标注 | 标明 AI 生成/辅助 | 对外内容、高风险内部材料 |
| 元数据 | 模型、时间、工具、责任人 | 文件、图片、音视频、报告 |
| 签名证明 | C2PA 等内容凭据 | 品牌内容、审计材料、对外发布 |
| 证据链 | 数据、SQL、Prompt、Tool、审批 | DataAgent、合规分析、经营报告 |

![图52-3：生成内容溯源链路](../../images/part10/ch/ch52-03-content-provenance.svg)

*图52-3：生成内容溯源链路。来源：本书自绘。Alt text：链路从最终 Agent 输出出发，依次追溯到使用的工具调用、检索的知识片段、原始输入，每步标注 trace ID 和时间戳，体现每条结论可追溯到完整决策链。*

**对于企业报告，“由 AI 生成”远远不够。真正有价值的 provenance 是数字和结论能够回到哪份数据、哪条 SQL、哪个 Metric、哪个模型、哪次人工编辑和哪次审批。**

![图52-4：AI 生成报告的合规证据包样张](../../images/part10/ch/ch52-04-compliance-evidence-package.png)

*图52-4：AI 生成报告的合规证据包样张。来源：本书自绘。Alt text：证据包样张展示封面、控制矩阵摘要、关键控制点测试结果、异常事件日志等部分，体现可提交给监管或审计方的合规报告结构。*

证据包建议拆成两层：

- **业务/合规摘要**：用途、数据范围、模型/供应商、审批、风险和发布状态；
- **受控技术证据**：SQL、Trace、Prompt/Context 摘要、模型版本、Tool Result、Artifact hash 和策略决策。

对外材料不应暴露全部内部实现，内部审计又不能只看到一句 AI 标识。两类视图共享同一底层证据，但访问粒度不同。

### 证据需要冻结版本

报告提交审批或正式导出时，要冻结当时的数据快照、模型版本、Metric、Artifact 和审批记录。不能让历史报告自动跟随底层最新数据变化，否则平台无法证明“当时为什么得出这个结论”。

---

## 52.5 数据主体权利、留存与外部模型边界

### 删除不是删掉一条会话

个人或业务数据可能存在于：

```text
原始数据 / 上传文件
 -> OCR/Parser/ASR
 -> RAG chunk / Embedding
 -> Memory / Cache
 -> Trace / Eval samples
 -> Artifact / Report
 -> Backup / Audit evidence
```

一次删除或更正请求必须知道派生关系。实时检索和 Memory 应停止继续使用被删除信息；某些审计 Trace 可能因法律/安全责任需要保留，但应限制访问并禁止重新进入模型上下文；评测样本可以根据场景转成脱敏版本。

**合规删除的工程基础是资产目录和 lineage。没有派生关系，就无法证明删除执行到了哪里。**

更正也要处理版本。客户状态、合同信息、组织结构或 Metric 更新后，旧向量、缓存和报告不应继续作为当前事实；历史 Run 则需要保留当时版本，解释为什么过去结果不同。

### 外部模型和跨境边界必须由平台路由执行

Agent 可能调用外部模型、OCR、向量库或第三方 Agent。平台必须知道请求中哪些内容会离开受控环境：用户输入、System Prompt、RAG chunk、Tool Result 和身份元数据都可能被发送。

第45章 LLM Gateway 应根据数据等级和合规策略执行路由，例如：

| 数据/任务 | 推荐边界 |
|---|---|
| 公开资料 | 可使用批准的外部模型 |
| 一般内部数据 | 根据供应商、区域和策略决定 |
| 敏感数据 | 受控部署或脱敏后外部处理 |
| 高敏/受监管业务 | 默认私有环境或专门批准路径 |

模型目录还应关联供应商数据处理协议、区域、日志保留、训练使用政策、安全认证和删除机制。采购材料不能和真实调用配置分离，否则审计时无法证明“那次 Run 到底用了哪个外部服务”。

---

## 52.6 合规发布、审计与持续复审

合规工程化最终要进入发布节奏，而不是在发布以后补材料。

一个 Use Case Registry 至少可以记录：

```yaml
use_case:
  id: dataagent_revenue_analysis
  owner: analytics_platform
  users: [regional_manager, finance_analyst]
  regions: [CN, EU]
  risk_tier: medium
  data_sources:
    - dataset: sales_order
      financial: true
    - dataset: customer_profile
      pii: true
  models:
    - provider: local
      model: enterprise-llm
  outputs: [chart, markdown_report, csv_export]
```

平台据此关联控制矩阵、评测、审批和证据位置。原稿中的 `mini-platform/projects/compliance-control-matrix/` 可以作为后续实验设计；当前仓库没有该实验目录，因此不应把它写成已经部署的生产模块。

### 触发式复审比所有变更走同样流程更有效

高风险触发点包括：

- 新外部模型/新处理区域；
- 新个人信息/敏感数据；
- 新写操作或自动决策；
- 新外部用户/对外发布；
- 新导出和分享渠道；
- 人工监督减少；
- 删除/留存策略变化。

低风险文案或内部读接口优化可以走轻量路径。**合规不是所有变更都变慢，而是高风险变化必须自动进入更深证据检查。**

### 审计查询要产品化

法务、内审、安全和数据治理不应每次都让工程师手工拼日志。一个受控证据目录至少应支持按以下对象检索：

```text
use_case / run_id / artifact
user / tenant
data_category
model_provider / region
tool / policy / approval
delete_request / retention
```

不同角色看到不同粒度：摘要默认可见，敏感明细需临时授权；谁查看或导出审计证据，本身也要被审计。

### 外部审计前冻结证据，而不是用当前状态解释历史

审计窗口内应固定：Use Case、模型、策略、数据类别、审批记录、Trace 样本、删除回执和相关版本。当前模型已经升级，不代表可以用新版本解释半年以前的报告。

### 持续抽样

每月从高风险 Run 中抽取少量样本验证：

- owner 是否存在；
- 数据来源是否可追；
- 模型与区域是否符合策略；
- 高风险动作是否有人监督；
- Artifact 是否有 Evidence；
- 导出、删除和留存是否按规则执行。

缺失证据应转成平台 backlog，而不是等下一次外部问询再补。

**合规成熟度的判断，不是制度文件有多厚，而是任意一个高风险用例都能快速回答“用途是什么、数据从哪里来、模型在哪里运行、谁复核过、输出去了哪里、如何纠正和删除”。**

## 本章小结

合规工程化把法规与内部制度转成平台可执行、可记录和可复核的控制。Use Case Registry 与风险等级描述用途和影响，控制矩阵把 NIST AI RMF、EU AI Act、中国相关合规要求和内部制度映射到数据、模型、Guardrails、HITL、Trace 与发布门禁；内容溯源则把生成材料连接回数据、模型、工具和人工编辑。删除、留存、外部模型和跨境调用也需要通过资产 lineage 和网关策略进入运行边界。**合规的目标不是让工程团队成为法律专家，而是让法律和合规判断能够落到稳定系统对象上，并随产品变化持续有证据可查。**

## 参考文献

- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)

- [NIST AI 600-1: Generative AI Profile](https://www.nist.gov/itl/ai-risk-management-framework/nist-ai-600-1)

- [Regulation (EU) 2024/1689: Artificial Intelligence Act](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)

- [生成式人工智能服务管理暂行办法](https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm)

- [互联网信息服务深度合成管理规定](https://www.cac.gov.cn/2022-12/11/c_1672221949354811.htm)

- [C2PA Specifications](https://c2pa.org/specifications/specifications/)
