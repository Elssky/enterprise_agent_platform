# 第24章 MCP 与企业工具生态

---

MCP 提供统一协议，让模型应用可以发现并调用外部 Tools、Resources 和 Prompts。它显著降低连接外部能力的成本，但**协议统一不等于企业治理完成**：Server 是否可信、谁能调用、工具版本、凭证、网络、审计和失败恢复仍要由企业平台负责。

在本书架构里，MCP 属于 L3 协议接入层；Runtime 和 Tool Registry 仍属于企业自己的运行与治理层。正确路径始终是：发现 MCP 能力 → 映射并登记到 Registry → Runtime 通过 Registry 调用。

**MCP 标准化“怎样连接”，Registry 与 Policy 决定“这个能力能不能进入生产、谁能用、按什么版本用”。MCP 不能替代 Tool Registry。**

## 24.1 Host、Client、Server：先把协议角色和平台角色分开

MCP 定义 Host、Client 和 Server：

- **Host**：承载用户会话、LLM 和上层编排；在企业 Agent 中通常对应应用/Runtime 一侧。
- **Client**：维护与某个 Server 的协议连接，执行 `tools/list`、`tools/call` 等请求。
- **Server**：独立暴露 Tools、Resources 和 Prompts。

*表24-1：MCP 各层组件与 Registry、Runtime 的关系。来源：本书整理。*

| 层次 | 组件 | MCP 相关职责 |
|---|---|---|
| L2 运行时 | Runtime | 发 `action`、通过 Registry `invoke`、记录 `result` |
| L2 运行时 | Tool Registry | 保存 MCP 工具映射后的 ToolSpec、版本和风险元数据 |
| L3 协议 | MCP Client | 连接 Server，处理 `tools/list` / `tools/call` / transport |
| L3 协议 | MCP Server | 暴露 Tools、Resources、Prompts |

这里最重要的边界是：**Run 主循环不直接依赖某个 MCP Server。** Runtime 只认识 Registry 中的平台工具，MCP Client 只是某个 handler 背后的实现方式。这样 Server、SDK 或 transport 升级时，不会把协议细节直接渗入状态机。

MCP Resources 也不能替代 RAG。Resource 更适合“读取已知 URI/资源”，RAG 解决“在大规模知识中搜索哪些证据”。两者可以配合，但权限、索引、引用和检索评测仍属于知识工程层。

## 24.2 Tools、Resources、Prompts：三类能力要按风险分别治理

MCP 的三类原语看起来都能“给模型上下文”，实际风险不同。

*表24-2：MCP 三类能力的企业边界。来源：本书整理。*

| 能力 | 作用 | 企业风险 | 推荐治理 |
|---|---|---|---|
| Tools | 调用外部动作或查询 | 副作用、越权、参数注入 | 登记为 ToolSpec，经 Registry + Policy 执行 |
| Resources | 读取文件、schema、日志、知识等 URI | 敏感数据、上下文膨胀、版本漂移 | ACL、大小限制、来源/版本记录 |
| Prompts | 暴露可复用提示模板 | 提示注入、模板漂移 | 版本化、来源可信度、调用方范围 |

Tools 风险最高，因为可能直接改变系统状态；Resources 虽然“只读”，但仍可能把整库 schema、完整日志或敏感文件送入模型；Prompts 则会影响模型行为，不能因为不执行代码就完全信任。

**来自 MCP Server 的工具描述、资源内容和 Prompt 都应视为外部输入，而不是平台可信配置。第三方 Server 的返回不能直接获得更高信任等级。**

## 24.3 Transport 与部署：本地开发轻，远程生产必须有服务工程

常见 transport 包括 stdio 和 Streamable HTTP。旧版 HTTP+SSE 可作为兼容路径，但新远程部署应优先采用规范当前主流方式。

*表24-3：MCP 传输方式。来源：本书整理。*

| 传输 | 场景 | 关键要求 |
|---|---|---|
| stdio | 本地子进程、IDE、开发工具 | 子进程生命周期、stdin/stdout 阻塞、容器清理 |
| Streamable HTTP | 远程 Server、K8s、多 Host 共享 | TLS、鉴权、连接池、超时、body 限制、网关路由 |
| HTTP+SSE（兼容） | 旧规范遗留端点 | 只作兼容路径 |
| 进程内 | 教学、单测 | 不代表生产 transport |

远程 MCP Server 仍然是服务：要有健康检查、并发控制、超时、熔断、版本发布、容量和 SLO。协议标准并不会自动补上这些能力。

Server 可以采用 sidecar 或共享服务。Sidecar 隔离强、故障半径小，但实例多；共享 Server 运维简单，却需要更严格的多租户、配额和熔断。拆分标准应看数据域、权限、调用频率和事故影响，而不是代码目录。

网络边界还要控制返回体。长报表、日志或大文件不应直接塞进 Tool Result 和模型上下文；应返回摘要 + `artifact_ref/resource_uri`，原始对象进入受权限控制的存储。

## 24.4 MCP → Registry：发现、映射、注册、执行

生产集成建议固定五步：

1. **发现**：Client 调 `tools/list` 获取 Server 能力；
2. **映射**：生成企业唯一命名，避免多个 Server 同名；
3. **注册**：把 `inputSchema`、描述、来源、风险和 handler 映射成 ToolSpec；
4. **健康检查**：周期检查 Server/工具版本，异常时从 Planner 工具视图摘除；
5. **执行**：Runtime → Registry `invoke` → handler → MCP Client → Server。

