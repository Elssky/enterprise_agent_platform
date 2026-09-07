# 第22章 Agent Runtime

---

Agent Runtime 定义企业 Agent 的执行契约。一次经营分析可能经历多轮规划、SQL 查询、结果校验、报告生成和人工审批；用户关掉页面、服务重启、工具超时后，任务仍要能够回到同一个 `run_id` 继续。

聊天后端关心“下一条消息是什么”，Runtime 关心的是另一组问题：任务当前处于什么状态，哪些动作已经执行，下一步由谁负责，失败后从哪里恢复，以及整条链路能否被审计。

**Runtime 的核心价值，是把模型的不确定决策转换成可暂停、可恢复、可审计的任务执行。Planner 可以建议下一步，但 Run 的状态迁移和真实副作用必须由 Runtime 掌握。**

## 22.1 Run、Step 与 Tool Call：把任务、决策和副作用分开

企业 Agent 最容易出错的做法，是把会话、推理轮次和工具执行混成一个对象。更稳妥的对象模型至少包含 Run、Step 和 Tool Call。

*表22-1：Run、Step 与 Tool Call 的职责边界。来源：本书整理。*

| 对象 | 代表什么 | 主要字段 | 典型用途 |
|---|---|---|---|
| Run | 一次可审计任务 | `run_id`, `agent_id`, `input`, `context`, `state` | SLA、检查点、审批、审计 |
| Step | Planner 的一轮决策 | `run_id`, `step_index`, `planner_output` | 组织多轮规划和工具反馈 |
| Tool Call | 一次实际工具执行 | `tool_call_id`, `tool`, `args`, `status`, `output` | 回放、幂等、错误分类 |

一次 Run 可以包含多轮 Step，一轮 Step 可以产生零次、一次或多次 Tool Call。Planner 只提出调用意图，工具必须由 Runtime 通过 Registry 执行。

一次 `/run` 请求应生成稳定任务身份：

```json
{
  "input": "上周华东区销售下滑的主要 SKU 是什么？",
  "context": {
    "user_id": "u-ops-001",
    "tenant_id": "demo-retail",
    "scope": ["sales_region:east"]
  },
  "options": {
    "idempotency_key": "optional-client-key",
    "max_steps": 20
  }
}
```

`context` 必须原样进入 Policy 和工具层；`idempotency_key` 用于客户端重试时避免重复创建工单、发送邮件或写数据库；`max_steps` 则给 Planner 循环设置硬边界。

*表22-2：Runtime 与相邻组件的分工。来源：本书整理。*

| 组件 | Runtime 做什么 | 组件自身负责什么 |
|---|---|---|
| Planner | 调用 `next_step()` 并接收结构化决策 | 选择下一步，不直接执行工具 |
| Tool Registry | 按工具名和版本查 handler | 管理 schema、版本、风险元数据 |
| Policy | 在受控动作前请求裁决 | 鉴权、风险和审批策略 |
| Memory | 读取/写入当前任务需要的上下文 | 长短期记忆与组织上下文 |
| Console | 推送状态、事件与审批待办 | 展示进度并接收人工回调 |

**Runtime 平台化的意义，是让不同 Agent 共享同一套状态、错误、恢复和审计语义，而不是每个应用自己发明执行循环。**

## 22.2 Run 六态：内部编排可以复杂，对外生命周期必须稳定

Run 对外只需要少量稳定状态。内部 LangGraph 节点、Planner 子图或工作流分支可以很多，但 Console、SLA、检查点和审计不应跟着变化。

*表22-3：Run 六态的含义与典型迁移。来源：本书整理。*

| 状态 | 含义 | 典型迁移 |
|---|---|---|
| `pending` | Run 已创建，尚未开始规划 | `start` |
| `planning` | Planner 正在生成下一步 | `plan_ready`, `plan_error` |
| `executing` | Runtime 正在执行工具或准备下一轮 | `next_step`, `done`, `need_approval`, `exec_error` |
| `waiting_human` | 有意暂停，等待审批或人工回调 | `approved`, `rejected` |
| `succeeded` | 任务结束且没有未完成副作用 | 终态 |
| `failed` | 不可恢复错误、拒绝、取消或重试耗尽 | 终态 |

