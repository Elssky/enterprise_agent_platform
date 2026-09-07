# 第41章 成本治理与缓存优化

---

Agent 账单异常时，最容易做的动作是换便宜模型；最常见的误判也是把所有成本都归给模型单价。一次真实 Run 可能包含多轮 Planner、长上下文、SQL、Python、检索、报告生成、Judge 和重试。便宜模型如果让工具失败和人工接管增加，单位成功任务成本反而可能更高。

成本治理首先要回答“钱花在哪一条任务链上”，然后才讨论模型路由、缓存和预算。优化也不能只证明费用下降，还要证明质量、安全和用户体验没有被转移成新的隐性成本。

**Agent 成本治理的单位应该是“一个被业务接受的成功任务”，而不是一次模型调用。**

## 41.1 先把成本贴回 Run 和 Step

一次 Run 的成本可以粗略拆成：

$$
Cost_{run}=
\sum_i Cost_{model_i}
+\sum_j Cost_{tool_j}
+Cost_{retrieval}
+Cost_{storage}
+Cost_{eval}
+Cost_{retry}
$$

外部模型 API 还可以拆成输入/输出 token 与缓存折扣：

$$
Cost_{model}=P_{in}T_{in}+P_{out}T_{out}-Discount_{cache}
$$

自建模型则更多表现为 GPU/NPU 时间、显存、吞吐、利用率和运维成本，治理逻辑仍然一样：每一次 Run 为什么花这些资源？

![图41-1：从一次 Run 看 Agent 成本流向](../../images/part7/ch/ch41-01.png)

*图41-1：从一次 Run 看 Agent 成本流向。来源：本书自绘。Alt text：一次 Run 的成本被拆解到模型调用、上下文 token、重试、工具执行等环节，每段标注占比，箭头汇向总成本，体现成本可归因到具体环节。*

成本事件至少要关联：

```json
{
  "tenant_id": "tenant_finance",
  "agent_id": "dataagent_finance",
  "run_id": "run_cashflow_042",
  "step_id": "step_sql_generate",
  "trace_id": "trace_cashflow_042",
  "cost_type": "model_call",
  "model": "model:v4",
  "input_tokens": 8420,
  "output_tokens": 620,
  "cache_hit_tokens": 5100,
  "estimated_cost_usd": 0.018,
  "prompt_version": "finance:v12",
  "semantic_layer_version": "finance:v18"
}
```

这样第38章的 Trace、第39章的 Eval 和 FinOps 才能看同一条事实。

**成本归因和可观测性不是两套系统：Trace 解释任务怎么跑，成本事件解释同一条路径每一步花了多少。**

## 41.2 真正有用的是单位任务成本，而不是月底总账单

总金额用于财务结算，工程治理更需要：

*表41-1：成本指标与诊断意义。来源：本书整理。*

| 指标 | 回答什么问题 | 典型动作 |
|---|---|---|
| 单位成功任务成本 | 完成一个可用任务平均花多少 | 路由、缓存、流程优化 |
| 失败成本占比 | 多少费用花在超时、错误、回滚 | 修 Tool/重试/状态机 |
| 缓存节省 | 哪些稳定上下文/结果真正复用 | 调整缓存键与生命周期 |
| 高成本 Step | 钱集中在哪一段 | 上下文压缩、异步、工具重构 |
| 成本-质量关系 | 多花的钱是否换来价值 | 配合 Eval/用户反馈决策 |

如果 30% 成本来自 SQL 连续修复，换更便宜模型可能只是让重试更多；如果强模型显著降低高价值报告的人工返工，单次调用贵也可能是合理的。

因此更值得优化的是：

$$
CostPerAcceptedTask=
\frac{TotalCost}{N_{accepted\ tasks}}
$$

业务“接受”可以按场景定义为报告批准、SQL 被保存、任务成功并通过质量门禁等。

## 41.3 模型路由：强模型用在真正需要的地方

任务不必共用一个模型。指标解释、格式整理、轻量分类可以用小模型；复杂财务归因、高风险报告、跨源推理可以使用强模型并增加 Eval/HITL。

路由可以同时考虑：

$$
Utility(model,task)=
\alpha Quality-
\beta Cost-
\gamma Latency-
\delta Risk
$$

这个式子不是要求线上真的计算一个神奇总分，而是强调**风险不是模型价格可以交换掉的变量**。高风险任务的安全/权限可能是硬门禁。

一个路由配置可以显式写：

