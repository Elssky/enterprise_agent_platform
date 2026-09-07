# Part VI DataAgent 主线深潜 · 优化导读

Part VI 把前面分散的模型、数据、知识和 Agent Runtime 能力收拢到一条真正面向业务的数据任务链：**用户问题先被结构化，再绑定正式业务口径；SQL 负责可信取数，Python 负责受控分析，报告层负责把结论组织成带证据的业务产物。**

这一部分统一使用“上周华东区销售下滑，主要 SKU 是哪些？和品类结构有没有关系？”作为贯穿案例，六章不是六套独立技术，而是同一个 `run_id` 里的连续步骤。

## 本部分章节

| 章 | 核心问题 | 最重要的工程边界 |
|---|---|---|
| 第32章 DataAgent 产品形态 | DataAgent 到底比 NL2SQL 多什么 | 自然语言自由，底层 Question Frame 结构化 |
| 第33章 语义层工程 | 怎样避免“SQL 对、业务口径错” | Metric/View/Glossary 约束模型可见事实 |
| 第34章 NL2SQL 工程化 | SQL 怎样安全生成和执行 | 生成、校验、执行、解释分层；权限不可自修复 |
| 第35章 Text-to-Python | SQL 之后怎样做灵活分析 | Python 只读受控 Artifact，运行在隔离沙箱 |
| 第36章 可视化与报告 | 怎样把结果变成可信业务材料 | 每条关键结论绑定 EvidenceRef |
| 第37章 对标与生态 | 自研、采购、开源怎样组合 | 借组件，不丢 Runtime、口径和证据主权 |

## 一条完整 DataAgent Run

```text
用户问题
  ↓
Question Frame
  ↓
Semantic Layer / Schema Linking
  ↓
Read-only NL2SQL
  ↓
Result Artifact
  ↓
Python Sandbox（需要时）
  ↓
Chart / EvidenceRef / Report
  ↓
HITL / Publish
  ↓
Trace + Eval + Feedback
```

上游每一步都为下一步提供结构化证据，而不是只传一段自然语言：Metric 带版本，SQL 带 hash，数据结果带 Artifact，Python 带输入/代码 hash，报告结论带 EvidenceRef。

## 推荐阅读路径

如果目标是先搭可信问数，优先读 **32 → 33 → 34**；如果还要支持诊断和经营报告，再读 **35 → 36**；第37章适合在做技术选型、自研/采购边界或平台路线时阅读。

Part V 已经定义 Runtime、Registry、Planner、Memory 和 HITL，本部分不再重复这些底座。DataAgent 的重点是如何**消费**这些能力，而不是自己再建一套数据专用 Runtime。

## 本部分统一判断

DataAgent 最容易被高估的是自然语言和 SQL 生成能力，最容易被低估的是业务语义和证据链。真实业务并不满足于“查到了一个数”：用户会追问这个数怎么算、为什么有权限看到、数据截止到几点、推断有没有依据、报告能不能直接转发。

**因此，DataAgent 的成熟度最终不由“能问多少数据”决定，而由同一个业务问题能否从口语、口径、查询、分析一直走到可复核报告，并在任何一步不确定时安全停下来决定。**