![图22-1：Run 六态状态机](../../images/part5/ch/p5-01-run-state-machine.png)

*图22-1：Run 六态状态机。来源：本书自绘。Alt text：状态机包含 pending、planning、executing、waiting_human、succeeded、failed 六个节点，箭头表示从创建、规划、执行、人工等待到成功或失败的合法迁移。*

`waiting_human` 不是“系统卡住”，而是 Runtime 明确知道自己为什么暂停、正在等谁、批准后从哪里继续。审批可能持续数小时甚至数天，但仍属于同一个 Run。

终态也不能由模型决定。模型说“完成了”只代表一个生成意图；Runtime 还要确认工具队列为空、没有悬挂审批、必要 artifact 已落盘、失败已处理，才能进入 `succeeded`。

**状态机的所有合法迁移都应由 Runtime 触发。模型和 Planner 可以提出结束、审批或重试建议，但不能自行修改平台状态。**

## 22.3 执行循环、SSE 与预算：让一次 Run 有明确边界

最小执行循环可以压缩为：创建 Run → 调 Planner → 校验并执行工具 → 依据结果继续规划、等待人工或结束。

```text
create run -> planning
while run is not terminal:
  decision = planner.next_step(context)

  if decision asks for tools:
      validate policy and tool schema
      emit action event
      execute tool through registry
      emit result event
      write checkpoint

  elif decision asks to finish and no tool is pending:
      mark succeeded

  elif approval is required:
      mark waiting_human

  else:
      classify error and recover or fail
```

这里有两个硬边界：Planner 不驱动状态机；工具执行前必须经过 schema、Policy、版本和幂等检查。

![图22-2：端到端 Run 时序](../../images/part5/ch/p5-02-run-sequence.png)

*图22-2：端到端 Run 时序。来源：本书自绘。Alt text：时序图展示客户端、Runtime、Planner、Tool Registry 和模型网关之间的调用顺序，从 /run 请求到状态迁移、工具调用、事件流推送和最终返回。*

SSE/事件流应该输出平台事件，而不是把模型 token 当成任务状态。典型事件可以包括：

```text
state      # Run 状态变化
action     # 即将执行的工具及摘要
result     # 工具执行结果或 artifact ref
approval_request
approval_result
artifact
error
```

一次 Run 还必须有统一预算：LLM 调用数、Tool Call 数、最大 Step、Run 总超时、token/cost budget。没有预算的 Agent 会在参数修正、检索不充分或 Planner 犹豫时把局部错误放大成无限循环。

取消也需要明确语义。用户取消后，Runtime 要停止未执行动作，尽力取消进行中的 Tool Call，并记录哪些副作用已经发生。取消并不自动等于回滚；已经发出的邮件、写入的工单或外部请求可能需要补偿动作或人工处理。

## 22.4 Checkpoint 与恢复：恢复的是决策上下文，不只是状态字段

持久化 `state=executing` 远远不够。Runtime 重启后还必须知道 Planner 看过哪些结果、工具已经执行到哪里、Memory 当前是什么版本、哪些 Handoff/审批仍在等待。

一个可恢复检查点至少应保存：

```json
{
  "run_id": "run-8f3a",
  "state": "executing",
  "step_index": 4,
  "planner_context_ref": "mem://run-8f3a/planner-v4",
  "tool_calls": ["tc-001", "tc-002"],
  "memory_snapshot": "memory://run-8f3a/v3",
  "handoff_stack": [],
  "pending_approval": null,
  "budget": {
    "llm_calls": 5,
    "tool_calls": 2
  }
}
```

**检查点必须足以恢复“下一步为什么会这样决策”的最小上下文，而不是只恢复一个进度条。**

大对象不应重复写入 Planner 上下文。SQL 结果、长报告、文件和图表应写成 Artifact/ResultRef，检查点只保存引用和内容哈希。这样既避免 checkpoint 膨胀，也能让前端、审计和后续工具复用同一份产物。

恢复时尤其要守住幂等：

- 同一个 `tool_call_id` 不重复执行；
- 同一个 `approval_id` 不重复创建待办；
- 同一个发布动作使用稳定业务幂等键；
- 外部调用超时后先查询真实状态，再决定是否重试。

