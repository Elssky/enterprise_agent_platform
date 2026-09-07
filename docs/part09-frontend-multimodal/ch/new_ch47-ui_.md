# 第47章 对话 UI 与流式输出

---

Agent UI 不是聊天窗口的换皮。业务用户问“华东区本月毛利异常来自哪些 SKU”，如果页面只流式输出一句“主要来自生鲜和家电”，任务仍然没有落地。用户还需要知道：系统用了哪个指标口径，正在查数据还是等审批，工具是否成功，证据能否展开，失败后能否继续，停止按钮是否真的终止了后台任务。

**企业 Agent UI 的核心对象不是一段文本，而是一条正在运行、可以中断、恢复、审批和追溯的任务。** 聊天气泡只是这个任务的一种视图。前端需要把 Runtime、Tool Registry、Policy、Artifact 和 Trace 的状态翻译成用户能理解的界面，同时把取消、重试、审批、导出和反馈重新写回同一条 Run。

本章聚焦三件事：怎样定义前后端事件协议，怎样从事件流构建稳定消息状态，以及怎样处理断线、取消、工具等待和多端恢复。第48章继续讨论图表、表格、Artifact 与审批卡片，第49章再扩展到文件和语音。

---

## 47.1 企业 Agent UI：聊天只是入口

普通聊天 UI 主要关注消息输入、Markdown 渲染和逐字输出。企业 Agent UI 还要承载任务状态、工具证据和业务动作。

*表47-1：企业 Agent UI 七类界面单元。来源：本书整理。*

| 界面单元 | 作用 | 企业要求 |
|---|---|---|
| 会话入口 | 输入问题、选择工作区与任务模式 | 绑定租户、用户、数据域与权限 |
| 消息流 | 展示问题、回答、引用和错误 | 支持流式、折叠、恢复和引用跳转 |
| 工具进度 | SQL、检索、图表、审批等状态 | 只展示授权后的参数摘要和结果 |
| 上下文面板 | 指标口径、数据源、筛选条件 | 说明回答适用范围 |
| 业务控件 | 停止、重试、确认、导出、转人工 | 高风险动作服务端二次校验 |
| 反馈入口 | 差评、纠错、人工备注 | 回流 Eval 与 Run 复盘 |
| 观测标识 | `run_id`、trace、版本、耗时 | 支持排障与审计 |

**前端透明不等于把内部日志全部展示给用户。** 用户需要的是“正在查询销售数据”“等待审批”“查询被权限策略拒绝”，而不是 SQL 引擎堆栈、模型内部调试文本或未经脱敏的工具返回。

不同角色还需要不同视图：业务用户看任务、证据与可操作入口；工程人员看事件、错误码与 Trace；安全或合规人员看权限、审批和导出。三种视图可以来自同一 Run，但字段可见性必须分开。

### 业界路线：框架解决效率，平台仍要定义契约

*表47-2：Agent UI 技术路线及边界。来源：本书整理。*

| 路线 | 代表 | 主要价值 | 企业仍需自建 |
|---|---|---|---|
| 流式应用 SDK | Vercel AI SDK | 模型流、消息 hooks、工具调用 | 权限、Trace、业务状态 |
| 对话组件框架 | assistant-ui | 线程、消息、附件、运行态组件 | Tool/Policy/Artifact 契约 |
| 应用内 Copilot | CopilotKit | 共享页面状态、人在回路 | 服务端授权和审计 |
| Agent-UI 协议 | AG-UI | 跨后端统一事件语义 | 租户、组件、安全和观测规范 |

框架可以替换，**`run_id`、消息状态、工具状态、审批和错误语义不能跟着框架一起变化。**

---

## 47.2 流式协议：SSE 传输的是任务事件，不只是 token

文本型 DataAgent 默认适合 SSE。服务端持续推送文本、工具进度和状态，客户端偶尔通过普通 HTTP 发送取消、审批等控制请求，部署和浏览器支持都相对简单。WebSocket 更适合强双向控制、多人协作和实时语音；WebRTC 留到第49章处理低延迟媒体。

*表47-3：三类实时链路的适用边界。来源：本书整理。*

