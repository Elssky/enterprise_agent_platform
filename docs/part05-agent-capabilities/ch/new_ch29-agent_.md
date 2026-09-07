# 第29章 Agent 协议与标准

---

企业 Agent 平台不会只连接一种能力。工具可能通过 MCP 暴露，外部供应商可能提供完整 Agent，桌面端或合作伙伴系统还可能有自己的消息协议。问题不是“哪个协议会赢”，而是这些外部能力进入企业后，是否仍然服从同一套身份、权限、版本、审计和恢复规则。

以经营分析为例：内部 Data Agent 通过 MCP 查询销售，外部舆情服务以 A2A Agent 形式返回分析结果，最终 Report Agent 把两类证据汇总。协议可以不同，但 Runtime 仍然只管理一条 `run_id`；外部工具和 Agent 也不能因为支持“标准协议”就绕过 Registry 和 Policy。

**协议降低的是连接成本，不是治理成本。任何外部能力进入生产前，都要被翻译成企业内部可版本化、可授权、可审计的对象。**

## 29.1 协议版图：先区分“连接的对象是什么”

![图29-1：L3 协议版图](../../images/part5/ch/p5-09-l3-protocol-landscape.png)

*图29-1：L3 协议版图。来源：本书自绘。Alt text：分层版图把 MCP、A2A、Agent Card、内部 Registry 按职责层叠放置，箭头标出它们的衔接点。*

*表29-1：主要协议与平台映射。来源：本书整理。*

| 协议/机制 | 主要对象 | 典型用途 | 企业平台落点 |
|---|---|---|---|
| MCP | Tools、Resources、Prompts | SQL、文件、SaaS、桌面工具 | ToolSpec / Resource adapter |
| A2A | 远程 Agent / 长任务 | 委托供应商或跨组织 Agent | External AgentSpec / Handoff |
| Agent Card | Agent 元数据 | endpoint、skills、auth、能力发现 | L1 Agent Catalog |
| ACP / 事件协议 | 持续消息、协作事件 | 多方协作、事件广播 | Event Bus adapter |
| 模型 tools API | 模型函数调用意图 | Function Calling | Registry 导出工具 schema |

协议选型先看协作对象。数据库查询不必包装成远程 Agent；一个会持续半小时、返回多个 artifact 的法律审查服务，也不适合被伪装成普通函数调用。

**MCP 解决工具/资源互通，A2A 解决 Agent 委托，Agent Card 解决能力发现，事件协议解决持续协作。它们不是同一个问题的不同品牌。**

## 29.2 MCP：工具协议仍然要收敛到 Registry

第24章已经给出主链路：

```text
MCP Server
  → tools/list snapshot
  → enterprise ToolSpec
  → Registry
  → Runtime action/invoke/result
  → MCP Client tools/call
```

Runtime 不直接 import MCP Client。这样 stdio/HTTP、SDK、Server 地址或协议版本变化时，只影响适配层，不改变 Run 状态机。

协议适配器还要保留两份事实：

1. 外部 Server 当时原始声明的 tool schema；
2. 企业治理后真正暴露给 Planner 的 ToolSpec。

二者不一定相同。企业可能屏蔽某些参数、缩小描述、限制租户、提高风险等级。事故发生时，必须能判断是远端声明发生了变化，还是内部映射错误。

同一能力也可能同时通过 MCP、HTTP 和供应商 tools API 暴露。Catalog 应把它们归到一个业务能力资产下，指定首选/备用入口，防止 Planner 看到三个名字却实际触发同一副作用。

## 29.3 A2A 与 Agent Card：远程 Agent 是一项可跟踪委托，不是一个 HTTP 黑盒

A2A 更适合有状态、长时、可能返回 artifact 的远程任务。平台把任务委托给外部 Agent 时，外层 Run 不消失；A2A Task 只是其中一个异步 Tool Call / Handoff。

*表29-2：A2A Task 与平台 Run 的映射。来源：本书整理。*

| A2A 概念 | 平台映射 | 关键记录 |
|---|---|---|
| Task | 外部 Tool Call / Handoff | `external_task_id` |
| Message | 出站 payload / 返回消息 | Policy 脱敏结果 |
| Task state | Tool/Run 子状态 | 超时、取消、等待输入 |
| Artifact | 结果引用 | hash、来源、版本、密级 |

Agent Card 用于发现，不代表授权。Card 可以声明名称、skills、endpoint 和认证方式，但企业导入后仍应生成内部 AgentSpec，并做：schema 校验、SSRF/URL 防护、认证审查、租户范围、风险等级、owner 和版本固定。

Card 的原文和解析后的 AgentSpec 都应保留。供应商新增一个 `send_report` skill，绝不能因为 Card 自动刷新就直接进入 Planner 候选；新增能力必须重新准入。

**“远端声明自己会什么”只是能力发现，“本地平台允许它做什么”才是生产权限。**

外部任务还必须传播取消语义。用户取消本地 Run 后，平台应尽力取消远端 Task；无法取消时至少标记 orphan、保留 external task id，并决定后续 artifact 如何处理。

## 29.4 事件与 ACP：事件表示发生了什么，不能直接等同执行命令

持续协作常需要事件流，例如报告生成后通知品牌、法务和 Reviewer。企业通常已经有内部 Event Bus，ACP 或其他消息协议更适合作为边界适配，而不是直接成为 Runtime 工具执行入口。

要区分：

```text
report.ready        # 事件：某事已经发生
publish_report(...) # 命令：要求执行副作用
```

外部事件进入平台后，要先校验签名、租户、幂等键、事件时间和 payload schema，再由 Runtime/Workflow 决定是否创建或推进 Run。**消息到达不能自动等于拥有执行权限。**

