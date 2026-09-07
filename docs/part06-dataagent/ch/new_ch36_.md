# 第36章 数据分析、可视化与报告

---

SQL 和 Python 已经给出数字与计算结果，DataAgent 还没有真正完成任务。业务用户需要的是能拿去讨论、修改、审批和传播的材料：哪些是事实，哪些是推断，哪些建议还需要人确认；每个关键结论又能否点回指标、查询和分析证据。

报告层最容易把严谨的上游链路重新变成“聊天机器人”：模型把数字写成一段流畅文字，图表没有口径，建议没有责任人，用户编辑后 EvidenceRef 被删掉。这样报告看起来完整，却无法进入正式经营流程。

**DataAgent 的报告层不是把查询结果“写得更漂亮”，而是把事实、推断、图表和建议组织成每条关键结论都能回到 EvidenceRef 的可发布业务产物。**

## 36.1 从结果到洞察：事实、推断和建议不是同一种内容

*表36-1：复述、洞察、推断与建议。来源：本书整理。*

| 类型 | 示例 | 证据要求 |
|---|---|---|
| 事实/复述 | 华东运营 GMV 下降 12.3% | 直接来自 SQL/Metric |
| 洞察 | 三个 SKU 贡献下滑差额的 58% | 来自 Python/聚合 Artifact |
| 推断 | 可能与促销结束有关 | 需要额外证据，标注不确定性 |
| 建议 | 品类经理核对促销与补货变化 | 明确责任人、前提和是否需审批 |

模型不能重新计算 58%。SQL/Python 没有产出的数值，报告中就不应出现。

报告还要限制洞察数量。经营会材料通常需要 3–5 条主线结论，而不是把所有 EDA 信号都塞进去。系统的价值是帮助业务收敛重点，而不是展示发现了多少异常。

语言强度应匹配证据：没有促销日历，只能写“可能相关，需确认”，不能写“促销结束导致下滑”。

**事实由工具计算，推断由证据约束，行动由组织负责。把三者写在同一语气里，是报告最常见的责任混淆。**

## 36.2 图表是一种结构化产物，不是图片提示词

图表类型先服务分析意图：趋势用折线，排名/贡献用横向条形，构成用堆叠条，分布用直方图/箱线图，关系用散点。

DataAgent 不应让模型为了“更好看”生成 3D 图、过多颜色或不可比较的视觉编码。更重要的是，图表 spec 中的字段、过滤、聚合、排序和单位都必须来自上游 schema/Artifact。

例如：

```json
{
  "chart_type": "horizontal_bar",
  "data_ref": "artifact://run-1/category-contrib.json",
  "x_field": "gmv_delta",
  "y_field": "category",
  "sort": "gmv_delta_asc",
  "metric": "gmv_ops@2025Q1",
  "title": "华东运营 GMV 下滑品类贡献"
}
```

`chart_renderer` 校验字段和数据引用，再返回 chart Artifact。第48章前端可以负责交互，但不能把图表重新变成无法追溯的模型图片。

图表还需要适应传播。交互页面可以 hover 和下钻，导出 PDF/截图时则应把 Metric、时间范围、单位和数据时间写在图表附近，避免离开系统后上下文消失。

**图表越简洁，背后的数据契约越要完整。没有明确口径和 data_ref 的“漂亮图”，不适合进入经营材料。**

## 36.3 自动 EDA：负责找候选信号，不负责替业务下结论

自动 EDA 可以检测缺失率、异常值、分布偏移、Top 变化和样本量风险。但这些是候选信号，不等于业务洞察。

例如 SKU 空值率上升，可能影响 Top SKU 排名；某门店异常高，可能是促销，也可能是录入问题。DataAgent 可以把这类结果放进“质量提示/待验证线索”，而不是写成已经成立的经营原因。

EDA 输出应包含方法和阈值，例如“该 SKU 低于历史均值 2.4 个标准差”，而不是“AI 发现异常”。方法、参数、输入 hash 和数据范围都应进入 Artifact。

任务级别也不同：普通单指标问数无需自动 EDA；诊断任务可以跑轻量 EDA；订阅式工作台才适合主动异常发现。

严重质量问题还应改变 Run：轻微告警 → 报告脚注；严重异常 → 降级为草稿、等待数据刷新或进入 HITL。

## 36.4 EvidenceRef：报告可信的核心契约

