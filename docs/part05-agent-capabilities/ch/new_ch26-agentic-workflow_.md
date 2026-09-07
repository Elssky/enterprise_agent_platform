# 第26章 Agentic Workflow

---

Reflexion、Self-Refine、Tree of Thoughts 等方法可以让 Agent 在局部失败后重新思考、改写或搜索更多候选，但它们不应该变成第二套 Runtime。企业真正需要的是：在已有 Planner 和 Run 状态机内部，引入**受预算、可观测、可关闭**的增强机制。

**Agentic Workflow 是 Planner 的局部增强层，不替代 Runtime、Policy 或 Tool Registry。增强机制可以多想几次，但不能因此获得额外执行权。**

## 26.1 增强机制的边界：默认关闭，按任务启用

第25章 Planner 已经负责选择下一步，第22章 Runtime 已经负责状态和执行。Reflexion、Self-Refine、ToT 只解决“Planner 内部是否值得再做一次判断”。

![图26-1：Agentic Workflow 增强边界](../../images/part5/ch/ch26-workflow-enhancement-boundary.svg)

*图26-1：Agentic Workflow 增强边界。来源：本书自绘。Alt text：图中展示 Runtime、Planner 和增强机制三层边界；Reflexion、Self-Refine 和 Tree of Thoughts 位于 Planner 内部，默认关闭，并把额外 LLM 调用计入 Trace 与预算。*

*表26-1：Planner 与增强机制的职责。来源：本书整理。*

| 能力 | 解决什么问题 | 不应该承担什么 |
|---|---|---|
| Planner | 决定下一步动作 | 不直接执行工具 |
| Reflexion | 根据失败观察总结并调整下一次决策 | 不修复权限/系统故障 |
| Self-Refine | 对已有草稿进行多轮自评与改写 | 不改变事实来源 |
| Tree of Thoughts | 在多个候选推理分支中搜索 | 未选分支不能执行真实工具 |

每种增强都应有开关、最大轮数、token/cost budget 和适用任务。低风险 FAQ 没必要启用复杂反思；高价值报告可以允许一次 Self-Refine；复杂规划可在离线/内部阶段使用 ToT，但不能把分支探索变成多条真实副作用路径。

## 26.2 Reflexion：只反思模型可修复的错误

Reflexion 的价值，是把工具或评测反馈转成下一轮 Planner 可用的“失败经验”。例如 SQL 参数错误、证据不足、字段选择不合理，模型可以总结原因后重新规划。

它不适合处理：

- `POLICY_DENIED`；
- 网络/服务不可用；
- 外部系统已经产生副作用但状态不确定；
- 业务规则明确禁止的动作。

这些问题继续让模型“反思一下”只会增加成本，甚至鼓励它寻找绕过策略。

一个最小 Reflexion 记录可以是：

```json
{
  "step": 4,
  "failure_type": "TOOL_ARGUMENT_INVALID",
  "observation": "metric_id is required",
  "reflection": "先解析指标，再调用查询工具",
  "max_retry_round": 1
}
```

**反思的边界不是“模型有没有新想法”，而是错误是否属于模型能够合法修正的决策空间。**

## 26.3 Self-Refine：改表达，不重写事实

Self-Refine 更适合报告、邮件、解释和代码草稿等 Artifact。模型先生成结果，再按检查项批评并改写。

风险在于：第二轮“润色”可能偷偷改变数字、引用或结论。因此应把**事实槽位**与**表达槽位**分开：

```json
{
  "facts": {
    "gmv_change": -0.083,
    "top_sku": "SKU-1024",
    "evidence_refs": ["sql://q-001", "kb://policy-v3#c12"]
  },
  "draft": "华东区销售下降……"
}
```

Self-Refine 只能修改 `draft`，事实值和 EvidenceRef 默认只读。若改写需要新增事实，应重新进入检索/工具链，而不是在文本生成阶段补充。

*表26-2：Reflexion 与 Self-Refine 的区别。来源：本书整理。*

| 机制 | 主要输入 | 输出变化 | 典型风险 |
|---|---|---|---|
| Reflexion | 失败观察/执行反馈 | 下一步决策 | 对不可修复错误重复推理 |
| Self-Refine | 已有草稿 + 评价标准 | Artifact 表达 | 改写时篡改事实 |

## 26.4 Tree of Thoughts：搜索候选计划，未选分支绝不能产生副作用

ToT 通过生成多个候选思路、评分并继续扩展较优分支，提高复杂推理的搜索能力。生产应用的关键限制是：**分支是内部思考候选，不是并行执行路径。**

