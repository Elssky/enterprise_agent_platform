# 第48章 Generative UI 与富交互

---

DataAgent 的富交互不是“多画几张图”，更不是让模型直接生成一段 HTML。用户完成毛利异常分析后，会继续筛选门店、修改时间范围、保存经营说明、提交审批、导出报告。此时图表、表格、表单和按钮都开始影响真实业务状态。

如果图表没有绑定指标口径，表格没有字段权限，导出按钮绕过服务端审批，Artifact 编辑后覆盖了原始证据，界面越丰富，事故越难解释。

**Generative UI 的生产定义应是：Agent 在受控协议内选择、填充和编排平台登记过的组件；模型表达界面意图，平台决定什么能够被渲染、查看和执行。** 这把富交互从“模型生成前端”重新放回 Tool Registry、Policy、Runtime、Evidence 和 Trace 的治理边界内。

第47章解决事件流和任务状态，本章进一步回答：工具结果怎样成为图表、表格、表单、Artifact 和审批卡片；用户修改或点击后，怎样继续保持权限、证据和审计链路。

---

## 48.1 从对话结果到任务工作台

对话回答通常在消息结束时完成；富交互对象会继续进入业务流程。用户可能编辑报告、调整筛选器、钻取数据、提交审批或导出文件。因此每个交互对象都应有稳定身份、状态和动作边界。

*表48-1：从对话 UI 到 Generative UI 的能力递进。来源：本书整理。*

| 第47章能力 | 第48章新增对象 | 企业边界 |
|---|---|---|
| 流式消息 | 图表、表格 | 字段、口径和 `data_ref` 受控 |
| 工具状态 | 可操作工具卡 | 动作重新鉴权 |
| 应用状态 | 筛选器、表单 | 参数通过 Schema 校验 |
| 人在回路 | 审批卡片 | 影响范围、证据和决策留痕 |
| 对话历史 | Artifact 工作区 | 版本、协作、发布与撤回 |

Generative UI 可以服务六类常见任务：异常分析、经营报告、参数修正、审批确认、数据核验和协作交接。

*表48-2：DataAgent 工作台任务入口。来源：本书整理。*

| 任务 | 富交互对象 | 后续动作 |
|---|---|---|
| 异常分析 | 图表、表格、口径卡 | 钻取、切维度 |
| 经营报告 | Artifact、图表引用 | 编辑、复核、发布 |
| 参数修正 | 筛选器、表单 | 重新执行 Tool |
| 审批确认 | 审批卡、影响范围 | 批准、拒绝、转派 |
| 数据核验 | 字段表、质量提示 | 修正映射、反馈数据问题 |
| 协作交接 | 评论、任务状态、引用 | 转工单、通知责任人 |

**富交互的价值，在于把“Agent 说了什么”推进到“用户基于什么证据做了什么”。**

### 产品形态可以借鉴，治理边界不能照搬

国内 Agent 产品正在从单纯聊天走向插件、工作流和可配置任务界面。腾讯元器的 MCP 插件配置、阿里云百炼的 Agent/Workflow 类型、Coze Studio 的节点试运行，都说明一个共同趋势：外部能力先结构化登记，再进入用户可操作界面。

![图48-1：腾讯元器接入 MCP 插件的配置表单](../../images/part9/ch/ch48-tencent-mcp-plugin-form.png)

*图48-1：腾讯元器接入 MCP 插件的配置表单。来源：产品界面截图。Alt text：表单展示 MCP 服务地址、鉴权方式、工具列表等配置项，体现国产 Agent 平台集成外部工具的典型 UI 交互方式。*

工具进入界面前，平台必须知道它是谁、有哪些参数、返回什么结构、需要什么权限。

![图48-2：阿里云百炼 Model Studio 的应用类型创建界面](../../images/part9/ch/ch48-alibaba-application-type.png)

*图48-2：阿里云百炼 Model Studio 的应用类型创建界面。来源：产品界面截图。Alt text：界面展示对话助手、工作流助手等应用类型卡片，每类标注适用场景，体现企业 Agent 平台按任务形态提供差异化模板的 UI 设计。*

自主决策型任务和固定 Workflow 不必共享同一种界面容器。

![图48-3：Coze Studio 单节点试运行表单](../../images/part9/ch/ch48-coze-node-test-form.png)