EvidenceRef 将一句结论绑定到真实数据/计算来源。

![图36-1：报告产物与 EvidenceRef 证据链](../../images/part6/ch/ch36-report-evidence-chain.svg)

*图36-1：报告产物与 EvidenceRef 证据链。来源：本书自绘。Alt text：图中展示 SQL 结果、Python artifact、EvidenceRef、图表 spec、报告草稿和 HITL 发布之间的引用关系，强调关键洞察必须保留 artifact、locator、content hash 和指标版本。*

```json
{
  "ref_id": "ev_002",
  "source_tool": "python_sandbox@v1",
  "artifact_id": "df_sku_contrib",
  "locator": "row:sku_id=SKU-A",
  "metric_id": "gmv_ops",
  "metric_version": "2025Q1",
  "content_hash": "sha256:8f3a2b1c"
}
```

自由文本“依据：Python 分析”不够。系统需要能找到具体 Artifact/locator，验证 hash，并展示 Metric 和数据时间。

经营报告可以保持稳定结构：

1. 执行摘要：3–5 条最重要结论，全部带 EvidenceRef；
2. 问题与口径：Question Frame、Metric/version、时间范围；
3. 关键发现与图表；
4. 推断与限制；
5. 建议与责任人；
6. 附录：Run ID、SQL hash、Python hash、freshness、质量告警和证据列表。

**报告正文可以短，证据不能短路。用户平时不打开附录，不代表附录可以不存在。**

## 36.5 用户编辑：表达可以改，事实不能悄悄改

业务负责人一定会编辑报告：改标题、删段落、调整语气、替换图表。平台不应禁止编辑，但应区分“表述字段”和“事实字段”。

- 表述调整：可以自由修改；
- 数字、Metric、时间、证据：修改后必须重新绑定或重新计算；
- 模型生成段落改成新的业务判断：标记为人工补充/人工修改；
- EvidenceRef 被删除但结论仍保留：保存/发布前阻断或提示重新绑定。

审批也绑定具体 report version + artifact hash。用户编辑后，旧审批不应自动覆盖新版本。

报告版本对比最好不仅做文本 diff，还比较 EvidenceRef、图表 data_ref 和关键事实是否变化。语言变更和事实变更对应不同复核强度。

**人工可以拥有最终表达权，但不能让人工编辑把系统已经建立的证据链静默抹掉。**

## 36.6 建议不是自动决策：说明“谁应该进一步做什么”

DataAgent 可以提出行动建议，但不应替业务 owner 做补货、调价、促销等决定。

好建议通常包含：

```text
action_candidate
responsible_role
supporting_evidence
preconditions
risk_level
approval_required
```

例如：“建议品类经理核对 SKU-A 促销结束日、补货和陈列变化；当前只确认了销售下滑贡献，尚未验证促销日历。”

这比“立即恢复促销”更符合 DataAgent 的证据边界。

若平台不知道责任人，应写“需业务 owner 指派”，不能让模型虚构组织角色。建议被采纳、修改或拒绝也应回流 Eval：高驳回可能说明模型过度推断或证据不足，高采纳的重复分析则可以沉淀为 Playbook。

## 36.7 输出评估：SQL 正确率之外，还要评报告是否 grounded

*表36-2：DataAgent 输出评估维度。来源：本书整理。*

| 维度 | 核心检查 |
|---|---|
| 答案 | 数值、排序、Metric、freshness |
| 洞察 | 每条关键结论是否有 EvidenceRef |
| 图表 | 类型是否匹配问题，字段/data_ref 是否合法 |
| 报告 | Run ID、版本、限制、附录是否完整 |
| 交互 | 歧义时是否追问，证据不足时是否降级/拒写 |
| 编辑后版本 | EvidenceRef 是否仍支持最终文本 |

硬校验优先：locator 是否存在、hash 是否一致、Metric 是否匹配、数值是否在 Artifact 中。LLM-as-Judge 可以辅助判断语言清晰度、相关性和是否过度推断，但不能替代精确数值和证据校验。

负样本尤其重要：洞察无 EvidenceRef、chart 字段不存在、模型心算贡献度、把推断写成事实、报告编辑后丢脚注、旧审批用于新版本。这些才是生产中最需要阻断的失败。

线上再看人工修改率、审批驳回率、图表重生成、负面反馈和建议采纳率。SQL 一直正确但报告持续被退回，问题就应定位到表达/证据层，而不是继续调 NL2SQL。