例如 Planner 可以比较三种分析方案：查销售→库存、查促销→价格、查区域→门店；评分后只选择一条进入 Runtime。未被选中的分支不能调用数据库写工具、发消息或创建工单。

*表26-3：ToT 的三层边界。来源：本书整理。*

| 层 | 允许做什么 | 禁止做什么 |
|---|---|---|
| Thought generation | 生成候选计划/假设 | 真实工具副作用 |
| Branch evaluation | 根据已有证据评分 | 绕过 Policy 获取新权限 |
| Runtime execution | 只执行被选中的正式决策 | 同时执行多个未经批准分支 |

参数至少应限制 `branch_factor`、`max_depth`、`max_llm_calls`、`max_cost` 和总时长。高分不是执行授权，最终候选仍要通过 Tool Registry 和 Policy。

## 26.5 为什么不把 AutoGPT 式无限自治循环作为默认架构

“直到任务完成为止不断规划—执行—反思”的无限循环很适合展示自主性，却不适合默认生产模式。真实企业任务存在工具副作用、不可恢复错误、用户撤回、预算和责任边界。

成熟系统应显式定义停止条件：

- Step/LLM/Tool Call 达到上限；
- 连续重复相同动作或近似参数；
- 证据长期无法增加；
- 目标条件已满足；
- 关键前提缺失，需要澄清；
- Policy/HITL 阻断；
- 用户取消；
- 成本或 SLO 超限。

**生产 Agent 的自主性应是“有界自主”，而不是“不停地自己想办法”。**

## 26.6 预算、Trace 与灰度：增强层必须独立可观测

Agentic Workflow 应至少分别记录三个计数：

```text
step_index
llm_call_count
tool_call_count
```

增强机制往往增加 LLM 调用但不增加正式 Step，如果只看 Step 数，会低估成本。每次 Reflexion、Self-Refine 和 ToT branch 应形成独立 Trace span，并标记是否影响最终决策。

*表26-4：增强策略的生产约束。来源：本书整理。*

| 约束 | 推荐方式 |
|---|---|
| 开关 | 按 Agent/任务类型默认关闭、显式启用 |
| 轮数 | Reflexion/Self-Refine 1–2 轮起步 |
| 成本 | 单独统计额外 LLM 调用和 token |
| 工具 | 内部候选不得产生副作用 |
| 权限 | 仍由 Runtime/Policy 决定 |
| 失败 | 增强失败可降级回基础 Planner |
| 发布 | 策略版本独立灰度和回滚 |

评测要比较“基础 Planner”与“基础 + 增强”的真实增益：任务成功率提高多少、成本增加多少、延迟增长多少、是否增加高风险误行为。只要收益不足以覆盖复杂度，就应该关闭增强。

## 26.7 mini-platform：把增强策略做成可插拔模块

mini-platform 更适合把这些方法做成 Planner 内部策略，而不是新 Runtime：

```python
planner = Planner(
    reflection_policy=ReflectionPolicy(max_rounds=1),
    refine_policy=RefinePolicy(enabled=False),
    thought_search=ThoughtSearch(enabled=False),
)
```

测试至少覆盖：权限失败不会触发 Reflexion；Self-Refine 不改变事实槽位；ToT 未选分支不执行工具；预算耗尽后回到基础失败/人工路径；关闭增强时外部 Run 契约保持不变。

增强策略版本可以绑定：

`workflow_enhancement + prompt + model + budget + eval_set`

这样新策略出现回归时，可以只撤回增强层，不影响 Runtime 和工具目录。

## 本章小结

Reflexion、Self-Refine 和 Tree of Thoughts 都是 Planner 内部的局部增强，不应扩张 Runtime 状态或绕过 Tool Registry/Policy。Reflexion 只处理模型可修正的决策错误，Self-Refine 默认只改表达，ToT 的未选分支绝不能执行真实副作用。

增强机制必须受轮数、LLM 调用、时间和成本预算限制，并能单独评测、灰度和关闭。

**Agentic Workflow 的价值不在于让模型“想得更多”，而在于只在值得的任务上用有限额外推理换取可证明的质量提升。**

## 参考文献

Shinn, N. et al. (2023). *Reflexion: Language Agents with Verbal Reinforcement Learning*.

Madaan, A. et al. (2023). *Self-Refine: Iterative Refinement with Self-Feedback*.

Yao, S. et al. (2023). *Tree of Thoughts: Deliberate Problem Solving with Large Language Models*.
