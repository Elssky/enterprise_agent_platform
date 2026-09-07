# 第39章 企业级 DataAgent 评测体系设计与 Benchmark 构建

---

企业级 DataAgent 的评测对象不是一段最终回答，而是一条数据任务链。SQL 可能碰巧得到正确数字，却用了错误 Metric；报告可能语言流畅，却把相关关系写成因果；任务最终完成，也可能绕过权限或通过不可复现的路径得到结果。

因此，一个可用于发布决策的 Benchmark 必须同时回答：结果是否正确，模型得到的语义上下文是否正确，执行轨迹是否合理，安全边界是否守住，以及完成任务付出了多少成本。

**企业 DataAgent Benchmark 的目标不是产生一个漂亮总分，而是把“在哪些任务上可靠、在哪些约束下必须停下来”变成可重复验证的发布边界。**

## 39.1 Benchmark 不是题库：它是一套可复现的质量协议

一个合格 Benchmark 至少包含四部分：

1. **任务定义**：明确测什么能力和边界；
2. **可复现数据**：数据快照、权限和上下文固定；
3. **统一执行/判分流程**：不同版本按相同协议运行；
4. **可解释指标**：分数能回到具体失败类型。

只有“问题 + 黄金答案”而没有数据版本、语义口径、执行环境和评测脚本，更接近练习题，不适合作为生产回归。

![图39-1：从 LLM Benchmark 到企业 DataAgent Benchmark 的演进时间线](../../images/part7/ch/ch39-01.png)

*图39-1：从 LLM Benchmark 到企业 DataAgent Benchmark 的演进时间线。来源：本书自绘。Alt text：时间轴从早期通用 NLP benchmark、Text-to-SQL（Spider）、多步 workflow（Spider 2.0）到企业内部任务集，标注评测对象逐步从单句 SQL 扩展到全链路任务。*

评测对象经历了明显扩展：传统 NLP 关注固定输入输出；MMLU、BIG-Bench、HELM、C-Eval、CMMLU 评通用模型能力；AgentBench、WebArena、OSWorld 开始评工具和环境交互；WikiSQL、Spider、BIRD、Spider 2.0 评数据库和企业式 Text-to-SQL；BEAVER、Workspace-Bench、Deep Research 类 benchmark 又继续增加领域知识、依赖关系、开放报告和多步任务。

公开 Benchmark 适合提供方法论和能力下限，但**企业是否上线仍要看自己的表、Metric、权限、用户问题和运行轨迹。** 一个模型在 Spider 上得分高，不能证明它理解公司的经营 GMV 或能正确处理无权限用户。

## 39.2 评测对象：结果、语义上下文、轨迹、安全与成本

![图39-2：DataAgent 评测对象分层图](../../images/part7/ch/ch39-02.png)

*图39-2：DataAgent 评测对象分层图。来源：本书自绘。Alt text：自上而下分层，最终答案、解释与口径、SQL/代码正确性、执行轨迹，每层标注对应评测方式，体现评测须覆盖结果与过程多层而非只看答案。*

可以把质量拆为：

$$
Score_{quality} =
w_r Score_{result}
+ w_s Score_{semantic}
+ w_t Score_{trajectory}
+ w_{safe} Score_{safety}
$$

若还要考虑运行效率：

$$
Score_{agent}=Score_{quality}-w_c\cdot CostPenalty
$$

这些权重只是一种表达，生产中更重要的是区分“可加权指标”和“硬门禁”。越权、敏感泄漏、未审批写操作等通常应直接失败，不能让一个很高的语言质量分把风险平均掉。

*表39-1：评测层与典型问题。来源：本书整理。*

| 评测层 | 核心问题 | 典型方法 |
|---|---|---|
| Result | 数字、表格、Artifact 是否正确 | 执行比对、数值断言 |
| Semantic | Metric、schema、source、Memory、Policy 是否正确 | 必需 source / context 精准率召回率 |
| Trajectory | 工具、状态、权限检查、恢复路径是否合理 | eval_trace、规则、source graph |
| Safety | 是否越权、泄漏、绕过审批 | 硬规则 / Safety Set |
| Cost/Latency | 正确任务的运行代价是否可接受 | Trace 成本和时延 |

**结果正确不能掩盖口径错误、越权路径或不可复现轨迹。** 同样，轨迹不必和“参考脚本”逐步一致，只要必要证据、控制点和业务结果都成立。

## 39.3 任务空间：先画能力地图，再填样本

