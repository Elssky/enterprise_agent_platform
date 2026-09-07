# 第25章 Planner 与编排模式

---

Planner 决定“下一步应该做什么”，Runtime 决定“这个动作能不能执行以及任务如何推进”。这两个职责必须分开。模型越擅长规划，越不能让它顺手承担工具执行、状态迁移和权限判断，否则一次推理错误会直接变成系统副作用。

**Planner 是决策器，不是执行器。它输出下一步建议，Runtime 才拥有状态机和工具执行权。**

## 25.1 Planner 的最小接口：输入足够，输出要小

Planner 需要看到用户任务、当前状态、可用工具、必要上下文、历史观察和预算，但不应直接获得所有系统能力。输入应由 Runtime/Registry 按当前身份和状态裁剪。

一个最小 Planner 输出可以只有：

```json
{
  "decision": "tool_call",
  "tool": "sql_executor",
  "version": "v1",
  "arguments": {"metric": "gmv", "region": "east"},
  "reason_summary": "需要先获得华东区 GMV 基线",
  "confidence": 0.86
}
```

其他合法决策可以是 `finish`、`clarify`、`handoff`、`request_human`。Planner 不直接调用 handler，也不修改 Run 状态。

**Planner 输出越接近一个小型、稳定的决策协议，Runtime 越容易验证、回放和替换实现。**

## 25.2 ReAct：边观察边决定，适合路径难以预先写死的任务

ReAct 把推理、行动和观察交错进行。它适合问题需要根据工具结果动态调整路径的场景，例如先查销售，再根据异常结果决定是否查库存或价格。

优点是灵活，缺点也很明确：工具选择可能反复、路径长度难预测、成本更难控制。生产实现必须配套：

- `max_steps`、LLM/Tool Call budget；
- 重复工具 + 相同参数检测；
- 状态相关工具白名单；
- 结构化错误反馈；
- 结束和澄清条件。

Planner 不应因为某次工具失败就无限“再想一种方式”。权限拒绝、不可恢复系统错误和预算耗尽需要 Runtime/Policy 明确终止。

## 25.3 Plan-and-Execute：先冻结关键计划，再逐步执行

Plan-and-Execute 先形成多步计划，再由 Runtime 执行；中间条件变化时可触发 replan。它更适合高风险、长链路或希望执行前审计的任务。

![图25-1：Plan-and-Execute 流程](../../images/part5/ch/p5-06-plan-and-execute.png)

*图25-1：Plan-and-Execute 流程。来源：本书自绘。Alt text：流程先由 Planner 生成多步计划，再逐步执行；遇到错误或前提不成立时回到重规划，箭头展示先规划后执行和 ReAct 边想边做的区别。*

*表25-1：ReAct 与 Plan-and-Execute 的取舍。来源：本书整理。*

| 模式 | 优势 | 风险 | 更适合 |
|---|---|---|---|
| ReAct | 灵活、能根据观察实时调整 | 循环、成本和路径难预测 | 调研、诊断、低风险探索 |
| Plan-and-Execute | 可提前检查计划、路径更易解释 | 初始计划可能失效 | 长任务、高风险、多阶段执行 |
| 固定 Workflow | 行为最稳定 | 灵活性低 | 强合规、路径确定任务 |

高风险任务可以采用“计划冻结”：审批人先看到拟执行动作、工具和影响范围，批准后只允许执行已批准计划；如果后续 replan 引入新的高风险动作，必须重新审批。

**计划可审计，不等于计划不可变化。关键是任何改变执行责任的计划变化都要重新进入验证。**

## 25.4 状态图：是 Planner 内部实现，不是 Runtime 外部状态机

LangGraph 或自研 state graph 可以表达 `select_table → generate_sql → execute → reflect → revise` 等内部节点。它们属于 Planner/Workflow 的实现细节。

对外仍应折叠成第22章的 Run 六态：

- 内部生成/选择 → `planning`；
- 工具执行 → `executing`；
- 需要人工 → `waiting_human`；
- 结束 → Runtime 验证后进入终态。

这样 Planner 实现可以从 ReAct 换成图、从单模型换成多模型，而前端、SLO、HITL 和审计契约不需要一起重写。

## 25.5 工具视图、业务策略与停止条件

Planner 每轮只能看到 Registry/Policy 计算出的最小工具视图。没有权限的工具不应该靠 Prompt 禁止，而应该根本不进入候选。

业务策略也不应埋进 Planner Prompt。折扣阈值、数据导出范围、必须审批的动作、禁止访问的字段，都应由 Policy 或结构化配置维护。Planner 可以读取策略结果，但不能通过改写自然语言绕过它。

成熟 Planner 还必须知道什么时候不该继续：

- 输入关键字段不足 → `clarify`；
- 必要证据不存在 → `finish/insufficient_evidence`；
- 权限不足 → 停止或请求合法审批；
- 连续重复路径 → 终止/转人工；
- 成本或时间预算耗尽 → 停止；
- 高风险动作超出当前授权 → `request_human`。

**“知道什么时候停”与“会选择工具”同样是 Planner 的核心能力。**

## 25.6 Planner 评测：最终答案正确不代表路径正确

只看最终答案，会掩盖大量不可接受的路径：调用了多余工具、尝试越权、重复扫描数据、先写后撤、成本高出十倍。

Planner 评测应同时覆盖：

*表25-2：Planner 评测维度。来源：本书整理。*

| 维度 | 示例指标 |
|---|---|
| 工具选择 | 正确工具率、非法工具尝试率 |
| 路径质量 | 平均 Step、冗余调用、重规划次数 |
| 停止能力 | 无证据拒答、澄清正确率、循环率 |
| 风险行为 | Policy denied 次数、高风险未审批尝试 |
| 结果质量 | 任务完成率、业务正确率 |
| 资源消耗 | token、Tool Call、时间、成本 |

回放样本要保存 Planner 版本、Prompt/config、当时可见 ToolSpec、模型版本和关键观察。否则升级后无法判断行为变化来自模型、工具目录还是 Planner 策略。

## 25.7 mini-platform：Planner 可替换，Runtime 契约不变

mini-platform 中 Planner 应以小接口挂到 RunLoop：

```python
class Planner(Protocol):
    def next_step(self, context: PlannerContext) -> PlannerDecision:
        ...
```

同一测试集可以替换 ReAct、Plan-and-Execute 或图式 Planner，只要输出同一 `PlannerDecision`。这使模型和编排框架成为可替换模块，而不成为平台状态机的事实来源。

生产发布时，Planner 版本最好绑定：

`planner_mode + prompt/config + model + tool_view_policy + eval_set`

新版本先做离线回放和 shadow run，再按 Agent/租户灰度。出现循环、工具误选或成本异常时，只回滚 Planner 组合，不必回滚整个 Runtime。

## 本章小结

Planner 负责提出下一步决策，Runtime 负责执行和状态迁移。ReAct 适合动态探索，Plan-and-Execute 更适合需要预审计划的长任务和高风险路径，固定 Workflow 则适合确定性强的流程。

Planner 应使用最小工具视图，业务风险规则放在 Policy 而非 Prompt；评测不能只看最终答案，还要看路径、停止、风险和成本。

**企业级 Planner 的成熟度，不是“计划看起来多聪明”，而是它的每个建议都能被验证、受预算约束，并且在证据不足或权限不满足时主动停止。**

## 参考文献

Yao, S. et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR.

LangGraph. (n.d.). *Documentation*.
