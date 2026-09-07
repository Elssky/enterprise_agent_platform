# 第28章 多 Agent 协作

---

多 Agent 的价值，不是让多个模型“开会”，而是把天然不同的职责、权限和交付物拆到不同执行角色中，同时仍由同一个 Runtime 管理任务状态和审计链。

例如一份经营分析报告可能需要 Question Agent 澄清口径、Data Agent 查数、Report Agent 组织材料、Reviewer 检查风险。若全部塞给一个 Agent，它会同时拥有 SQL、报告生成、审批和外发权限，Prompt 和责任边界都会变得过宽；若简单拆成四个独立聊天机器人，又会丢失统一 `run_id`、检查点和证据链。

**多 Agent 的工程目标，是“职责分离而任务不分裂”：角色可以多个，但用户面对的仍是一条可追踪、可暂停、可恢复的 Run。**

## 28.1 什么时候值得拆成多个 Agent

多 Agent 不是默认升级路线。单 Agent 加清晰工具链能完成的任务，拆分只会增加路由、Handoff、状态同步、成本和调试复杂度。

*表28-1：单 Agent 与多 Agent 的选择信号。来源：本书整理。*

| 判断维度 | 单 Agent 更合适 | 多 Agent 更合适 |
|---|---|---|
| 工具权限 | 同一鉴权域 | SQL、报告、外部发送等权限明显不同 |
| Prompt/专长 | 一个角色能覆盖 | 澄清、分析、复核需要不同上下文和标准 |
| 责任 | 最终 Tool Call 足以说明 | 不同团队需对中间产物分别负责 |
| 并行 | 步骤天然串行 | 多数据源/区域可并行 |
| 交付 | 一个回答 | 报告、附件、审批意见、外部 artifact 多种产物 |

![图28-1：单/多 Agent 决策树](../../images/part5/ch/p5-07-multi-agent-decision-tree.png)

*图28-1：单/多 Agent 决策树。来源：本书自绘。Alt text：决策树从单 Agent 是否过载、是否需要专长分工、是否需要并行等问题分支，引向保持单 Agent 或拆分多 Agent 的结论。*

真正值得拆分的信号通常是：**不同角色需要不同权限、不同责任人或不同输入输出契约**。仅仅为了“看起来更智能”增加角色，没有生产价值。

还要区分多 Agent 与 Agentic Workflow。Reflexion、Self-Refine、ToT 可以发生在同一个 Agent 内；多 Agent 意味着出现多个独立 `agent_id`、权限和责任边界。

## 28.2 角色设计：Router 选 Agent，Planner 选工具

一个可治理的角色至少要声明：

```text
agent_id
version
capabilities
input_schema
output_schema
tool_allowlist
tenant_scope
risk_level
owner
SLO
```

*表28-2：典型角色。来源：本书整理。*

| 角色 | 主要职责 | 典型输出 | 工具边界 |
|---|---|---|---|
| Workflow / Router | 接收任务、选择下一角色 | Handoff 决策 | Agent Catalog、路由规则 |
| Question / Clarifier | 补齐口径和槽位 | `query_spec` | 低风险知识读取 |
| Data / Executor | 查数、计算、事实生成 | 指标 JSON、EvidenceRef | 语义层、SQL、Python |
| Report / Synthesizer | 生成报告或摘要 | Markdown/Artifact | 模板、渲染 |
| Reviewer / Policy | 风险、质量和合规复核 | pass / reject / HITL | 规则、评测、审批 |

Router 和 Planner 不应混淆：Router 决定“谁处理”，Planner 决定“当前 Agent 下一步用什么工具”。若让一个全局 Planner 同时理解所有 Agent 和所有 ToolSpec，候选空间会快速膨胀，也不利于权限隔离。

角色之间也不应自动继承权限。Data Agent 有客户明细读取权、Report Agent 有外发权，并不意味着组合之后可以“读取客户明细再外发”。Handoff 时必须重新计算接收方可见上下文和允许动作。

**多 Agent 的权限不是各 Agent 权限的并集，而应按当前任务重新做最小授权。**