## 36.8 一份可发布报告应该长什么样

“华东下滑”可以形成如下骨架（示例数字仅用于结构说明）：

> **华东区上周运营 GMV 下滑复盘（待 Controller 确认）**  
> Run：`run-8f3a` · Metric：`gmv_ops@2025Q1` · 数据截至：2025-06-14 06:00
>
> **执行摘要**
> - 华东上周运营 GMV 较前周下降 12.3%。[`ev_001`]
> - SKU-A/B/C 合计贡献下滑差额的 58%。[`ev_002`]
> - 日化品类占比变化与主要下滑 SKU 重合；**这是待验证推断**，需结合促销日历确认。[`ev_004`]
> - SKU 字段存在轻微质量告警，SKU 级排序仅供参考。[`ev_005`]
>
> **行动候选**
> - 品类经理核对 SKU-A 的促销结束、补货与陈列变化；补充证据后再判断是否调整策略。

正式附录再保留 SQL/Python hash、Artifact、Metric、质量和审批记录。报告读者可以先读结论，审计和数据人员则能沿证据继续展开。

## 36.9 报告生命周期：草稿、复核、发布、修订和撤回都要有状态

报告一旦进入会议、邮件或跨部门流转，就不是聊天消息。建议至少区分：

```text
draft → needs_review → approved → published
                     ↘ rejected
published → superseded / withdrawn
```

对外/正式经营报告默认进入 HITL。审批人确认的是具体版本与 EvidenceRef，不是一个会持续变化的 URL。

数据回补、Metric 变化、分析代码修复或业务争议都可能要求重新生成。旧报告不能静默覆盖，应保留原版本并标记 superseded/withdrawn，必要时通知原接收者。

争议也应结构化分类：

- 数据/口径错 → 回语义层/查询重新计算；
- 图表误导 → 改 chart spec；
- 把相关写成因果 → 调整解释与 Eval；
- 建议越权 → 改为待审批行动项；
- 敏感字段 → 安全/发布链处理。

**报告可修订不等于历史可以被改写。企业真正需要的是“新版本纠正旧结论，同时旧版本仍能解释当时为什么发布”。**

## 36.10 用户反馈是报告链路的输入，不只是点赞埋点

业务用户的修改、删除、驳回和补充比单纯 thumbs-up 更有信息量。反馈应按类型回写：

- 数字/口径修正 → 语义层、SQL、数据质量；
- 洞察证据不足 → Python/分析链；
- 图表不合适 → chart template；
- 语言/结构调整 → 报告模板；
- 建议被驳回 → 行动边界/业务规则；
- 发布被拒 → HITL/Policy。

反馈至少关联 report version、EvidenceRef、修改前后内容、反馈人和是否影响事实。正式报告的事实争议应进入回归样本，不能只留在文档评论中。

传播行为也有价值：哪些图表经常被复制，哪些段落总被删，哪些报告持续被追问，都能帮助模板和 Playbook 沉淀。

## 本章小结

报告层把 SQL/Python 的计算结果转成可以被业务阅读、复核和发布的产物。模型负责组织语言，图表和关键数值必须来自结构化 Artifact；事实、推断与建议使用不同证据强度和责任边界。

EvidenceRef 是整章的核心契约：每条关键洞察都能回到 tool、artifact、locator、Metric 和 hash。人工编辑、审批、修订和撤回都围绕具体 report version 进行，不能破坏这条证据链。

**一份 DataAgent 报告真正“生成成功”的标志，不是 Markdown/PDF 已经产出，而是业务用户能快速读懂，复核人员能沿证据验证，组织又能明确知道哪些内容可以发布、哪些判断仍需人承担责任。**

## 参考文献

Dibia, V. (2023). LIDA: A tool for automatic generation of grammar-agnostic visualizations and infographics using large language models. *ACL Demo*.

Tang, Z., et al. (2025). *LLM/Agent-as-Data-Analyst: A survey*.

Wilke, C. O. (2019). *Fundamentals of Data Visualization*. O'Reilly.

Huo, N., et al. (2026). *BIRD-INTERACT*. ICLR 2026.

Es, S., et al. (2024). *RAGAS: Automated evaluation of retrieval augmented generation*. EACL.

Vega-Altair Contributors. (2024). *Vega-Lite*.