![图24-1：MCP → Registry 桥接闭环](../../images/part5/ch/p5-05-mcp-registry-bridge.png)

*图24-1：MCP → Registry 桥接闭环。来源：本书自绘。Alt text：外部 MCP Server 暴露的工具先经企业 Registry 登记、打风险等级、加权限策略，再供 Runtime 调用，调用结果回流审计，箭头构成接入到治理的闭环。*

一个 Server 工具可能叫 `query_sales`，平台可映射为 `mcp_db_query_sales@v1`。Run 只 pin 平台版本，不直接依赖 Server 临时返回的 schema。

**MCP 发现结果不能自动进入 Planner。发现是候选能力，注册和准入才决定它是否成为生产工具。**

版本变化要分三层追踪：

- `server_version`：能力提供方发布了什么；
- `tool_spec_version`：企业平台登记了什么契约；
- `registry_version/visibility`：某个 Agent 实际可见什么。

这样 Server 侧升级时，企业可以影子测试、灰度新 ToolSpec，并在必要时只回滚 Registry 可见版本，而不是要求外部团队立刻撤代码。

## 24.5 安全边界：身份、凭证、数据驻留和供应链都不能交给协议

MCP 本身不是企业 IAM。生产接入至少需要：

- Host → Client → Server 的调用身份可传播；
- 使用短期服务身份/密钥系统，不给 Server 长期高权限凭证；
- 网络访问使用 allowlist、TLS/mTLS、出站控制；
- `tenant_id`、用户、`run_id`、`tool_call_id` 进入结构化审计；
- 日志中的参数和结果按 PII/密级脱敏；
- 外部 Server 做代码、依赖、网络和供应链审查；
- Server 只持有最小能力，不把只读查询和高风险写操作塞进同一宽权限实例。

数据驻留不能只看最终结果。Client 日志、Server 错误堆栈、trace 样本都可能包含 SQL 条件、客户 ID 或资源 URI，同样要纳入区域和合规策略。

Resources 的 ACL 也必须显式。模型“读取上下文”本身就是数据访问，不能因为没有 Tool Call 副作用就绕过授权。

**MCP 最大的安全误区，是把“开放协议”误解为“可信生态”。协议只定义消息，信任仍需企业自己建立。**

## 24.6 错误与降级：不要把所有 MCP 故障包装成 `tool failed`

至少要区分四类失败：

*表24-4：MCP 错误分类与恢复。来源：本书整理。*

| 类型 | 示例 | 推荐动作 |
|---|---|---|
| 连接失败 | Server 不可达、网关超时、连接池耗尽 | 有界重试、副本切换、熔断 |
| 协议失败 | JSON-RPC/返回结构错误、schema 不兼容 | 摘除版本、告警，不让 Planner反复尝试 |
| 业务失败 | 查询为空、文件不存在、后端业务错误 | 保留业务错误给 Planner 判断 |
| 策略失败 | 租户不匹配、scope 不足、风险禁止 | 直接拒绝或进入 HITL，不能绕行 |

对用户的降级也要确定：只读查询 Server 暂不可用时可以提示稍后重试；Resource 不可读时可基于缓存证据回答但明确不完整；高风险写工具失败时不能偷偷切另一条写路径。

Server 返回错误码应映射成平台统一错误分类，使 Runtime 能决定 retry、replan、fail 或 human review，而不是让模型从自然语言错误里猜。

## 24.7 mini-platform 与准入生命周期

mini-platform 中 MCP 示例验证的是“协议工具先进入 Registry，再进入 RunLoop”：

```text
mini-platform/tools/mcp_db/
├── server.py
├── client.py
└── registry_bridge.py

projects/multi-agent-workflow/lib/
└── registry_setup.py

tests/test_mcp_db.py
```

```bash
cd mini-platform
python3 projects/multi-agent-workflow/run.py start
pytest tests/test_mcp_db.py -q
```

示例没有覆盖生产所需的远程 TLS、短期令牌、连接池、健康检查、自动摘除和完整 Resources/Prompts，因此不能把单测通过等同于 Server 已具备生产资格。

生产 MCP Server 应经过：候选 → 静态审查 → 影子调用 → 小流量 → active → 周期复审 → deprecated/disabled。复审重点看：owner 是否仍存在、schema 是否和 Registry 一致、凭证是否轮换、依赖/供应链是否安全、网络范围是否变化、错误是否还能映射到 Runtime 恢复策略。

长期无人使用或无人维护的 Server 应退出目录；历史 Trace 仍保留其版本和调用证据。**开放工具生态要靠稳定的准入与退出机制维持质量，否则“接得快”最终会变成大量无人负责的影子集成。**

## 本章小结

MCP 解决外部工具、资源和 Prompt 的协议互通，不能替代企业 Tool Registry、Policy、IAM 和 Trace。Runtime 应只通过 Registry 调用生产 MCP 工具，Server/Client 的变化不能直接改变 Run 状态机。

生产接入必须治理 transport、身份、凭证、数据驻留、供应链、版本和错误分类。第三方 Server 的描述和返回都应作为不可信输入处理，并通过影子测试和灰度进入平台。

**MCP 的价值是让工具供应更丰富；企业平台的责任，是让这些能力进入同一套命名、权限、版本、审计和恢复规则。**

## 参考文献

Anthropic. (2024). *Model Context Protocol*.

Model Context Protocol. (2024–2025). *Specification*.

Google. (2024–2025). *Agent2Agent Protocol*.
