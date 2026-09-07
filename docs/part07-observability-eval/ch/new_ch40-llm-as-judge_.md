# 第40章 在线评测、模型裁判与持续优化

---

离线 Benchmark 通过以后，DataAgent 仍会在真实流量中遇到新问法、新权限组合、新数据状态和新的用户预期。用户点踩一份报告，也不一定意味着模型回答错误：可能是等待太久、证据隐藏、权限拒绝解释不清，或报告确实用了错误 Metric。

在线评测的任务，就是把这些现场信号重新连接到 Run、Trace、版本和业务证据。LLM-as-Judge 可以扩大开放式质量检查的覆盖面，但它本身也是一个会偏、会漂移、需要版本治理的模型组件。

**线上反馈首先是线索，不是 Ground Truth；只有与 Trace、业务证据和人工判断结合以后，才适合转成质量样本。**

## 40.1 在线评测、离线 Benchmark 与人工复核是一套闭环

![图40-1：在线评测、离线评测与人工复核的闭环关系](../../images/part7/ch/ch40-01.png)

*图40-1：在线评测、离线评测与人工复核的闭环关系。来源：本书自绘。Alt text：环形关系图，离线 benchmark 设基线、在线评测覆盖真实流量、人工复核校准裁判，三者结果互相回流，箭头表示构成持续校准的质量闭环。*

三类机制职责不同：

- **离线 Benchmark**：固定样本与环境，防止已知问题回归；
- **在线评测**：发现生产分布中的未知问题和行为变化；
- **人工复核**：处理高风险、争议和自动评测不稳定的样本。

线上发现的新问题经过确认后进入 Regression/Safety Set；离线修复通过后再小流量灰度；人工复核不仅校准 Agent，也校准 Judge 和 rubric。

这条链依赖统一关联键：`run_id`、`trace_id`、模型/Prompt/Tool/语义层/Policy 版本、Artifact 和用户反馈。没有这些事实，点踩率只能告诉团队“有人不满意”，无法说明该改哪里。

**在线评测不是把用户反馈做成一个看板，而是把真实使用中出现的异常转成可复现、可归因、可回归的工程资产。**

## 40.2 用户反馈：显式、隐式和业务结果都不能直接当标签

线上质量信号至少有三类。

*表40-1：线上反馈信号。来源：本书整理。*

| 类型 | 示例 | 优点 | 风险 |
|---|---|---|---|
| 显式反馈 | 点赞/点踩、评分、文字意见 | 意图直接 | 覆盖低、强情境性 |
| 隐式行为 | 重试、追问、下载、复制、人工接管、放弃 | 覆盖广 | 含义多义 |
| 业务结果 | 报告采纳、SQL 保存、工单升级、审批通过 | 接近真实价值 | 滞后且归因复杂 |

例如“继续追问”既可能表示答案不清楚，也可能表示用户获得启发；下载报告通常是正向信号，但也可能只是拿去人工大改。因此反馈记录需要绑定现场证据：

```json
{
  "feedback_id": "fb_001",
  "run_id": "run_fin_042",
  "trace_id": "trace_fin_042",
  "task_type": "cashflow_root_cause",
  "feedback_type": "thumb_down",
  "user_comment": "华东区口径不对",
  "artifact_refs": ["report_fin_042"],
  "model_version": "model:v4",
  "prompt_version": "finance:v12",
  "semantic_layer_version": "finance:v18",
  "policy_version": "policy:v7"
}
```

可以计算反馈强度用于**筛样优先级**，但不能把这个分数当质量真相。最终还要看 Trace、工具结果、Metric、权限和人工裁定。

线上采样也要混合：固定比例随机样本 + 所有安全命中 + 低分 + 灰度版本 + 显式负反馈 + 高成本/人工接管。只采成功会漏掉失败，只采点踩又会高估问题严重程度。

## 40.3 线上看板的关键不是指标多，而是能下钻到 Trace

在线评测可以按四类信号组织：

**质量**：任务完成率、首次可用答案率、点踩、重生成、人工接管、报告采纳。

**效率**：交互轮数、P50/P95 延迟、Tool Call、重试、token/Run。

**安全**：越权拦截、敏感字段、正确拒答、审批完整率。

**业务价值**：看板保存、报告进入会议、建议被采纳等。

指标应按任务类型、业务域、租户、版本切片。月末财务任务本身更复杂，点踩上升不一定意味着模型退化；Policy 收紧导致拒答增加，也可能是安全改进。

管理层可以看趋势，工程团队必须能从“某类任务点踩从 6% 变 13%”继续下钻：是否集中在某个 Prompt、某个 Metric、某个 Tool、某个数据源或某种失败路径。

**指标负责发现“哪里不对劲”，Trace 负责证明“为什么不对劲”。没有下钻能力的在线评测，无法指导修复。**

## 40.4 LLM-as-Judge：评开放式语义，不替代硬事实

LLM-as-Judge 适合报告质量、解释完整性、证据支撑、可执行性和表达适配等开放式判断。它不应替代：SQL 执行结果、数值断言、权限、EvidenceRef 存在性和安全门禁。

