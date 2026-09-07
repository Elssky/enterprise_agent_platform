# 第23章 Tool Registry & Function Calling

---

工具是 Agent 从“生成内容”进入“改变业务状态”的出口。模型生成一个函数名和 JSON 参数，并不意味着这个动作已经安全可执行；平台还必须判断工具是否存在、应该使用哪个版本、参数是否合法、用户是否有权限、副作用能否重试，以及执行结果如何被审计。

Function Calling 和 Tool Registry 解决的是两层问题：前者让模型结构化表达“想调用什么”，后者把企业工具变成可发现、可版本化、可授权、可执行的平台注册资产。

**Function Calling 是模型侧调用意图，Tool Registry 是企业侧执行契约。模型可以提出工具调用，但不能决定某个函数因此获得执行权。**

## 23.1 Registry 的位置：注册在管控面，调用在运行时

第22章的 Runtime 负责推进 Run，第25章的 Planner 负责选择下一步。Registry 位于二者之间：L1 管控面负责注册和发布工具，L2 Runtime 只按已发布版本 `get/invoke`。

![图23-1：Registry 分层架构](../../images/part5/ch/p5-03-registry-architecture.png)

*图23-1：Registry 分层架构。来源：本书自绘。Alt text：分层图含 ToolSpec 注册层、检索/版本层、权限策略层、调用执行层，Runtime 通过 Registry 接口调用工具，体现工具注册到调用的分层结构。* 图中虚线表示：Planner 不执行工具，只读取 Registry 导出的 OpenAI `tools` 定义或等价 schema；MCP 工具需要先注册为 ToolSpec，Runtime 后续仍按 `action` → `invoke` → `result` 流程执行（第24章展开）。

*表23-1：Registry 与相邻组件的职责边界。来源：本书整理。*

| 组件 | Registry 做什么 | 不做什么 |
|---|---|---|
| Runtime | 提供 `get/invoke` | 不驱动 Run 状态、不发 SSE |
| Planner | 提供当前可见工具 schema | 不替模型选择下一步 |
| Policy | 提供工具风险、权限元数据 | 不替代最终授权判断 |
| LLM Gateway | 导出 tools schema | 不直接执行 handler |
| MCP | 登记 MCP 工具映射 | 不承担 JSON-RPC 传输 |

没有平台级 Registry 时，每个 Agent 会自己 import 工具、自己写鉴权与重试，最终形成多个行为不一致的执行入口。**Registry 的核心作用是把工具“收口”：同一个业务动作只有一个可治理入口，工具发现、版本、schema 和审计使用同一份事实。**

注册面和调用面必须分开。Run 主循环不应临时注册工具，也不应根据模型输出动态 import 任意函数。工具在进入生产候选集前已经完成发布和治理；Runtime 只消费这个已批准目录。

## 23.2 ToolSpec：把能力、参数、风险和责任写成资产

最小 ToolSpec 不应只有函数名和参数。企业工具至少需要：

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    parameters_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    risk_level: str
    permissions: tuple[str, ...]
    idempotency: str
    timeout_seconds: int
    owner: str
    handler: Callable[..., Any]