*图48-3：Coze Studio 单节点试运行表单。来源：产品界面截图。Alt text：表单展示节点名称、输入参数填写区、运行结果展示区，体现低代码平台对工作流节点的调试 UI，输入参数、看输出结果、验证单步逻辑。*

输入 Schema、运行结果和日志处在同一工具节点里，比把原始工具 JSON 扔回聊天气泡更适合调试和治理。

---

## 48.2 Render Contract：模型选择组件，平台控制渲染

Generative UI 最重要的边界是**模型不拥有 DOM 和业务执行权**。模型输出结构化渲染意图，Render Gateway 再结合 ToolSpec、组件白名单、用户权限和 Policy 生成最终契约。

![图48-4：Generative UI 在企业 Agent 平台中的位置](../../images/part9/ch/ch48-position.svg)

*图48-4：Generative UI 在企业 Agent 平台中的位置。来源：本书自绘。Alt text：分层图中 Generative UI 位于 Agent 与用户之间，向下订阅工具调用结果和状态事件，向上展示富内容并把用户编辑回写给 Agent，标出它比普通对话 UI 多出的渲染与交互职责。*

一条推荐链路是：

```text
Tool Result
   ↓
Runtime：权限/证据/状态整理
   ↓
Render Gateway
   ↓
Component Registry + Policy
   ↓
受控 Render Contract
   ↓
Frontend Renderer
   ↓
用户动作 -> Runtime / Policy / Trace
```

*表48-3：核心概念及边界。来源：本书整理。*

| 概念 | 含义 | 不是什么 |
|---|---|---|
| Generative UI | Agent 选择并填充受控组件 | 任意前端代码生成 |
| Tool Rendering | Tool Result → 业务组件 | 原样展示工具日志 |
| Artifact | 独立生命周期的业务产物 | 大号消息附件 |
| 业务控件 | 会改变参数/状态的表单和按钮 | 装饰组件 |
| Component Registry | 可供 Agent 引用的组件与版本白名单 | 全部前端组件库 |
| Approval Card | 高风险动作的人机控制点 | 普通确认弹窗 |

**前端组件能显示什么、能操作什么、操作后能否执行，是三个不同权限问题。** 契约可以显式拆分：

```json
{
  "component": "chart",
  "component_version": "1.0",
  "data_ref": "dataset://retail-demo/margin/run_001",
  "visible_fields": ["sku_name", "gross_margin_delta", "category"],
  "allowed_actions": ["drill_down", "export_png"],
  "evidence": {
    "metric": "gross_margin_delta",
    "sql_ref": "sql://trace_abc/query_003"
  },
  "policy": {
    "approval_required": false,
    "allowed_roles": ["retail_manager", "finance_analyst"]
  },
  "trace_id": "trace_abc"
}
```

模型可以建议柱状图，不能凭自然语言创造一个“导出全部客户明细”的有效按钮。

---

## 48.3 五类基础组件：少而稳，比“什么都能生成”更重要

早期企业平台不需要几十种图表和任意控件。更值得做扎实的是五类高频组件。

*表48-4：基础 Generative UI 组件。来源：本书整理。*

| 组件 | 数据 | 常见动作 | 核心治理 |
|---|---|---|---|
| Chart | 聚合数据 + spec | 钻取、切维度、导出图 | 口径、分母、范围、快照 |
| Table | `data_ref` / 小结果 | 排序、筛选、下载 | 行列权限、脱敏、分页 |
| Form | Tool 参数 Schema | 修改、提交 | Schema + 服务端鉴权 |
| Artifact | 报告、方案、代码 | 编辑、复核、发布 | 版本、证据、协作 |
| Approval Card | 动作 + 影响范围 | 通过、拒绝、转派 | Policy、身份、审计 |

![图48-5：工具结果到受控组件的渲染契约](../../images/part9/ch/ch48-render-contract.svg)

*图48-5：工具结果到受控组件的渲染契约。来源：本书自绘。Alt text：工具调用返回 JSON 结构，前端按 type 字段分发到对应渲染组件（表格、图表、代码块、表单），契约约束双方不得越权改写彼此的数据，体现前端与 Agent 的解耦。*

### `data_ref` 是大数据和权限治理的关键

小摘要可以直接随消息返回，大表或敏感数据应使用引用。用户每次展开、分页、筛选或下载时，服务端根据**当前身份和当前策略**重新鉴权。这样既避免浏览器持有海量数据，也避免历史消息成为永久数据缓存。