| 协议 | 适合 | 不足 |
|---|---|---|
| SSE | 文本流、工具进度、长任务状态 | 双向控制较弱 |
| WebSocket | 双向控制、协同、复杂实时状态 | 鉴权、心跳和扩容更复杂 |
| WebRTC | 实时音视频、语音 Agent | 媒体链路工程复杂 |

流式协议最重要的不是“更早看到第一个字”，而是前端能否回答：这条事件属于哪个 Run、排第几、能否去重、断线后从哪里继续。

一个最小事件应包含：

```json
{
  "event_id": "evt_002",
  "run_id": "run_001",
  "message_id": "msg_001",
  "seq": 2,
  "type": "message.delta",
  "payload": {"content_delta": "正在查询"},
  "trace_id": "trace_abc"
}
```

*表47-4：DataAgent 流式事件契约。来源：本书整理。*

| 事件 | 触发时机 | 前端动作 |
|---|---|---|
| `message.created` | Runtime 创建助手消息 | 新建占位消息 |
| `message.delta` | 产生文本增量 | 增量渲染 |
| `tool.call.started` | 准备调用工具 | 新建工具卡 |
| `tool.call.delta` | 工具返回进度 | 更新阶段、行数、耗时 |
| `tool.call.completed` | 工具结束 | 固化摘要和结果引用 |
| `approval.required` | 需要人工确认 | 插入审批卡 |
| `message.completed` | 本轮完成 | 关闭运行态、开放反馈 |
| `error` | 任一阶段失败 | 展示恢复路径 |

**最终状态必须由 Runtime 事件决定，不能由模型文字决定。** 模型即使先输出“查询完成”，只要 `tool.call.completed` 还没到，UI 就不能把任务标成成功；工具被 Policy 拒绝后，也不能让前面的自然语言承诺继续制造“好像执行过”的错觉。

---

## 47.3 从事件流到稳定消息模型

企业前端建议把 Session、Message 和 Event 分开。事件描述过程，消息是过程折叠后的视图，会话则提供多轮与权限上下文。

*表47-5：消息模型三层。来源：本书整理。*

| 层 | 内容 | 用途 |
|---|---|---|
| Conversation | 用户、租户、工作区、权限上下文 | 多轮与跨端恢复 |
| Message | 用户/助手/工具/审批/错误消息 | 展示、引用与反馈 |
| Event | 某条消息的增量过程 | 流式、幂等、恢复 |

前端的 Event Reducer 把有序事件折叠为消息树和工具卡，而不是把 token 直接拼成字符串。

![图47-1：对话 UI 在企业 Agent 平台中的位置](../../images/part9/ch/ch47-position.svg)

*图47-1：对话 UI 在企业 Agent 平台中的位置。来源：本书自绘。Alt text：分层图中对话 UI 位于顶层，向下通过 HTTP/WebSocket 接 Agent Runtime，UI 层标注消息展示、状态感知、审批交互、证据展示四个职责区。*

前端不应直接调用模型或 Tool。Conversation API 负责把 Runtime、Gateway 和 Tool Registry 的内部事件转换为稳定 UI 契约，并在返回前完成权限与脱敏。

![图47-2：DataAgent 流式对话时序](../../images/part9/ch/ch47-sequence.svg)

*图47-2：DataAgent 流式对话时序。来源：本书自绘。Alt text：时序图展示用户提问、服务端推送 state/token/tool_call/done 事件、前端逐步渲染增量内容，工具调用期间显示 loading 状态，体现对话 UI 与 Agent 执行的实时协作。*

![图47-3：流式事件模型与前端 reducer](../../images/part9/ch/ch47-event-model.svg)

*图47-3：流式事件模型与前端 reducer。来源：本书自绘。Alt text：左侧是 SSE 事件流（state/token/tool_call/done 等类型），右侧是前端 reducer 把每个事件映射到状态更新，箭头展示事件驱动 UI 更新的数据流。*

Reducer 至少要处理四类非理想输入：

- 重复事件：按 `event_id` 幂等；
- 并发工具事件：按 `seq` 与父子关系折叠；
- 旧流污染：按 `run_id` 丢弃已取消 Run 的迟到事件；
- 历史恢复：快照 + 游标后的增量，而不是重播全部 token。

### 组件职责