```

*表23-2：ToolSpec 关键字段。来源：本书整理。*

| 字段 | 作用 | 生产要求 |
|---|---|---|
| `name` | 稳定能力名 | 不随实现位置变化 |
| `version` | 固定执行契约 | Run 必须 pin 实际版本 |
| `description` | 给模型和人解释用途 | 明确适用/禁止场景和副作用 |
| `parameters_schema` | 输入结构 | 调用前强制校验 |
| `output_schema` | 返回结构 | 便于 Planner 稳定消费 |
| `risk_level` | 动作风险 | 驱动 Policy/HITL |
| `permissions` | 最小权限声明 | 与用户/租户 scope 联合判断 |
| `idempotency` | 重复执行语义 | 写操作必须显式定义 |
| `timeout_seconds` | 单次执行预算 | 防止工具无限占用 Run |
| `owner` | 责任团队 | 发布、事故、下线均可追责 |

工具描述会直接影响模型选择，因此不能写成宽泛的“查询数据”“发送消息”。更好的描述应明确边界，例如：“只读查询销售汇总；不返回手机号；不执行写入；必须提供 tenant_id”。自然语言不能代替 Policy，但可以减少 Planner 误选。

**ToolSpec 是业务能力的接口契约，不是 Python 函数的注释。实现可以从本地函数迁到 HTTP/MCP，而 `name/version/schema/risk` 应保持可治理。**

## 23.3 Function Calling：结构化输出仍必须二次校验

模型 tools API 通常用 JSON Schema 描述参数，模型返回工具名和 arguments。这个输出仍然属于不可信输入。

典型链路是：

```text
Registry exports allowed ToolSpecs
        ↓
Planner/Gateway sends tools schema to model
        ↓
model proposes tool + arguments
        ↓
Runtime validates Policy + schema + version
        ↓
Registry.invoke(...)
        ↓
Tool Result → Runtime → Planner
```

模型返回了合法 JSON，也可能存在以下问题：

- `tenant_id` 与当前用户上下文不一致；
- 数值类型合法，但退款金额超过权限阈值；
- 工具版本已经下线；
- 参数会导致过大扫描或敏感数据导出；
- 同一副作用此前已经执行过。

因此至少要做两类校验：**结构校验**由 Registry/schema 完成，**授权和业务风险校验**由 Policy/业务规则完成。

对于模型支持的 strict structured tools，可以减少格式错误，但不能跳过企业校验。**“符合 schema”只说明参数长得像合法请求，不说明调用者有权做这件事。**

## 23.4 版本、发现与 Planner 工具视图

工具版本不能在生产中静默覆盖。`register(name=v1)` 后再次发布不兼容接口，应登记 `v2`；已有 Agent/Run 继续 pin `v1`，新版本先进入灰度。

*表23-3：Registry 核心操作。来源：本书整理。*

| 操作 | 作用 |
|---|---|
| `register(spec)` | 新增 `(name, version)`；禁止静默覆盖 |
| `get(name, version)` | 精确解析指定版本 |
| `list_versions(name)` | 查看全部版本与状态 |
| `list_allowed(context)` | 按租户、角色、Agent、环境过滤可见工具 |
| `disable(name, version)` | 停止新 Run 选择，但保留历史解释 |

Planner 看到的工具列表不应是整个 Registry。每一轮应根据用户身份、租户、Agent 配置、Run 状态、风险等级和环境计算最小工具视图。例如：

- 规划阶段可见只读查询；
- `waiting_human` 前不得暴露发布动作；
- 没有财务 scope 的用户根本看不到财务写工具；
- 测试工具不进入生产 Planner 上下文。

**“不给模型看见不该调用的工具”比在 Prompt 里反复要求“不要调用”更可靠，也能减少工具选择噪声。**

工具视图应进入 Trace：当时模型看到了哪些 `name@version`，为什么某个工具不可见。否则线上问题很难判断是 Planner 选错，还是工具目录本身给错了候选。

## 23.5 副作用、幂等与错误：工具安全取决于执行语义

写操作必须显式描述幂等和副作用。读取销售汇总可以安全重试，发送邮件、退款、修改主数据则不能简单重复。

*表23-4：工具副作用与推荐控制。来源：本书整理。*

| 类型 | 示例 | 控制方式 |
|---|---|---|
| 纯只读 | 查询指标、读取文档 | 有界重试、缓存 |
| 可重复写 | 保存草稿、创建临时 artifact | 稳定幂等键、可撤销 |
| 单次副作用 | 发邮件、提交工单、退款 | 幂等键 + 状态查询 + HITL/Policy |
| 高风险不可逆 | 删除关键数据、付款 | 默认人工审批或禁止自动执行 |

Registry/Runtime 需要返回结构化错误，而不是字符串：

```json
{
  "code": "TOOL_ARGUMENT_INVALID",
  "retryable": false,
  "tool": "sql_executor",
  "version": "v1",
  "details": {
    "field": "tenant_id"
  }
}
```

常见分类至少包括：`TOOL_NOT_FOUND`、`TOOL_ARGUMENT_INVALID`、`POLICY_DENIED`、`TOOL_UNAVAILABLE`、`TOOL_TIMEOUT`、`TOOL_BUSINESS_ERROR`、`TOOL_DUPLICATE_REQUEST`。

错误分类决定恢复路径：参数错可让 Planner 修正；网络暂时不可用可有界重试；权限拒绝不能让模型换参数继续试；副作用状态不确定时先查外部状态，而不是直接重复执行。

**工具系统最重要的“智能”不是自动重试，而是知道哪些失败绝不能重试。**

## 23.6 工具生命周期：上架、灰度、健康检查、下线

工具进入 Registry 之后仍要持续运营。一个完整生命周期可以压缩成：

`draft → test → canary → active → deprecated → disabled`

生产发布至少检查：

- schema 与实现一致；
- ToolSpec owner、risk、permission 完整；
- 正常/异常/权限/超时样本通过；
- 幂等策略有测试；
- 旧版与新版行为差异可解释；
- 健康检查和告警已接入；
- 回滚目标明确。

版本下线不能直接删除。历史 Run 需要知道当时调用了什么版本；新 Run 则停止选择该工具。工具别名、deprecated 提示和迁移窗口可以降低业务升级成本。

健康状态也应该影响 Planner 工具视图。某个 MCP/HTTP 后端持续失败时，可以临时标记 unavailable，使新 Planner 不再选择，而不是让每个 Run 都重复撞故障。

工具资产还要防止“无人负责”。调用量长期为零、owner 失效、schema 多次漂移或安全风险未修复时，应进入复审和退出流程。**工具目录的质量取决于能否持续清理无效能力，而不是条目越多越好。**

## 23.7 mini-platform：统一 `register → invoke → trace`

mini-platform 中 Tool Registry 的最小实现应验证同一条主线：工具先注册，再由 Runtime 统一调用。

```text
mini-platform/core/registry/
├── tool_registry.py
└── errors.py

