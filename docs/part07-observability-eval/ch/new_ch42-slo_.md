# 第42章 SLO 管理、限流与系统韧性

---

周一早高峰，销售经理批量生成经营周报。入口 API 仍然返回 `200`，监控也没有显示服务宕机，但用户迟迟拿不到报告，只能不断点击“重新生成”。从接口看系统还活着，从业务看已经不可用。

Agent 平台的可靠性对象不能只是一条 HTTP 请求，而应是一次 Run：用户是否及时知道任务已开始，最终能否拿到可用结果，失败后能否恢复，高峰降级时是否仍守住权限与审批，单位任务成本是否仍在合理范围。

**Agent 平台的“可用”不是接口返回 200，而是用户的 Run 在可接受时间、质量、成本和安全边界内达到可用终态。**

## 42.1 SLI、SLO 与 SLA：先从用户承诺定义任务目标

SLI（Service Level Indicator）是实际测量值；SLO（Service Level Objective）是内部服务目标；SLA（Service Level Agreement）则更接近对客户/业务方的正式承诺。

```text
SLI：过去 7 天任务成功率 98.6%
SLO：任务成功率 >= 98%
SLA：正式对外承诺及违约处理
```

Agent SLO 不应直接从基础设施指标反推。先问用户如何使用和等待，再定义工程指标。

*表42-1：不同 Agent 场景的等待语义。来源：本书整理。*

| 场景 | 用户真正关心 | SLO 应关注 |
|---|---|---|
| 交互式问数 | 快速看到系统响应，最终答案可用 | 首响应、最终完成、质量 |
| 长报告 | 离开页面任务不丢，可查进度 | 检查点、恢复、通知、Artifact |
| 后台批处理 | 截止时间前低成本完成 | 吞吐、deadline、失败成本 |
| 高风险审批 | 不越权、不绕过人工 | 审批完整、安全、审计 |

完整报告可以需要 10 分钟，但用户可能要求 5 秒内看到“任务已受理/正在查数”；后台批任务不必秒级，却必须在早上 8 点前完成。

**SLO 定义的是“用户可以依赖平台做到什么”，而不是基础设施团队最容易采集什么指标。**

## 42.2 Objectives 与 Guardrails：稳定性不能靠牺牲质量和安全换来

一个 DataAgent SLO 可以同时有优化目标和不可让步的护栏：

```yaml
slo:
  name: finance_dataagent_interactive
  objectives:
    first_response_p95_ms: 5000
    final_answer_p95_ms: 60000
    run_success_rate: ">= 98%"
    average_cost_per_successful_run_usd: "<= 0.20"
  guardrails:
    safety_violation_rate: "0"
    regression_set_pass_rate: ">= 97%"
    human_handoff_rate: "<= 5%"
```

例如切换小模型让 P95 降低 30%，但 Safety Set 出现越权样本，就不是可靠性优化。减少上下文让平均成本下降，但报告证据丢失，同样不能算 SLO 改善。

常见目标包括：

- 首响应时间；
- 最终完成时长；
- Run 成功率；
- Artifact/恢复可用性；
- 单位成功任务成本。

常见硬护栏包括：

- 越权/敏感泄漏为 0；
- 高风险审批完整；
- 核心 Regression/Safety 不退化；
- 数据质量限制不能被降级隐藏。

## 42.3 SLO 指标必须沿 Run 拆到 Step

![图42-1：SLO、错误预算与降级闭环](../../images/part7/ch/ch42-slo-degradation-loop.svg)

*图42-1：SLO、错误预算与降级闭环。来源：本书自绘。Alt text：图中展示任务 SLO、观测指标、错误预算、保护动作和长任务恢复之间的闭环，说明稳定性治理如何从线上信号进入发布规则和运行时保护。*

只看总延迟会掩盖根因。一次 60 秒 Run 可能是模型推理 50 秒，也可能排队 45 秒、SQL 5 秒、报告 10 秒。两者修法完全不同。

*表42-2：任务链路指标。来源：本书整理。*

| 层级 | 典型指标 | 主要用途 |
|---|---|---|
| 入口 | 受理成功、限流拒绝、重复请求 | 网关保护与公平性 |
| Run | 成功、取消、可重试/不可重试失败 | 判断任务是否真正完成 |
| Step | 模型/Tool/Artifact 延迟和成功率 | 定位瓶颈 |
| 质量 | Regression、在线抽样、人工接管 | 防止快速但低质量 |
| 风险 | Policy、审批、越权、脱敏 | 安全门禁 |
| 成本 | 单成功任务、失败成本、缓存节省 | 防止无限资源换成功率 |

这些指标都应可按 `tenant_id`、`agent_id`、`run_id`、模型、Prompt、Tool、语义层和 Policy 版本切片。否则“P95 变差”仍然无法定位是谁变了。