**先规则，再 Judge，再人工**是更稳的层次：

```text
确定性规则/执行验证
    ↓
开放式 Judge
    ↓
高风险/高分歧人工复核
```

一个 DataAgent Judge 输入可以同时提供：

```json
{
  "question": "本月经营性现金流为什么下降？",
  "task_type": "root_cause_analysis",
  "candidate_answer": "...",
  "evidence": {
    "sql_result_summary": "华东区贡献下降 62%...",
    "artifact_refs": ["chart_cashflow_042"],
    "source_graph_summary": "finance_semantic:v18 -> sql_result -> report"
  },
  "rubric": {
    "correctness": "结论与执行结果一致",
    "grounding": "关键结论可回到证据",
    "actionability": "下一步动作具体且不过度",
    "safety": "无越权或敏感信息"
  }
}
```

输出应结构化：

```json
{
  "dimension_scores": {
    "correctness": 4,
    "grounding": 3,
    "actionability": 2,
    "safety": 4
  },
  "confidence": 0.76,
  "failure_tags": ["missing_next_step"],
  "rationale": "关键数字有证据，但行动建议过泛。"
}
```

总分可以按维度加权：

$$
JudgeScore=\frac{\sum_i w_i(d_i/4)}{\sum_i w_i},\quad d_i\in\{0,1,2,3,4\}
$$

离散档位通常比自由 0–100 分更稳定。安全、权限和“无证据关键事实”等则更适合二元门禁。

**LLM-as-Judge 是质量筛查器，不是新的事实源；它只有在 rubric、证据、人工校准和版本治理共同约束下，才适合进入发布门禁。**

## 40.5 Rubric：把“这份报告好不好”拆成可验证标准

模糊 rubric，例如“答案是否高质量”，会奖励长度、格式和流畅度。企业任务需要把标准拆成原子检查项。

例如一份授信/经营分析报告可以分别检查：

- 关键定义是否准确；
- 公式/参数是否可复算；
- 主要结论是否有 EvidenceRef；
- 是否覆盖用户要求的维度；
- 是否把推断误写成事实；
- 行动建议是否和证据对应；
- 是否守住数据与权限边界；
- 可视化是否真正表达关键比较。

DACOMP 类 Data Agent benchmark 的启发在于：复杂报告不适合只打一个“像不像专业报告”的总分，而应同时评价任务满足度、可读性、专业深度和可视化等不同维度。

对开放的新型任务，可以让模型生成候选 rubric，但不应每次临场自由定标准。更稳的路线是：动态生成候选 → 去重/原子化 → 专家或规则审核 → 在多次任务中验证 → 稳定后进入 Regression Set。

**Rubric 的价值不是让 Judge 写更多评价文字，而是把业务专家的判断标准变成可重复运行的质量契约。**

## 40.6 Judge 偏差与校准：裁判本身也会犯错

常见偏差包括：

- **位置偏差**：成对比较偏好 A 或第一项；
- **长度偏差**：更长看起来更完整；
- **风格偏差**：格式漂亮被误判为事实更好；
- **自偏好**：偏爱与自身生成风格相似的答案；
- **参考泄漏**：奖励“像参考答案”，不是真正语义正确；
- **领域盲区**：不了解内部指标或政策。

工程控制至少包括：

1. 隐藏候选模型身份；
2. Pairwise 随机交换顺序，记录 `order_seed`；
3. Judge model、Prompt、rubric 全部版本化；
4. 固定专家 Golden Set 校准；
5. 多 Judge 比较均值/方差/分歧；
6. 高方差、低置信、高风险进入人工复核；
7. 安全结论始终由规则/Policy/专家兜底。

Judge 与人工一致率可作为一个基础指标：

$$
JudgeAgreement=
\frac{N_{judge=expert}}{N_{reviewed}}
$$

若 Agreement 下降，先检查任务分布和 Judge/rubric 是否漂移，不要直接根据新的 Judge 分去优化 Agent。

多个 Judge 时，可以同时展示：`mean_score`、`std_score`、`judge_agreement`、人工通过率，而不是只展示一个最漂亮的分数。

ResearchRubrics、DeepResearch Bench II、RubricEval、LLM-Rubric 等研究共同提示：**“一个模型的一次判断”不应该被当成评测真相。**

## 40.7 Agent-as-Judge：有些问题必须检查证据路径

普通 Judge 只读问题和最终文本，很难知道 Agent 是否真正读取了正确文件、Metric、SQL Result 或 Artifact。

![图40-2：Workspace-Bench 中的工作区依赖图与评分标准集示例](../../images/part7/ch/ch40-02.png)

*图40-2：Workspace-Bench 中的工作区依赖图与评分标准集示例。来源：本书自绘。Alt text：左侧是任务涉及的表、字段、工具构成的依赖图，右侧是对应的分项评分标准（口径、正确性、解释），示意复杂任务如何拆成可逐项打分的标准集。*

Agent-as-Judge 可以进一步查看：

```text
final answer
source graph
file / schema reads
tool calls
tool results
artifact lineage
policy results
```