长任务可以换 Worker、重启 Pod，甚至等待人工数天，但 **Run 身份不应变化**。这正是 Runtime 与普通请求处理器最根本的区别。

## 22.5 错误分类与恢复：先判断错误性质，再决定是否重试

“失败了就重试三次”是 Agent Runtime 最危险的默认策略之一。参数错误、权限拒绝、外部超时和业务条件不满足，恢复动作完全不同。

*表22-4：Runtime 常见错误类别与恢复策略。来源：本书整理。*

| 错误类型 | 典型原因 | Runtime 动作 |
|---|---|---|
| `TOOL_ARGUMENT_INVALID` | 参数不满足 schema | 反馈 Planner 修正；受预算限制 |
| `TOOL_NOT_FOUND` | 工具/版本不存在 | 重新规划或失败，不能盲重试 |
| `POLICY_DENIED` | 用户无权限或风险策略拒绝 | 停止动作，必要时进入 HITL |
| `TOOL_UNAVAILABLE` | 网络、服务暂时不可用 | 有界重试、熔断或备用只读路径 |
| `TOOL_BUSINESS_ERROR` | 业务状态不允许动作 | 交 Planner 判断澄清/结束 |
| `RUN_BUDGET_EXCEEDED` | Step/成本/时间耗尽 | 终止或转人工 |
| `CHECKPOINT_ERROR` | 状态无法持久化 | 不继续执行新副作用 |

模型能修复的是少数参数和规划错误；权限、系统故障和副作用状态不应该让模型“再想一个办法绕过去”。

恢复还应区分 retry、replan、resume 和 compensate：

- **retry**：同一动作因瞬时故障再次执行；
- **replan**：原路径不成立，Planner 选择另一条合法路径；
- **resume**：从 checkpoint 继续同一个 Run；
- **compensate**：副作用已经发生，需要撤销或业务补偿。

**错误分类的价值，是防止“智能重试”把一个小故障扩大成重复写入、越权尝试或无限成本。**

## 22.6 mini-platform 与生产准入

mini-platform 的 Runtime 重点不在模拟完整工作流引擎，而在把状态与工具执行边界固定下来。相关实现集中在：

```text
mini-platform/core/runtime/
├── run_loop.py
├── approval.py
└── ...

mini-platform/projects/multi-agent-workflow/
└── run.py
```

验证时应至少覆盖：

1. 正常 Run 从 `pending` 到 `succeeded`；
2. 工具参数错误可反馈 Planner，但不会无限循环；
3. `waiting_human` 重启后仍保持等待；
4. approve 后在同一 `run_id` 恢复；
5. 同一 Tool Call/审批回调重复到达不会重复产生副作用；
6. 进程重启后能从 checkpoint 恢复；
7. Run 超预算、取消或不可恢复错误进入明确终态。

生产准入还需要把 `run_id`、Step、Tool Call、Artifact、状态迁移、错误分类和审批记录统一进入 Trace。这样一次事故才能沿着同一条任务链回放，而不是分别去查聊天记录、应用日志和数据库日志。

Runtime 不应保存不可控的完整模型思维过程；平台真正需要的是**结构化决策、工具参数、观察结果、策略裁决、状态迁移和最终产物**。这些证据足以解释系统做了什么，也更适合审计和长期存储。

## 本章小结

Agent Runtime 是企业 Agent 从“会调用工具”走向“能长期运行”的核心执行层。Run 管任务生命周期，Step 管决策轮次，Tool Call 管真实副作用；内部 Planner 图可以变化，但 Run 六态、事件和错误语义应保持稳定。

检查点必须保存足够的 Planner 上下文和工具历史，让服务重启、人工等待和长任务都能在同一个 `run_id` 上恢复。重试、重规划、恢复和补偿也必须按错误类型分开处理。

**一个成熟 Runtime 的判断标准，不是任务是否大多能跑成功，而是任务暂停、失败、重启、取消和被人接管时，平台仍然知道已经发生了什么，以及下一步还能安全做什么。**

## 参考文献

Yao, S. et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models*. ICLR.

Wang, L. et al. (2024). *A Survey on Large Language Model based Autonomous Agents*. Frontiers of Computer Science.

OpenAI. (n.d.). *Agents SDK / tool calling documentation*.