*表47-6：Agent UI 关键组件。来源：本书整理。*

| 组件 | 职责 | 典型失败 |
|---|---|---|
| Conversation API | 统一会话与事件流 | 鉴权失败、事件断链 |
| Event Reducer | 事件 → UI 状态 | 重复、乱序、旧流污染 |
| Message Renderer | Markdown、引用、错误 | XSS、超大内容卡顿 |
| Tool Panel | 工具状态和结果摘要 | 敏感字段暴露 |
| Interaction Controller | 取消、重试、审批、导出 | 前端状态与后端状态不一致 |
| Observability Adapter | UI 行为 → Trace | 隐私字段过采集 |

工具大结果不要直接塞进消息。小摘要可以内联，表格和大对象应使用 `data_ref`，用户展开或下载时由服务端重新鉴权。

---

## 47.4 状态机：Streaming、ToolRunning、WaitingHuman 必须分开

只有 `loading / done` 两个状态无法承载 Agent 任务。至少应区分：

```text
idle
  -> streaming
  -> tool_running
  -> waiting_human
  -> streaming
  -> completed

任一运行态 -> recovering / error / cancelled
```

![图47-7：流式 UI 状态机](../../images/part9/ch/ch47-state.svg)

*图47-7：流式 UI 状态机。来源：本书自绘。Alt text：状态机含 idle、streaming、tool_calling、waiting_human、done、error 等节点，箭头标出 SSE 事件触发的合法迁移，体现前端状态随服务端事件驱动转换。*

### 取消不是“停止显示文字”

用户点击停止后，需要发生三件事：

1. 前端停止当前 Run 的渲染；
2. Runtime 收到 cancel 并迁移任务状态；
3. 能取消的工具尽量中止，不能取消的副作用步骤记录真实结果。

如果前端只断开 SSE，后台 SQL 仍可能继续执行，几十秒后旧结果又写回会话。

### 重试不是重发同一句话

重试应带上失败阶段和已完成证据。SQL 已成功而报告生成失败时，不需要重新查数；权限拒绝则不应重试，而应引导申请权限或调整问题。**恢复语义属于 Runtime，UI 只负责把可用恢复动作正确呈现。**

### 断线恢复

页面刷新或网络中断后，客户端先读取后端 Run 快照，再从游标继续订阅事件：

```text
GET /runs/{run_id}/snapshot
GET /runs/{run_id}/events?after_seq=128
```

前端浏览器内存不能成为任务事实来源。长任务可以跨设备回来继续查看，前提是 Run、Artifact 和 Event 都在后端持久化。

*表47-7：高频可靠性问题。来源：本书整理。*

| 问题 | 处理 |
|---|---|
| SSE 断线 | 游标恢复，超窗后展示重新连接/查看快照 |
| 事件乱序 | `seq + event_id` 幂等折叠 |
| 取消后旧事件到达 | 依据失效 `run_id` 丢弃 |
| 大工具结果 | 摘要 + `data_ref` |
| Markdown 注入 | 禁原始 HTML、URL 白名单/跳转确认 |
| 权限拒绝 | 独立状态和可行动提示，不包装成“AI 不会” |

---

## 47.5 UI SDK 与产品形态：借能力，不把平台语义外包

Vercel AI SDK、assistant-ui、CopilotKit 和 AG-UI 都值得借鉴，但它们分别覆盖流式 SDK、对话组件、应用状态连接和事件协议。企业平台仍应维护自己的 Conversation、Run、Tool、Approval 和 Artifact 契约。

国内 Agent 产品也能提供产品形态参照：腾讯元器把标准模式、工作流和 Multi-Agent 在入口处分开；阿里云百炼将模型、提示词、知识库、插件放在配置面；Coze Studio 用画布表达工作流节点和状态。这些界面更有价值的地方，不是视觉样式，而是**把不同任务形态和影响质量的配置显式化**。

![图47-4：腾讯元器的智能体应用模式选择界面](../../images/part9/ch/ch47-tencent-yuanqi-mode.png)

*图47-4：腾讯元器的智能体应用模式选择界面。来源：产品界面截图。Alt text：界面展示对话、工作流、发布等模式切换入口，标注 Agent 配置区与对话预览区的布局，体现 Copilot 式 Agent 构建工具的典型 UI 结构。*