对于有副作用的后续动作，仍然回到 Registry + Policy。

## 29.5 多协议组合：统一的是内部运行模型

一次任务可能同时用到 MCP 与 A2A：

![图29-2：MCP + A2A 组合时序](../../images/part5/ch/p5-10-mcp-a2a-combo-sequence.png)

*图29-2：MCP + A2A 组合时序。来源：本书自绘。Alt text：时序图展示一个 Agent 经 A2A 接收外部任务，内部再用 MCP 调用工具完成，结果沿 A2A 返回。*

组合时要把每层版本和证据固定下来：

- MCP tool / ToolSpec version；
- Agent Card version / etag；
- A2A endpoint 与 task id；
- adapter version；
- semantic layer version；
- artifact hash；
- 出站 Policy 决策。

否则同一个历史 Run 在未来回放时会依赖“远端现在是什么样”，而不是“当时是什么样”。

协议组合还会触发数据出域问题。内部 MCP 查到的客户明细，不能因为下一步是标准 A2A 调用就直接发送给外部 Agent。Policy 应根据数据密级、租户、合同范围和脱敏状态决定：允许、聚合后发送、只发送引用，或拒绝。

**跨协议任务真正需要统一的是身份链、权限链、版本链和 Trace，而不是把所有外部系统强行改成同一个协议。**

## 29.6 错误、部分成功与降级：协议层要翻译真实世界的不确定状态

外部协议最难处理的不是“完全不可用”，而是部分成功：

- MCP 写操作已提交，但网络响应超时；
- A2A Agent 已生成 artifact，但回调丢失；
- Card 仍可访问，但某个 skill 已被下线；
- 事件已被消费，但 ack 未返回。

适配器应把这些情况转换成稳定内部状态，而不是统一抛 `external_error`。

*表29-3：外部协议错误与恢复。来源：本书整理。*

| 类型 | 示例 | 推荐动作 |
|---|---|---|
| Transport | 超时、DNS、TLS | 有界重试/熔断 |
| Auth/Policy | 凭证失效、scope 不足 | 停止，刷新身份或转人工 |
| Contract | schema、状态枚举不兼容 | 冻结能力，禁止自动重试 |
| Remote business | 对方拒绝、结果为空 | 保留结构化原因给 Planner |
| State uncertain | 写入可能已发生 | 查询远端 task/idempotency state，再决定 |

替代路径也不能由模型随意寻找。远端高风险 Agent 不可用时，不能自动切换到另一个“描述相似但权限更宽”的供应商。备用能力同样要预先进入 Catalog 和 Policy。

## 29.7 准入、测试与退出：标准协议也需要生命周期

协议能力进入生产前，应经过准入沙箱。建议至少覆盖：

1. 正常只读/长任务；
2. 权限拒绝和不支持能力；
3. 超时、取消和重试；
4. schema/Card 变化；
5. 重复请求/重复事件；
6. 超大 artifact；
7. 数据出站和脱敏；
8. 远端部分成功。

协议 adapter 尽量做成无 LLM 可测试组件。MCP 用 fixture tool list，A2A 模拟 task lifecycle，Agent Card 用固定 JSON，Event adapter 测签名和幂等。这样外部协议变化时，平台可以在 CI/影子环境提前发现。

生产目录中的能力还要有 owner、版本、认证、数据域、健康状态、最近回归结果和退出条件。长期失败、无人维护、供应商合同变化或安全事件，应从 Planner 候选中 disable；历史 Run 仍保留快照和证据。

**协议支持不是一次“接通”动作，而是持续的版本和供应商依赖管理。**

## 29.8 mini-platform：协议变化停在 L3，Runtime 契约保持稳定

当前 mini-platform 可以把协议适配层理解为：

```text
mini-platform/core/protocol/
└── adapter.py

mini-platform/tools/mcp_db/
└── registry_bridge.py
```

依赖方向应固定：

```text
protocol adapter → Registry
Runtime → Registry
Runtime ✕ protocol client
```

生产扩展可以依次补：MCP 快照和健康检查 → Agent Card 导入 → A2A 异步 Task → 外部 Event adapter。每一步都要求最终输出能映射回 ToolSpec / AgentSpec / Run event / Artifact。

协议升级也要版本化适配器。旧 Run 记录当时使用的协议/adapter 快照，新版本先做兼容回放和灰度。不能因为外部 SDK 升级，就让历史事件含义随之改变。

## 本章小结

MCP、A2A、Agent Card 和事件协议针对的是不同互操作对象。企业平台不需要押注单一协议，但必须让所有外部能力落到稳定的内部对象：ToolSpec、AgentSpec、Run、Handoff、Artifact 和 Trace。

协议适配层负责连接、版本和错误翻译；Registry/Policy 负责能力准入与执行权限；Runtime 负责任务状态。外部声明永远不能自动升级为内部权限。

**企业 Agent 互操作的成熟度，不在“支持多少协议”，而在跨协议之后是否仍能回答：谁发起、谁授权、哪一版能力被调用、真实副作用是否发生，以及失败后还能否安全恢复。**

## 参考文献

Model Context Protocol. (2024–2025). *Specification*.

Anthropic. (2024). *Introducing the Model Context Protocol*.

Google. (2025). *Agent2Agent (A2A) Protocol*.

IBM. (2025). *Agent Communication Protocol (ACP)*.

OpenAI. (n.d.). *Function calling*.

Anthropic. (n.d.). *MCP SDK*.

Google. (n.d.). *A2A SDK*.

Wu, Q., et al. (2024). *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation*.