mini-platform/tools/
└── ...

tests/
├── test_registry.py
└── test_mcp_db.py
```

最小示例：

```python
registry.register(
    ToolSpec(
        name="sql_executor",
        version="v1",
        description="只读查询授权销售指标",
        parameters_schema={...},
        output_schema={...},
        risk_level="read_only",
        permissions=("sales:read",),
        idempotency="safe_retry",
        timeout_seconds=30,
        owner="data-platform",
        handler=query_sales,
    )
)

result = registry.invoke(
    "sql_executor",
    "v1",
    {"tenant_id": "demo-retail", "region": "华东"},
)
```

生产链路还应记录：`run_id`、`step_index`、`tool_call_id`、`name@version`、args 摘要、Policy 结果、幂等键、开始/结束时间、结果引用和错误类型。

## 本章小结

Function Calling 让模型结构化表达工具调用意图，Tool Registry 则负责把企业工具变成版本化、可校验、可治理的执行契约。两者必须通过 Runtime 汇合，而不是让模型直接执行函数。

ToolSpec 应包含 schema 之外的风险、权限、幂等、超时和 Owner；Planner 每轮只看到当前身份和状态允许的最小工具视图；写操作必须明确副作用和重试语义。

**一个企业工具是否成熟，不看“模型能不能调通”，而看任何一次调用能否说明：调用了哪个版本、为什么有权调用、参数如何校验、是否产生副作用，以及失败后还能不能安全恢复。**

## 参考文献

OpenAI. (n.d.). *Function calling / Structured Outputs documentation*.

Li, et al. (2025). *Tool Learning with Large Language Models: A Survey*.

Qu, et al. (2025). *Tool Learning with Foundation Models*.