普通问答、固定 Workflow 和 Multi-Agent 不必都藏在一个输入框里让 Runtime 猜。

![图47-5：阿里云百炼 Model Studio 的 Agent 配置界面](../../images/part9/ch/ch47-alibaba-modelstudio-config.png)

*图47-5：阿里云百炼 Model Studio 的 Agent 配置界面。来源：产品界面截图。Alt text：界面分工具栏、模型选择、系统提示词、测试对话四个区域，展示企业级 Agent 构建平台的典型配置 UI 组成。*

模型、知识源和插件等影响回答质量的设置，应能被查看和版本化，而不是成为后端隐藏参数。

![图47-6：Coze Studio 工作流画布中的节点与配置面板](../../images/part9/ch/ch47-coze-workflow-canvas.png)

*图47-6：Coze Studio 工作流画布中的节点与配置面板。来源：产品界面截图。Alt text：画布中多个工作流节点通过连线组成 DAG，右侧面板配置选中节点的参数，体现低代码 Agent 编排工具的可视化工作流 UI。*

多步骤查询、计算、绘图、审批和导出，更适合用任务/节点视图承载，而不是全部压进自然语言消息。

---

## 47.6 前端可观测、异常回放与验收

前端可观测不是页面 PV/UV。它要解释用户实际经历的一次 Run：首字何时出现，工具卡何时出现，中间是否断线，用户是否取消、重试、展开证据或修改参数。

*表47-8：前端观测维度。来源：本书整理。*

| 维度 | 典型指标 |
|---|---|
| 体验 | TTFT、完整回答时间、工具卡首帧 |
| 可靠性 | 断线率、恢复率、取消成功率、重复事件率 |
| 质量 | 差评、追问、证据展开、人工纠错 |
| 治理 | 权限拒绝、审批、导出、敏感字段拦截 |

这些行为要与 `run_id`、`artifact_id` 和 trace 关联，但不要把原始敏感内容无边界复制到前端日志。

### 上线前必须跑异常路径

建议把以下事件序列做成前端回归样本：

- 流式回答中途断网并重连；
- 工具超时后进入可重试失败；
- 权限拒绝并引导申请；
- 审批等待到期；
- 用户取消后迟到 token/tool result 到达；
- 刷新页面后恢复长任务；
- 大表只展示摘要和 `data_ref`；
- 旧事件协议/旧客户端回放历史 Run。

每个样本都应保存**初始状态、事件序列、期望 UI 状态与后端 Run 状态**。只看截图无法验证 reducer 是否正确。

### 多端入口使用同一语义

Web、移动端、客服工作台、IM 和 BI 嵌入页可以长得不同，但核心事件不能各自解释。`run.cancelled` 在所有端都应表示后端已经进入取消状态；审批状态和幂等 key 也必须一致。

事件协议因此需要版本化。字段新增、状态重命名和顺序变化都要有兼容窗口和历史回放样本。**前端事件协议一旦被多端、Trace、Eval 和客服系统消费，它就是平台 API，而不是页面内部实现。**

## 本章小结

企业 Agent UI 展示的是任务，而不只是文本。Conversation、Message 与 Event 应分层建模，SSE 事件需要 `run_id`、`event_id`、`seq` 和 trace，前端通过 reducer 构建稳定消息与工具状态。Runtime 负责真实任务状态，模型文字不能决定完成态；取消、重试、审批和断线恢复都必须有后端语义。对话框可以使用成熟 UI SDK，但消息、工具、权限和 Trace 契约应掌握在平台侧。上线验收也要从成功路径扩展到事件乱序、旧流污染、断线恢复、权限拒绝和多端一致性。**一个生产级 Agent UI 的判断标准，是用户能看懂系统正在做什么，系统也能还原用户当时看到了什么。**

## 参考文献

WHATWG. (n.d.). [Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html).

Vercel. (n.d.). [AI SDK documentation](https://sdk.vercel.ai/docs).

assistant-ui. (n.d.). [Documentation](https://www.assistant-ui.com/docs).

OpenTelemetry. (n.d.). [Documentation](https://opentelemetry.io/docs/).