Benchmark 容易被大量简单问数“刷满”。更好的方式是先定义任务空间，再要求每个分桶达到最低覆盖。

![图39-3：企业 DataAgent Benchmark 任务空间矩阵](../../images/part7/ch/ch39-03.png)

*图39-3：企业 DataAgent Benchmark 任务空间矩阵。来源：本书自绘。Alt text：矩阵以"任务类型（查询/归因/预测）"和"难度（单表/多表/多步）"为轴，每格放一类代表任务，体现 benchmark 按任务空间均衡覆盖而非随意堆题。*

至少考虑三组维度：

**任务意图**：查询、对比、诊断、归因、预测、解释、报告、拒答/审批。

**执行复杂度**：单表、多表 Join、多事实表、跨源、历史快照、多轮、长上下文、多个 Artifact。

**企业约束**：Metric 歧义、权限差异、数据冲突、新鲜度、人工确认、安全限制、业务修订。

覆盖率可以写成：

$$
Coverage =
\frac{\sum_{d \in D} I(count(d)\ge min(d))\cdot weight(d)}
{\sum_{d \in D} weight(d)}
$$

这样 1000 道单表查询不会掩盖“高风险审批样本只有 2 道”。

样本集也应分用途：

- **Golden Set**：高质量人工确认，稳定比较核心能力；
- **Regression Set**：历史故障和已修复问题；
- **Safety Set**：越权、敏感数据、拒答、Prompt Injection 等；
- **Stress Set**：长上下文、多表、工具故障、资源限制；
- **Open Report Set**：开放式分析/报告，需要 rubric；
- **Candidate Pool**：线上新问题，尚未完成准入。

**Benchmark 的样本数量是次要指标，关键是它是否覆盖真实任务分布和不能承受的失败。**

## 39.4 确定性评测优先：能用程序判定的，不要先交给 Judge

SQL、数字、权限和结构化 Artifact 应优先使用确定性评测。

SQL 至少区分“能否执行”和“结果是否正确”。不同 SQL 文本可能语义等价，因此结果比较前要标准化列、类型、排序、NULL 和浮点格式：

$$
ResultHit=
\mathbf{1}[Normalize(R_{pred})=Normalize(R_{ref})]
$$

数值任务使用绝对/相对容差：

$$
NumHit(x,x^*)=
\mathbf{1}\left[
|x-x^*|\le \max(\epsilon_{abs},\epsilon_{rel}|x^*|)
\right]
$$

多个关键数值可加权：

$$
Score_{num}=\frac{\sum_i w_i NumHit(x_i,x_i^*)}{\sum_i w_i}
$$

开放式报告也可以先做断言，例如：

- 是否出现正确 Metric/version；
- 所有关键数字是否存在于 SQL/Python Artifact；
- 必须结论是否覆盖；
- EvidenceRef 是否存在且可打开；
- 禁止字段是否没有出现；
- 报告是否正确进入 HITL。

这些断言通过后，才让第40章的 LLM-as-Judge 评价“解释是否完整、语言是否适合 CFO、建议是否可执行”。

**模型裁判应补充程序无法稳定表达的开放质量，而不是替代已经可以严格验证的事实。**

## 39.5 三层核心评测：Result、Semantic Context、Trajectory

![图39-4：结果评测、语义上下文评测与轨迹评测](../../images/part7/ch/ch39-04.png)

*图39-4：结果评测、语义上下文评测与轨迹评测。来源：本书自绘。Alt text：三种评测并列，结果评测比对最终答案、语义上下文评测检查口径与解释、轨迹评测核对执行步骤，箭头表示三者结合才能定位失败发生在哪一层。*

### Result

看最终数据、图表、报告和结构化字段是否正确。对开放式答案允许多种表达，但关键事实必须一致。

### Semantic Context

看 Planner 决策前是否拿到正确、足够且有权访问的材料。可以把参考必需材料 `S_ref` 与实际 Context Package 中的 `S_pred` 比较：

$$
ContextRecall=\frac{|S_{pred}\cap S_{ref}|}{|S_{ref}|}
$$

$$
ContextPrecision=\frac{|S_{pred}\cap S_{ref}|}{|S_{pred}|}
$$

不仅要防“漏看关键 Metric”，也要防“塞入大量无关 source”扰乱模型。

### Trajectory

看外显动作是否符合生产边界。例如：