**可靠性看板负责发现退化，Trace 负责把退化还原到任务链。SLO 没有 Trace 支撑，最终只能停在平均指标。**

## 42.4 错误预算：把“最近不稳定”变成可执行的发布规则

如果一周有 10 万个 Run，成功率 SLO 为 98%，允许的普通任务失败预算为：

$$
Budget_{failure}=N_{runs}(1-SLO_{success})=2000
$$

Agent 平台还可以分别维护：可用性预算、延迟预算、质量退化预算和成本超支预算。安全预算通常应为 0：越权或未审批高风险动作不应被平均到普通失败中。

*表42-3：错误预算与发布动作。来源：本书整理。*

| 状态 | 运行治理 | 发布治理 |
|---|---|---|
| 预算充足 | 正常监控 | 正常灰度/实验 |
| 消耗过快 | 下钻失败 Trace、收紧保护 | 暂停高风险变更 |
| 预算耗尽 | 启动复盘、限流/降级 | 只允许修复性发布 |

严重失败还可以加权，但不能让总分掩盖 Safety 事件。

错误预算的意义，是在可靠性和迭代速度之间建立共同语言：系统稳定时可以更积极试验；已经不稳定时，先修复而不是继续叠加模型、工具和 Prompt 变化。

**错误预算让“能不能继续发布”由运行证据决定，而不是事故会上的主观感受。**

## 42.5 三道保护线：限流、熔断与降级

**限流**解决入口放大：控制用户/租户并发、QPM、长任务队列和重复请求。

**熔断**解决下游放大：SQL、模型、外部 API 明显不健康时，暂停继续打流量，并在冷却后小流量探测。

**降级**解决能力缺口：完整功能暂不可用时，提供安全、可解释的替代。

*表42-4：三类机制的差异。来源：本书整理。*

| 机制 | 主要保护 | 典型动作 |
|---|---|---|
| Rate Limit | 系统入口和租户公平 | 排队、拒绝新低优先级任务 |
| Circuit Breaker | 不健康下游 | 暂停调用、切合格备用、稍后探测 |
| Degradation | 用户体验/任务可继续性 | 摘要、异步、关闭非关键 Tool、转人工 |

同一用户在 5 分钟内重复点击同一报告，不应新建多个 Run。平台根据任务指纹返回已有 `run_id` 和进度，可以直接消除一种典型放大效应。

高峰期也可以先返回核心摘要，完整 PPT 转异步；Chart Beautify 暂停，核心数据分析继续；低风险任务切换已验证小模型。

**限流、熔断和降级不是三套独立功能，而是阻止入口、下游和能力缺口把局部故障放大的三道防线。**

## 42.6 降级有底线：不能为了“可用”绕过权限与证据

最危险的韧性策略，是主路径失败后自动走一个不受控备用路径。例如：

- SQL 主服务超时 → 直连一个无行权限的副本；
- 强模型不可用 → 小模型继续执行高风险写操作；
- 报告生成慢 → 省略 EvidenceRef；
- 审批系统异常 → 默认放行。

这些都不属于降级，而是安全边界失效。

一个保护配置可以明确：

```yaml
protection_policy:
  rate_limit:
    per_user_concurrent_runs: 3
    per_tenant_qpm: 500
    duplicate_task_window_seconds: 300
  circuit_breaker:
    sql_executor:
      open_when_error_rate_gt: 0.30
      window: 2m
      cool_down: 5m
  degradation:
    high_load:
      disable_optional_tools: [chart_beautify, ppt_theme_render]
      prefer_async: true
    policy_sensitive:
      mode: read_only
      require_human_approval: true
```

优先级始终是：**安全/权限 → 核心业务事实 → 容量 → 非关键体验。**

用户也要看到降级是什么：“完整报告预计 12 分钟后完成，先返回关键指标摘要”，比“服务繁忙”更能减少重复提交。

## 42.7 长任务：Run 生命周期必须与 HTTP 连接解耦

报告、批分析和 HITL 可能持续数分钟或数小时，不能依赖一条 HTTP/SSE 连接存活。

可靠长任务需要：

```text
run_id
queue
state machine
checkpoint
progress API / event
idempotency key
artifact refs
cancel / retry semantics
```

状态可以是：

```text
submitted → queued → running → waiting_approval → running → succeeded
                    ↘ retryable_failure → queued
                    ↘ terminal_failure
                    ↘ cancelled
```

这里的细粒度 queue 状态不一定都要暴露成第22章 Run 六态，可以作为业务/Tool 子状态映射。

Checkpoint 只保存恢复所需事实：已完成哪些 Step、哪些副作用已经提交、Artifact 在哪里、下一步从哪里继续、恢复时要重新校验什么权限和数据版本。

写邮件、改数据库、创建工单必须用 `idempotency_key`，防止 Worker 重启或回调重放造成重复副作用。