例如报告写了“华东区贡献下降 62%”，Judge 不只判断句子合理，还应检查：是否读过相应 SQL Result、报告的 EvidenceRef 是否真正指向那组结果、Metric 版本是否正确。

这类动态工具型 Judge 特别适合跨文件、跨数据、多 Artifact 任务。它依然不能获得无限权限；评测环境应给 Judge **只读、最小、可审计** 的查询能力。

## 40.8 持续优化：从线上异常到可关闭的问题

完整链路可以表达为：

```text
Production Run
  → feedback / anomaly / cost / safety signal
  → Trace replay
  → deterministic check / Judge / human
  → root-cause label
  → Regression / Safety sample
  → fix Prompt / Tool / Semantic / Policy / UX
  → offline eval
  → gray release
  → online validation
  → close or reopen issue
```

重要的是“关闭问题”。样本进入修复队列后，应记录根因、修复版本、回归结果、灰度指标和最终结论。否则平台只会积累越来越多“曾经出现过的问题”。

根因也不一定是模型：

*表40-2：Judge/反馈失败与典型责任层。来源：本书整理。*

| 失败 | 优先检查 |
|---|---|
| 关键数字错 | Metric、SQL、Tool Result |
| Grounding 低 | EvidenceRef、Context、报告模板 |
| 任务没完成 | Planner、Tool 缺口、产品交互 |
| 语言过长 | Prompt / Report template |
| 权限/泄漏 | Policy、Context Builder、Tool |
| 用户总追问 | 信息架构、澄清、产品预期 |

**持续优化的单位应该是一条带 Trace、版本、证据和业务反馈的真实运行样本，而不是一句“Prompt 再优化一下”。**

## 40.9 A/B 与灰度：Judge 分数提高不等于真实用户受益

离线和 Judge 通过以后，还要看真实用户行为。实验对象可以是模型、Prompt、路由、检索、缓存、报告模板或工具策略。

Agent 的多轮上下文决定实验最好按用户、租户或 Session 分桶，而不是每次请求随机，否则同一会话可能前后使用两个版本，结果不可解释。

发布至少定义：

- **Primary metric**：任务完成、首次可用答案、报告采纳等；
- **Guardrail**：Safety、P95、成本、人工接管、拒答正确率等。

简化判定：

$$
Launch=1\quad \text{iff}\quad \Delta Primary>\tau_p\ \land\ Guardrails=pass
$$

高风险样本的 Safety/HITL 不是普通护栏，而是硬门禁。

也要防止“为 Judge 优化”：加更多固定段落、写更长 Evidence 列表可能提高裁判分，却让用户更难阅读。最终要联合看追问率、人工修改、采纳、投诉、延迟和成本。

## 40.10 Judge 漂移、人工申诉与版本治理

Judge 模型升级、Prompt 改写、rubric 变化、任务分布变化都会让历史分数失去直接可比性。因此每次 Judge 变更先在固定 Golden Set 上重跑，比较分数分布、failure tags 和人工一致率。

还应提供申诉：业务 reviewer 或工程 owner 可以指出裁判误解行业术语、没有看到图表证据、把合规拒答误判为未完成。申诉记录至少包含原样本、Judge 输入输出、人工理由和最终裁定。

申诉成立后，平台决定：修 rubric、增加示例、改阈值、增加结构化证据，或将这类任务永久转人工评审。

Judge 的版本账本至少记录：

```text
judge_model_version
judge_prompt_version
rubric_version
calibration_set_version
thresholds
applicable_task_types
known_failure_modes
```

**裁判如果不可质疑、不可回滚，也会成为新的黑盒单点。企业真正需要的是可校准的评测工具，而不是把质量责任转交给另一个模型。**

## 本章小结

在线评测负责发现真实流量中的新问题，离线 Benchmark 负责阻止已知问题回归，人工复核则校准高风险和争议判断。显式反馈、隐式行为和业务结果都只是信号，必须与 Trace 和版本事实结合。

LLM-as-Judge 适合开放式质量初筛，硬事实和安全仍优先使用确定性校验。Rubric 要原子化、可验证；Judge 要做顺序随机化、黄金样本校准、多模型对照、人工抽检和版本治理。复杂任务可以进一步使用 Agent-as-Judge 检查 source graph 和工具证据。

**一个成熟的持续优化系统，不是 Judge 给出低分后立刻改 Prompt，而是能够把线上问题定位到真实责任层，转成回归样本，验证修复，并用灰度数据证明用户确实得到改善。**

## 参考文献

Lei, F. et al. (2025). *DAComp: Benchmarking Data Agents across the Full Data Intelligence Lifecycle*. https://arxiv.org/abs/2512.04324

Tang, Z. et al. (2026). *Workspace-Bench 1.0*. https://arxiv.org/abs/2605.03596

Sharma, M. et al. (2025). *ResearchRubrics*. https://arxiv.org/abs/2511.07685

Li, R. et al. (2026). *DeepResearch Bench II*. https://arxiv.org/abs/2601.08536

Pan, T. et al. (2026). *RubricEval*. https://arxiv.org/abs/2603.25133

Hashemi, H. et al. (2025). *LLM-Rubric*. https://arxiv.org/abs/2501.00274