```text
消息/Artifact：保存 data_ref + schema + summary
              ↓ 用户查看/导出
Data API：重新鉴权 + 脱敏 + 分页
              ↓
当前可见结果
```

生成时有权看，不代表未来仍有权看；原作者有权看，也不代表分享接收者有权看。

### 图表不是图片提示词

图表应使用结构化 spec，并绑定：指标、时间范围、数据引用、排序规则、聚合方式和口径版本。模型可以建议图表类型，但**不能从自然语言报告重新计算数字，也不能通过视觉选择隐藏关键分母或过滤条件。**

---

## 48.4 Artifact：从消息附件变成独立业务产物

报告、经营说明、SQL 草稿和图表组合往往比原对话活得更久。Run 可以结束，Artifact 仍可能继续编辑、审批和发布；会话可以归档，已发布报告仍然需要审计。因此 Artifact 应拥有独立生命周期。

![图48-6：Artifact 生命周期状态机](../../images/part9/ch/ch48-artifact-state.svg)

*图48-6：Artifact 生命周期状态机。来源：本书自绘。Alt text：状态机含 generating、generated、editing、committed、archived 等节点，箭头标出用户编辑、提交、归档触发的迁移，体现可编辑产物的完整生命周期管理。*

可采用类似状态：

```text
generating -> draft -> reviewing -> approved -> published -> archived
                    \-> rejected
published -> withdrawn / superseded
```

*表48-5：Artifact 必需的四类信息。来源：本书整理。*

| 类型 | 内容 |
|---|---|
| 正文 | 文字、图表布局、说明块 |
| 证据 | SQL、Metric、data snapshot、EvidenceRef |
| 编辑 | AI 生成、人工修改、评论、diff |
| 状态 | 草稿、复核、审批、发布、撤回 |

**可编辑正文和不可静默覆盖的事实证据必须分开。** 用户可以把“毛利下降明显”改成更适合经营会议的措辞，但不能通过富文本编辑器把底层指标值改成另一个数字后仍保留原 EvidenceRef。

### 多人协作

多人协作至少要保证：

- Artifact 有 owner；
- 每次编辑形成版本；
- 高风险字段变化重新复核；
- 发布/导出绑定具体版本，而不是“当前最新”；
- Agent 对已复核段落默认生成候选修改，而不是直接覆盖。

普通文字可以 merge，指标引用和审批状态发生冲突时不能只做文本合并。

### 发布与撤回

Artifact 发布以后可能进入邮件、PPT、会议、工单和其他页面。如果后来发现数据补数、口径错误或权限变化，平台需要区分：过期、撤回、替换新版本和通知接收者。

撤回不是删除历史。旧版本要继续保留审计事实，但应明确标记“不可再作为当前结论使用”。

---

## 48.5 审批、导出与 UI 安全

Generative UI 会诱导用户点击真实动作，因此前端绝不能成为唯一安全边界。

![图48-7：UI 安全与审批时序](../../images/part9/ch/ch48-approval-sequence.svg)

*图48-7：UI 安全与审批时序。来源：本书自绘。Alt text：时序图展示 Agent 产生高风险动作时前端弹出审批控件、用户确认或拒绝、确认后 Runtime 继续执行，拒绝后任务暂停，体现审批在 UI 层的完整交互。*

正确路径是：

```text
Agent 提议动作
  ↓
Runtime/Policy 评估风险
  ↓
前端显示 Approval Card
  ↓
用户提交“同意/拒绝”意图
  ↓
服务端再次校验身份、版本和动作参数
  ↓
Tool 执行
```

隐藏按钮、disabled 状态和客户端角色判断，都不能代替服务端授权。

*表48-6：富交互风险与处理。来源：本书整理。*

| 风险 | 处理 |
|---|---|
| 任意 HTML/JS | 模型只输出结构化组件意图 |
| XSS/危险链接 | 转义、CSP、禁原始 HTML、跳转确认 |
| 未授权组件 | Registry 白名单校验 |
| Schema 漂移 | 版本化 Render Contract |
| 图表误导 | 强制口径、范围、数据来源 |
| 导出绕权 | 后端生成导出件并重检权限 |
| Artifact 污染 | 标记生成来源，高风险内容人工确认 |
| 旧组件不可回放 | 兼容层或静态摘要降级 |

![图48-8：模型输出与前端渲染之间的安全边界](../../images/part9/ch/ch48-security-boundary.svg)