## 28.3 Handoff：结构化转移控制权，而不是转发一段聊天

Handoff 应被视为同一个 Run 中的一次结构化控制权转移，并写入 Runtime/Trace。一个最小契约可以包括：

```json
{
  "handoff_id": "ho-001",
  "from_agent_id": "question-agent",
  "to_agent_id": "data-agent",
  "reason": "query_spec 已完整",
  "payload": {
    "goal": "解释 Q1 华东毛利下降",
    "query_spec_ref": "mem://run-1/query-spec-v2",
    "evidence_refs": []
  },
  "return_policy": "workflow",
  "idempotency_key": "run-1:ho-001"
}
```

![图28-2：Handoff 时序](../../images/part5/ch/p5-08-handoff-sequence.png)

*图28-2：Handoff 时序。来源：本书自绘。Alt text：时序图展示主 Agent 完成部分任务后，把任务上下文与状态打包交接给专长 Agent，后者处理完再交回，箭头标出交接点与上下文传递。*

Handoff 不应复制大型结果。Data Agent 输出十万行数据时，Report Agent 只需要 `result_ref`、schema、关键指标、样例和 hash，原始对象仍保留在受控存储。

接收方必须可以拒绝 Handoff，例如：payload 不完整、权限不足、任务不属于自身能力、证据已过期。拒绝不是系统错误，而是阻止错误继续传播的一种治理动作。

Handoff 还要幂等。Runtime 重试一次交接，不能让目标 Agent 重复创建报告、工单或外部任务。

**交接的核心不是“下一个 Agent 能看懂”，而是任务目标、证据、权限和责任在跨角色后仍然没有丢。**

## 28.4 共享状态：事实、推断和草稿必须分级

多 Agent 最容易失控的是所有角色共同读写一块“共享黑板”。一个 Agent 把临时推断写进去，另一个 Agent 可能把它当成事实继续执行。

共享状态至少应分三类：

1. **事实状态**：已执行查询、已确认用户输入、已通过审批的结果；带 EvidenceRef，可继续使用。
2. **推断状态**：意图判断、根因假设、候选计划；下游关键动作前需要再次校验。
3. **草稿状态**：报告段落、图表建议、未提交工具参数；允许修改，不能作为正式事实。

每次写入都应记录 Agent、版本、时间、来源和作用域。原始用户目标不应被任何子 Agent 静默覆盖；如果目标发生变化，应生成新版本并记录变更理由。

共享 Memory 也要克制。当前 Run 中的必要状态可以共享，长期用户记忆和敏感数据不能默认对所有 Agent 可见。

**共享越多并不代表协作越好。多 Agent 的稳健性往往来自“只传下一角色完成职责真正需要的最小状态”。**

## 28.5 路由、Agent Catalog 与低置信度处理

Router 不应靠模型临场猜测所有 Agent。生产通常采用：规则 + 分类模型 + Agent Catalog + 权限过滤的混合路由。

Agent Catalog 至少保存能力、输入输出 schema、工具白名单、租户范围、版本、SLO、owner 和健康状态。Router 先过滤不可用/无权限候选，再做语义选择。

*表28-3：常见路由策略。来源：本书整理。*

| 策略 | 优势 | 风险 |
|---|---|---|
| 规则路由 | 可预测、便宜 | 覆盖有限 |
| 分类模型 | 适应自然语言 | 需要置信阈值和回归集 |
| Catalog/能力匹配 | 适合 Agent 数量增多 | 元数据漂移 |
| 混合路由 | 兼顾稳定和灵活 | 运维复杂度更高 |

低置信度时，`clarify/reject` 应是一等结果。没有合适 Agent、任务缺关键字段或跨租户时，强行选择“最像的一个”会比停下来更危险。

路由结果也要进 Trace：候选、过滤原因、Catalog 版本、最终 Agent 和置信度。否则多 Agent 出错后会把所有问题归因成“下游 Agent 不稳定”。

## 28.6 冲突与并行：不要让末端 LLM 把矛盾“综合一下”

多个 Agent 并行后会出现事实、口径、叙事和资源冲突。