```yaml
routes:
  - task_type: metric_explanation
    risk: low
    model: small_model
    fallback: strong_model

  - task_type: root_cause_analysis
    domain: finance
    risk: high
    model: strong_model
    require_trace: true
    require_eval: true
```

路由调整要跑 Regression/Safety，再小流量灰度。只看到平均成本下降而不看失败、重试和人工接管，很容易误判收益。

**模型路由不是“能小就小”，而是在任务价值和风险允许的范围内，把推理预算分配给最需要它的步骤。**

## 41.4 缓存不是一个开关：不同层复用的是不同对象

![图41-2：Agent 平台的多层缓存结构](../../images/part7/ch/ch41-02.png)

*图41-2：Agent 平台的多层缓存结构。来源：本书自绘。Alt text：自上而下多层缓存，结果缓存、语义缓存、Prefix Cache、模型 KV Cache，每层标注复用对象与命中条件，箭头表示请求逐层尝试命中以降本。*

*表41-2：Agent 常见缓存。来源：本书整理。*

| 缓存 | 复用对象 | 适合 | 主要风险 |
|---|---|---|---|
| Prompt / Context cache | 系统提示、ToolSpec、schema、指标字典 | 稳定长前缀 | 版本变化后仍复用 |
| Prefix/KV cache | 模型前缀计算 | 自建/支持缓存的推理服务 | 前缀不稳定、命中低 |
| Result cache | 确定 SQL/说明/Artifact | 数据快照固定的低风险请求 | 过期、跨权限 |
| Semantic cache | 相似问题的模板、路径、部分结果 | 高频同义问法 | 语境相似但业务条件不同 |

自建模型和外部 API 的缓存重点不同。自建侧更关注 KV、批处理、吞吐和显存；外部 API 更关注稳定前缀、供应商缓存策略、token 计费。业务 Agent 不应感知供应商细节，模型网关负责把逻辑 Context Package 转成有利于各供应商缓存的请求格式。

稳定内容放前面、动态字段放后面；Tool 列表和 schema 序列化顺序应稳定，避免请求 ID、当前时间等高变化内容破坏可缓存前缀。

## 41.5 缓存键首先是权限和版本契约

企业缓存不能只用“问题文本 hash”。至少要考虑：

```json
{
  "tenant_id": "tenant_finance",
  "role": "finance_manager",
  "prompt_version": "finance:v12",
  "tool_version": "sql:v5",
  "semantic_layer_version": "finance:v18",
  "policy_version": "policy:v7",
  "data_snapshot": "warehouse:2026-06-09",
  "question_signature": "..."
}
```

用户问题字面相同，但租户、角色、数据快照、Metric 或 Policy 不同，就不能直接复用最终结果。

缓存失效应尽可能由事件/版本驱动：数据补数 → 数据结果缓存失效；Metric 改版 → 语义/SQL 模板缓存失效；权限变化 → 角色/用户缓存失效；Prompt/模型变化 → 生成结果缓存重新验证。

固定 TTL 只能作为兜底，不应成为企业数据缓存唯一失效机制。

**缓存命中率不是越高越好；权限、版本和数据新鲜度比相似度更重要。**

## 41.6 语义缓存：优先复用中间能力，而不是高风险最终答案

语义命中可以表示为：

