# Part VII 可观测性、评估与成本 · 优化导读

Part VII 回答企业级 Agent 从“能跑”走向“可运营”的五个问题：**发生了什么、质量怎么样、线上是否退化、每个成功任务花多少钱、压力下还能否守住承诺。**

五章不是五套独立平台。Trace 是共同事实底座，离线 Eval 把事实变成发布边界，在线 Judge/反馈发现新问题，成本治理解释资源投入，SLO 再把质量、成本和韧性变成用户承诺和发布纪律。

## 本部分章节

| 章 | 核心问题 | 最重要的工程边界 |
|---|---|---|
| 第38章 Agent 可观测性 | 一次 Run 怎样被还原 | Trace 记录事实链，不复制全部敏感原文 |
| 第39章 DataAgent Benchmark | 怎样证明新版本没有退化 | 结果、语义、轨迹、安全分层评测 |
| 第40章 在线评测与 Judge | 怎样发现真实流量长尾问题 | Feedback 是线索，Judge 是筛查器，不是 Ground Truth |
| 第41章 成本治理与缓存 | 钱究竟花在哪里 | 以业务接受的成功任务为成本单位 |
| 第42章 SLO 与韧性 | 压力下怎样保持可用 | SLO 对象是 Run，降级不能突破安全边界 |

## 一条完整运营闭环

```text
Production Run
  ↓
Trace / Metrics / Cost Events
  ↓
Offline Eval + Online Feedback/Judge
  ↓
Failure Classification
  ↓
Regression / Safety / Stress Samples
  ↓
Fix + Release Gate
  ↓
Gray Release
  ↓
SLO / Error Budget / Cost Validation
  ↓
Continue / Rollback / Freeze
```

## 推荐阅读路径

平台工程和 SRE 建议按 **38 → 42 → 41** 阅读：先有运行事实，再定义可靠性和成本边界。数据智能/模型团队建议按 **39 → 40 → 38** 阅读：先建立 Benchmark，再理解在线样本如何回流以及 Trace 为什么是评测证据来源。

如果只能先建设一项能力，优先把第38章的 Run/Trace/Artifact 关联做稳。没有可回放事实，后面的 Eval、Judge、FinOps 和 SLO 都会各自维护一套不一致的统计口径。

## 本部分统一判断

Agent 平台生产化最容易陷入“多建几个看板”：Trace 一个看板、Eval 一个分数、成本一个账单、SLO 一组红绿灯。这些系统只有围绕同一个 `run_id`、版本和 Artifact 工作，才能真正形成运营能力。

**可运营的 Agent 平台不是“指标更多”，而是任何一次线上变化都能回答：发生在哪条任务链、是否影响质量和安全、花了多少额外成本、是否消耗错误预算，以及下一次发布应继续、降级还是暂停。**