- 指标歧义时是否先消歧；
- 计算是否真正调用工具，而不是模型心算；
- Tool Result 是否回灌 Planner；
- 权限检查是否发生在副作用前；
- EvidenceRef 是否来自真实读取过的 Artifact；
- 不可恢复错误是否停止重试。

轨迹允许多解。A Agent 可以先查指标字典再 SQL，B Agent 可以先查语义 View，只要都覆盖必要 source 和控制点，就不应因为步骤不同被判错。

## 39.6 `eval_trace`：用半标准化轨迹避免被框架锁死

LangGraph、AutoGen、OpenAI Agents SDK 和自研 Runtime 的原始 Trace 格式不同。评测平台不应直接绑定某一框架，而应在入口归一成最小公共骨架：

```json
{
  "run_id": "run_fin_042",
  "steps": [
    {
      "step_id": "s1",
      "type": "context_pack",
      "inputs": ["turn_001", "schema_finance_v12"],
      "outputs": ["ctxpkg_042"]
    },
    {
      "step_id": "s2",
      "type": "tool_call",
      "tool": "sql_executor",
      "inputs": ["ctxpkg_042"],
      "outputs": ["sql_result_042"],
      "status": "succeeded"
    }
  ]
}
```

常见公共 step type：

```text
context_pack
model_call
tool_call
policy_check
memory_read / memory_write
artifact_write
human_review
handoff
```

评测使用 `eval_trace`，原始 Trace 仍由第38章的观测系统保存。

进一步可以抽取 source graph：

$$
G_{trace}=(V,E)
$$

节点是 Turn、Metric、Schema、Memory、Tool Result、Artifact；边是 reads、generates、references、derives。参考图不必规定完整行动顺序，而可以规定“必须读取哪些 source、禁止哪些 source、哪些依赖必须成立”。

一个简化评分：

$$
SourceGraphScore=
\eta_v\frac{|V_{pred}\cap V_{ref}|}{|V_{ref}|}
+\eta_e\frac{|E_{pred}\cap E_{ref}|}{|E_{ref}|}
-\eta_n Noise(G_{pred})
$$

完整 source graph 标注成本较高，因此可以分层：核心 Golden Set 标完整图；普通 Regression 只标关键 source/禁止 source；线上失败在事故复盘时逐步补充。

**轨迹标准化的目的不是强制所有 Agent 按相同步骤工作，而是让不同实现都能被同一套生产控制点检验。**

## 39.7 公开 Benchmark 怎么用：校准方法，不替代企业准入

*表39-2：公开 Benchmark 的借鉴重点。来源：本书整理。*

| 类型 | 代表 | 可借鉴 | 企业仍需补齐 |
|---|---|---|---|
| Text-to-SQL | WikiSQL、Spider | SQL 泛化与执行评测 | 私有 Metric、权限 |
| 大规模 SQL | BIRD、Spider 2.0 | 复杂 schema / enterprise workflow | 企业语义层和组织流程 |
| 企业 SQL | BEAVER | 私有仓库、领域知识、子任务诊断 | 完整多轮 Agent 轨迹 |
| Agent | AgentBench、WebArena、OSWorld | 工具与环境交互 | 企业数据/审计 |
| Deep Research | DeepResearch Bench、ResearchRubrics | 证据与开放报告 rubric | SQL、权限、Metric |
| Workspace | Workspace-Bench | source/file dependency graph | 数据分析专属契约 |

公开排行榜适合看模型/方案能力趋势，也适合学习 dataset version、runner、submission、leaderboard 的运营方式。企业则应维护私有 leaderboard，将模型、Prompt、Tool、语义层、Policy 和 Runtime 版本放到同一批内部任务上比较。

## 39.8 持续评测平台：Benchmark 要进入发布流水线

一个可运行的持续评测平台至少包含：

```text
Dataset Registry
Eval Runner
Deterministic Evaluators
LLM Judge / Human Review
Trace Adapter
Metrics / Leaderboard
Release Gate
Sample Lifecycle
```

每次 Eval Run 都绑定：

```text
eval_run_id
benchmark_version
model_version
prompt_version
tool_version
semantic_layer_version
policy_version
data_snapshot_version
runtime_version
judge/evaluator_version
```

否则“这次准确率低 2%”无法解释是谁变了。

评测频率也要分层：

- **Smoke Eval**：PR/小改动快速检查；
- **Regression Eval**：Prompt、Tool、Runtime 变更；
- **Safety Eval**：权限/Policy/模型重大变更；
- **Nightly Eval**：固定跨场景趋势；
- **Release Eval**：重大版本完整门禁。