*表28-4：冲突类型与处理。来源：本书整理。*

| 冲突 | 示例 | 处理 |
|---|---|---|
| 事实冲突 | 同一指标返回不同值 | 回到权威数据源和版本 |
| 口径冲突 | 时间、过滤、metric_id 不同 | 退回重新对齐 query_spec |
| 叙事冲突 | Report 与 Reviewer 结论相反 | 保留批注并修订，不静默覆盖 |
| 写冲突 | 多 Agent 同时改同一 Artifact | 单写者/版本/乐观锁 |
| Handoff 环 | A→B→A 反复转移 | 栈深、payload hash、max_steps |

当两个 Data Agent 给出不同数字时，Report Agent 不能用“平均一下”解决；Reviewer 指出合规风险时，也不能让 Workflow 根据文本流畅度继续发布。

**多 Agent 系统必须允许输出“不一致，无法自动完成”。不能自动裁决的冲突，本身就是需要升级到规则或人工的事实。**

并行执行还需要明确合并条件。只有 metric version、时间范围、租户、EvidenceRef 等前提一致时，结果才可以合并。

## 28.7 Runtime、失败恢复与 mini-platform

多 Agent 仍然使用同一套 Run 六态。检查点只需增加必要协作状态，例如：

```json
{
  "run_id": "run-001",
  "active_agent_id": "report-agent",
  "handoff_stack": ["workflow-agent", "report-agent"],
  "shared_state_refs": ["mem://run-001/query-spec-v2"],
  "agent_versions": {
    "workflow-agent": "v3",
    "data-agent": "v4",
    "report-agent": "v2"
  }
}
```

Handoff 失败要分原因恢复：上下文缺失 → 回上游补齐；权限不足 → HITL/拒绝；能力不匹配 → Router 重选；目标 Agent 暂不可用 → 有界重试/备用；循环达到阈值 → 转人工或失败。

`projects/multi-agent-workflow/` 的最小链路应验证：

```bash
cd mini-platform
python3 projects/multi-agent-workflow/run.py start
python3 projects/multi-agent-workflow/run.py approve
```

验收至少包括：同一 `run_id` 贯穿全部 Agent；Handoff 后重启可恢复 `active_agent_id`；目标 Agent 缺失/拒绝时返回结构化错误；循环不会无限发生；每个 Agent 的工具白名单和输入输出都可追溯。

还要比较单 Agent 与多 Agent 的真实收益：路由准确率、Handoff 拒绝率、冲突率、任务完成率、成本、延迟、人工接管和错误定位时间。如果拆分后没有改善责任隔离或任务质量，就应允许合并回简单架构。

**多 Agent 架构要能扩张，也要能收缩。角色数量不是成熟度指标。**

## 本章小结

多 Agent 适合职责、权限或组织责任天然不同的复杂任务，不应作为默认架构。Router 决定 Agent，Planner 决定工具；Handoff 在同一个 Run 中结构化转移控制权，不能靠自然语言转发替代契约。

共享状态需要区分事实、推断和草稿；跨 Agent 权限按任务重新计算；并行结果有冲突时优先回到权威源或人工仲裁，而不是让模型把矛盾润色掉。

**多 Agent 的成熟度不看系统里有多少“角色”，而看每一次交接后还能否准确回答：谁负责、看到了什么证据、拥有什么权限，以及任务失败后应该由谁接回来。**

## 参考文献

Li, G., et al. (2024). CAMEL: Communicative agents for “mind” exploration of large language model society. *NeurIPS*.

Qian, C., et al. (2024). *ChatDev: Communicative Agents for Software Development*.

Google. (2025). *Agent2Agent (A2A) Protocol*.

Microsoft. (n.d.). *AutoGen*.

Wu, Q., et al. (2024). *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation*.

OpenAI. (2024). *Swarm*.

Hong, S., et al. (2024). *MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework*.

Wang, L., et al. (2024). *A Survey on Large Language Model based Autonomous Agents*.

Model Context Protocol. (2024). *Specification*.

Yao, S., et al. (2023). *ReAct: Synergizing Reasoning and Acting in Language Models*.