**长任务可靠性不是“进程一直不死”，而是进程、连接甚至执行器都可以变化，任务仍能在同一 Run 上恢复且不会重复执行业务动作。**

## 42.8 容量规划：一次入口请求会被多步 Agent 放大

Agent 的真实下游工作量可以粗略估算为：

$$
Workload=
QPS_{entry}\times AvgStepsPerRun\times AvgCallsPerStep\times RetryFactor
$$

入口 10 QPS，平均 6 Step，每 Step 1.5 次下游调用，重试系数 1.2，就可能形成 108 QPS 的下游调用，还未计 token 长度和 Artifact。

*表42-5：不同资源域的瓶颈。来源：本书整理。*

| 资源域 | 主要瓶颈 | 关注信号 |
|---|---|---|
| 模型 | token 吞吐、并发、KV/cache、排队 | 模型 P95、超时、token |
| Tool | SQL、Python、外部 API 配额 | Tool 成功、熔断、重试 |
| 队列 | 积压、优先级反转、Worker 心跳 | queue time、deadline |
| 存储 | Trace、Artifact、Eval 写入 | I/O 延迟、审计完整 |
| Eval | Judge/回归抢占生产资源 | Eval 队列与成本 |

不能只扩模型。模型扩容后 SQL、图表渲染、存储或队列可能变成新瓶颈。不同任务也应有不同优先级：交互式用户请求 > 核心长任务 > 普通异步 > 夜间批评测。

缓存命中下降也会突然放大容量，因此第41章的缓存同时是 FinOps 和 SLO 变量。

## 42.9 压测和故障注入要模拟真实任务链

传统压测只打 `/run` 入口，最多证明网关能收请求。Agent 压测还要模拟：

- Context 变长；
- 模型排队/超时；
- SQL 变慢；
- Tool 返回空/错误；
- 缓存大面积失效；
- 报告 Artifact 写入变慢；
- HITL 积压；
- 用户重复提交；
- Worker 重启和 Checkpoint 恢复。

主动让某个下游失败，可以验证限流、熔断、降级、幂等和错误预算是否真正生效。

压力解除后还要清理：高峰期积压的低优先级 Run、降级缓存、临时 Artifact 和延迟通知不能继续制造过期结果。

**韧性不是事故时临时点几个开关，而是平时已经用真实任务链验证过“局部失败发生时，系统会怎样一致地退化和恢复”。**

## 42.10 SLO 违约后的发布冻结与业务沟通

SLO 违约不应只触发告警。可以建立 Gate：

- P95 持续超阈值 → 暂停相关模型/流式实验；
- 核心任务成功率低 → 暂停功能扩流；
- Safety Set 失败 → 立即阻断；
- 人工接管异常上升 → 暂停高风险自动化；
- 成本预算异常 → 限制低价值任务和高成本 Eval。

冻结范围不必是全平台。哪个能力影响 SLO，就冻结相关模型路由、工具、Prompt 或流量扩大。

解冻需要明确证据：问题根因、修复版本、Regression/Stress 通过、灰度观察、业务 owner 对用户承诺的确认。

SLO 调整也需要业务参与。把报告 deadline 从 10 分钟放到 30 分钟，对工程看是队列参数，对业务可能意味着会议前拿不到材料。应使用真实任务样本说明变更后的等待、降级和恢复体验。

事故沟通则告诉用户：哪些任务受影响、是否需要重试、当前 Artifact 是否可信、完整结果何时补发。沟通应来自 Trace/Run 状态，而不是运营人员现场猜测。

**SLO 的最终作用，是把可靠性从 SRE 看板上的数字变成跨业务、平台、安全和 FinOps 都能理解的运行承诺与发布纪律。**

## 本章小结

Agent SLO 应围绕 Run 定义，而不是入口 API。交互式任务、长报告、批处理和审批有不同等待语义；首响应、最终完成、质量、安全和单位成本共同构成任务级可靠性。

错误预算控制发布节奏；限流、熔断和降级分别阻止入口、下游和能力缺口放大问题；长任务通过队列、Checkpoint 和幂等从 HTTP 生命周期中解耦。任何降级都不能绕过 Policy、Evidence 和 HITL。

**一个有韧性的 Agent 平台并不承诺“每个依赖永远不失败”，而是承诺依赖变慢、变错或暂时不可用时，任务仍会以用户可理解、业务可接受、平台可恢复的方式进入确定状态。**

## 参考文献

Beyer, B. et al. (2016). *Site Reliability Engineering*. O'Reilly. https://sre.google/sre-book/table-of-contents/

Beyer, B. et al. (2018). *The Site Reliability Workbook*. O'Reilly. https://sre.google/workbook/table-of-contents/

Envoy Proxy. (n.d.). *Rate limit filter documentation*. https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/rate_limit_filter

Kubernetes. (n.d.). *Horizontal Pod Autoscaling documentation*. https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