高风险 Safety Set 失败直接阻断，不能被总分拉回。成本和运行时长也应进入 leaderboard；如果质量提升 1% 但成本翻倍，是否发布是产品选择，而不是单纯“分数更高”。

**评测只有真正能阻断发布、指导灰度和触发回滚时，才从报告变成平台基础设施。**

## 39.9 样本生命周期：从线上问题成长为质量资产

Benchmark 会随业务变化。Metric 升级、流程废止、权限改变后，旧样本可能不再适合当前门禁，因此需要状态：

```text
candidate
→ confirmed
→ release_gate / regression / safety
→ observe / needs_update
→ retired
```

每条样本至少记录：来源、业务域、适用版本、Ground Truth 构造依据、EvidenceRef、owner、裁定人、最近通过版本和退役原因。

线上失败、人工驳回、用户修订、审计问题和高成本任务都可以进入 Candidate Pool，但进入正式集前要完成：脱敏、去重、口径确认、数据快照固定、评分规则确认。

退役不是删除。历史样本仍用于解释旧版本，只是不再影响当前发布门禁。

还要防 Benchmark 污染：长期只围绕公开/固定题调 Prompt，会让分数上升而泛化不变。保留隐藏样本，持续吸收真实线上长尾，是维持 benchmark 有效性的关键。

**评测集本身也是生产资产，需要版本、owner、准入、复审和退役，而不是越积越大的静态题库。**

## 本章小结

企业级 DataAgent 评测需要把 Result、Semantic Context、Trajectory、Safety 和 Cost 分开观察。能够确定判断的 SQL、数字、权限和 Evidence 应优先由程序校验，开放式解释和报告再交给 Judge/专家。

Benchmark 按真实任务空间覆盖，而不是靠简单问题堆数量；`eval_trace` 和 source graph 让不同 Agent 实现能够共享控制点评测。公开 benchmark 提供方法，内部 Gold/Regression/Safety 才决定上线。

**成熟的评测体系最终不是告诉团队“模型得了多少分”，而是明确：哪些场景已经可以自动完成，哪些失败会阻断发布，某次改动修复了哪些真实问题，又有没有破坏其它任务。**

## 参考文献

Hendrycks, D. et al. (2021). *Measuring Massive Multitask Language Understanding*. ICLR. https://arxiv.org/abs/2009.03300

Srivastava, A. et al. (2023). *Beyond the Imitation Game: BIG-Bench*. TMLR. https://arxiv.org/abs/2206.04615

Liang, P. et al. (2023). *Holistic Evaluation of Language Models (HELM)*. TMLR. https://arxiv.org/abs/2211.09110

Huang, Y. et al. (2023). *C-Eval*. https://arxiv.org/abs/2305.08322

Li, H. et al. (2023). *CMMLU*. https://arxiv.org/abs/2306.09212

Jimenez, C. E. et al. (2024). *SWE-bench*. ICLR. https://arxiv.org/abs/2310.06770

Liu, X. et al. (2024). *AgentBench*. ICLR. https://arxiv.org/abs/2308.03688

Zhou, S. et al. (2024). *WebArena*. ICLR. https://arxiv.org/abs/2307.13854

Xie, T. et al. (2024). *OSWorld*. https://arxiv.org/abs/2404.07972

Zhong, V., Xiong, C., & Socher, R. (2017). *WikiSQL / Seq2SQL*. https://arxiv.org/abs/1709.00103

Yu, T. et al. (2018). *Spider*. EMNLP. https://arxiv.org/abs/1809.08887

Li, J. et al. (2023). *BIRD*. NeurIPS Datasets and Benchmarks. https://arxiv.org/abs/2305.03111

Lei, F. et al. (2024). *Spider 2.0*. https://arxiv.org/abs/2411.07763

Chen, P. B. et al. (2024). *BEAVER*. https://arxiv.org/abs/2409.02038

Du, M. et al. (2025). *DeepResearch Bench*. https://arxiv.org/abs/2506.11763

Sharma, T. et al. (2025). *ResearchRubrics*. https://arxiv.org/abs/2511.07685

Tang, Z. et al. (2026). *Workspace-Bench 1.0*. https://arxiv.org/abs/2605.03596

Muennighoff, N. et al. (2023). *MTEB*. EACL. https://arxiv.org/abs/2210.07316