$$
CacheHit=
Similarity(q,q')>\tau_s
\land Fresh(data)
\land PolicyAllowed(user,result)
$$

后两个条件通常比向量相似度更重要。

*表41-3：适合复用的对象。来源：本书整理。*

| 对象 | 风险 | 推荐策略 |
|---|---|---|
| 指标定义、字段说明、公开 FAQ | 低 | 版本/权限一致时可直接复用 |
| SQL 模板、图表配置 | 中 | 复用模板，重新执行查询 |
| 分析计划/归因路径 | 中高 | 作为候选，重新读取证据 |
| 最终结论/正式报告 | 高 | 默认重新验证；仅完整快照一致时考虑复用 |

DataAgent 更值得缓存的是已验证的**中间能力**：Metric 解释、SQL 模板、schema linking 候选、分析路径、固定图表 spec，而不是昨天的一段结论。

如果缓存命中后用户点踩、Judge 认为 Evidence 不足或 Safety 出问题，不仅删除这一条结果，还要复盘相同模板和路由规则。

## 41.7 预算控制：在执行前决定怎样花钱

预算不能等月底才看。Run 开始和关键 Step 前都可以估算：上下文 token、模型调用、SQL 扫描、Python 资源、Judge/报告等。

预算可按租户、用户、Agent、任务、项目、时间周期配置：

```yaml
budget_policy:
  tenant_id: tenant_finance
  monthly_usd_limit: 5000
  per_run_token_limit: 50000
  warning_threshold: 0.8
  actions:
    - when: monthly_usage_ratio > 0.8
      action: notify_admin
    - when: estimated_tokens > 30000
      action: summarize_context
    - when: estimated_cost_usd > 2.0
      action: require_approval
    - when: monthly_usage_ratio > 1.0
      action: block_low_priority_tasks
```

预算动作不只有 allow/deny：

- 压缩非关键上下文；
- 切换合格的小模型；
- 降低非关键 Judge 抽样；
- 将长报告转异步；
- 限制检索/工具范围；
- 高成本高价值任务要求审批；
- 超限时阻断低优先级任务。

用户需要知道发生了什么。例如“完整报告成本较高，已转为异步”“当前可先返回核心指标摘要”，比突然报 quota error 更可用。

**好的预算控制更像调度器：在价值、风险和资源之间选择可接受路径，而不是一把到月底才落下来的限额刀。**

## 41.8 降本是否成立，要和质量、安全、延迟一起验收

降本发布条件可以表达为：

$$
AllowedOptimization=
Quality\ge Q_{min}
\land Safety=pass
\land Latency\le L_{max}
\land CostReduction>\epsilon
$$

换模型、减少上下文、提高缓存、减少重试、降低 Judge 抽样都可能伤害质量，因此要跑离线 Regression/Safety，再在线灰度。

典型误区：

- 小模型单价下降，但 SQL 错误和重试增加；
- 缓存命中率提升，但过期答案导致追问增加；
- Context 压缩更激进，却丢 Evidence；
- Judge 抽样减少，低风险省钱，高风险问题也漏检；
- 长任务转异步降低高峰成本，但前端没有清晰反馈，用户重复提交。

成本看板应联合显示用户修订、人工驳回、Judge/Regression、安全和 SLO。省下的钱如果只是转移到人工团队，不算真正优化。

## 41.9 成本异常如何复盘：从“模型太贵”回到具体任务

一个实用的异常复盘顺序：

1. 找 top 成本租户/Agent/任务；
2. 拆模型、上下文、Tool、重试、Eval、存储；
3. 看失败成本和人工接管；
4. 与版本/缓存变化对齐；
5. 抽代表 Run 回放；
6. 决定是路由、缓存、Prompt、Tool、数据预聚合还是产品范围问题。

例如现金流归因成本激增，Trace 发现：稳定 schema 每次重复进入长 Context，同时 Join Key 错误导致 SQL 重试。更好的动作是稳定前缀缓存 + 改 Tool 错误反馈/语义 Join，而不是第一步就换低价模型。

高成本还可能暴露结构问题：报表每次扫描原始明细，说明数据平台需要预聚合；Python 总拿大对象分析，说明应下推数据库；低价值任务长期走深度 Agentic Workflow，说明产品默认配置过重。

异常台账至少记录 owner、受影响任务、版本、根因、策略动作、质量验证和复查时间。FinOps 的价值不是催团队少花钱，而是推动平台把“为什么贵”转成可修复的工程事实。

**成本异常如果无法落到具体 Run 和具体 Step，最终只能围绕模型单价争论；能落到任务链后，很多降本动作其实是可靠性和架构优化。**

## 本章小结

Agent 成本由整条任务链共同决定。模型、上下文、Tool、检索、重试、Artifact 和 Eval 都应通过 Run/Step 成本事件归因。工程治理更应关注单位成功任务成本、失败成本和成本-质量关系，而不是月底总金额。

模型路由按任务风险和价值分配推理预算；缓存按 Prompt、KV、结果和语义分层，缓存键必须包含租户、权限、版本和数据快照；预算控制在执行前介入，并为用户提供可解释的降级路径。

**成本优化只有在质量、安全和 SLO 都没有出现不可接受退化时才成立。真正成熟的 FinOps，不是把每次模型调用压到最低价，而是让每类业务任务以可解释的资源投入获得值得的结果。**

## 参考文献

LiteLLM. (n.d.). *Documentation*. https://docs.litellm.ai/

GPTCache. (n.d.). *Documentation*. https://gptcache.readthedocs.io/

FinOps Foundation. (n.d.). *FinOps Framework*. https://www.finops.org/framework/

OpenTelemetry. (n.d.). *Metrics documentation*. https://opentelemetry.io/docs/concepts/signals/metrics/