*图48-8：模型输出与前端渲染之间的安全边界。来源：本书自绘。Alt text：模型输出经过 HTML 转义、CSP 限制、沙箱隔离等安全层才渲染到 DOM，箭头标出每道过滤关卡，防止模型生成的恶意脚本执行。*

### 导出必须重新校验

分享、下载、邮件发送、嵌入外部系统和生成 PDF，都是新的数据访问动作。导出时应重新检查：

- 当前用户权限；
- 接收范围；
- Artifact 版本；
- 每个组件的数据等级；
- Evidence 是否仍有效；
- 是否需要审批；
- 是否需要脱敏降级版。

**“用户已经在页面上看见了”并不能推出“允许导出和传播”。**

---

## 48.6 组件版本、兼容与降级

富交互比文本更容易受到前端升级影响。图表库、组件 Schema、数据域和权限策略都会变化；历史 Artifact 不能因为 UI 升级就变成打不开的黑盒。

平台应同时保存：

```text
component_type
component_version
render_contract_version
data_ref / evidence_ref
artifact_version
policy_version
```

组件不兼容时，优先降级为**只读摘要 + Evidence 链接 + 重新生成入口**，而不是让整条历史消息失败。

典型降级：

| 情况 | 降级方式 |
|---|---|
| 图表组件不可用 | 表格/静态摘要 |
| `data_ref` 过期 | 标记过期 + 重新计算 |
| 当前权限降低 | 保留元数据，隐藏敏感内容 |
| 审批状态冲突 | 以后端最新状态为准 |
| 旧组件版本已退役 | 静态快照 + 迁移说明 |

组件模板也需要版本和退役。高频报告布局、指标卡和审批卡可以沉淀为模板，但要绑定适用任务、Metric、权限要求和最后复审时间。错误模板的规模化复用，比一次模型生成错误更危险。

---

## 48.7 运行证据、验收与持续改进

Generative UI 的观测对象不是“组件渲染成功率”而已，还包括用户怎样使用产物：是否改图、删图、修改指标说明、拒绝导出、重新生成、提交审批或撤回发布。

一条 Artifact Trace 最好可以串起：

```text
原始问题
 -> Tool Calls
 -> data_ref / EvidenceRef
 -> Render Contract
 -> 用户编辑
 -> Approval
 -> Published Artifact
 -> Export / Share
 -> Feedback / Withdrawal
```

这些信号能把问题分到正确 owner：用户反复删掉某类图表，可能是图表选择策略；反复修改指标解释，可能是语义层；反复拒绝导出，可能是风险提示和权限规则。

### 上线验收应使用完整产物样本

不要分别让前端看组件、后端看接口、安全看 Policy。用一个真实 Artifact 样本贯穿：

1. Tool 产出结构化结果和证据；
2. Render Gateway 生成组件；
3. 用户修改筛选器并重新计算；
4. 用户编辑报告文字；
5. 审批人检查证据；
6. 导出时权限变化；
7. 发布后发现口径问题并撤回。

验收至少要证明：

- 组件只使用授权字段；
- 动作不能绕过服务端；
- 用户编辑不会静默改变证据事实；
- 历史 Artifact 可以按当时版本回放；
- 权限变化后敏感内容会重新校验；
- 已发布产物能够被标记过期、撤回和通知。

**Generative UI 的成熟度不在组件数量，而在一个富交互产物从生成到撤回是否始终可解释。**

## 本章小结

Generative UI 应让 Agent 在组件白名单和 Render Contract 内选择界面，而不是生成任意 HTML/JS。Tool Result 必须先经过 Runtime、Policy 和证据整理，再映射为图表、表格、表单、Artifact 或审批卡片。`data_ref` 负责把大数据和权限从消息中解耦，用户查看或导出时重新鉴权。Artifact 不是消息附件，它拥有独立版本、协作、审批、发布、撤回和证据生命周期。任何会改变业务状态的 UI 动作都必须服务端二次校验。**富交互真正增加的不是视觉复杂度，而是业务动作和产物责任，因此治理强度也必须同步增加。**

## 参考文献

Vercel. (n.d.). [AI SDK documentation](https://sdk.vercel.ai/docs).

Model Context Protocol. (n.d.). [Specification and documentation](https://modelcontextprotocol.io/).

JSON Schema. (n.d.). [Specification](https://json-schema.org/).

W3C. (n.d.). [Web Content Accessibility Guidelines (WCAG) 2.2](https://www.w3.org/TR/WCAG22/).
