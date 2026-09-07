# 第32章 DataAgent 产品形态

---

DataAgent 是把自然语言问题、可信数据、分析工具和业务交付串成一条任务链的数据 Agent。用户看到的是“问数—追问—分析—报告”，平台真正要管理的则是 Question Frame、语义层、SQL、Python、Artifact、审批和 Trace。

用户问：“上周华东区销售相对前周明显下滑，主要 SKU 是哪些？和品类结构有没有关系？”只做 NL2SQL，系统可能很快生成一条查询；生产级 DataAgent 还要先确认“销售”是哪套指标、“华东”是哪一级组织、“上周”按哪种业务周，再判断问题是查数还是诊断、是否需要 Python 做贡献度分析，并把最终数字绑定到指标版本和数据时间。

**DataAgent 的产品边界不是“能不能把自然语言变成 SQL”，而是能否把问题定义、可信取数、分析、报告和人工责任放进同一条可回放的数据任务链。**

## 32.1 DataAgent 不等于 NL2SQL

NL2SQL 是 DataAgent 的核心能力之一，却只覆盖“把问题转成查询”这一小段。企业问数更常见的失败是口径错、权限错、上下文丢失、复杂分析被硬塞进 SQL，或最终报告没有证据。

*表32-1：只做 NL2SQL 与生产级 DataAgent 的差异。来源：本书整理。*

| 环节 | 只做 NL2SQL | 生产级 DataAgent |
|---|---|---|
| 问题理解 | 模型直接猜字段和指标 | 先形成 Question Frame |
| 口径绑定 | Prompt 中写说明 | 绑定语义层 Metric + version |
| 执行 | SQL 直接运行 | Registry + Policy + 只读执行器 |
| 多轮追问 | 每轮重新理解 | Working Memory 继承已确认 Frame |
| 复杂分析 | 尽量写进一条 SQL | SQL 取数后交 Python/分析 Tool |
| 交付 | 数字或表格 | 图表、EvidenceRef、报告与审批 |

DataAgent 可以理解为三层叠加：

1. **问数链路**：理解问题、绑定口径、生成查询、执行并解释；
2. **分析链路**：在受控结果集上做统计、拆解、对比和归因；
3. **交付链路**：把结果组织为图表、报告、审批对象和可回放 Artifact。

指标定义、新鲜度、血缘和数据权限仍由数据平台/语义层掌握；Runtime、Registry、Policy 和 Trace 由 Agent 平台提供；DataAgent 应用负责问题分型、领域策略、交互和报告模板。

**模型可以帮助理解业务语言，但不能自行创造指标口径、数据权限或证据来源。**

## 32.2 ChatBI、BI Copilot 与 DataAgent

三类产品都可以有自然语言入口，但工程边界不同。

*表32-2：ChatBI、BI Copilot 与 DataAgent。来源：本书整理。*

| 形态 | 典型交互 | 数据范围 | 更适合 |
|---|---|---|---|
| ChatBI | 对话查数 | 单库/单主题 | 轻量自助查询 |
| BI Copilot | 在 BI 内改筛选、图表、解释看板 | 当前数据集/报表 | 已有 BI 用户提效 |
| DataAgent | 任务型问数、分析、报告 | 语义层、多源、跨工具 | 多轮诊断、长任务和审批 |

BI 仍适合固定看板、正式财务报表和高频监控；DataAgent 更适合探索式问题、临时分析、报告初稿和需要多步工具的任务。两者应共享语义层，而不是各维护一套 GMV、毛利和收入定义。

判断一个“对话数据产品”是否真正进入 DataAgent，可追问三个问题：

- 关键指标能否指回 `metric_id@version`？
- 执行过程能否回放 SQL、参数、权限和 Artifact？
- 多轮追问是否修改结构化任务状态，而不只是把历史聊天重新塞给模型？

答不上这些问题的系统，更接近 ChatBI/BI 插件。

## 32.3 四种产品形态：问数 → 分析 → 报告 → 任务工作台

DataAgent 更适合渐进式建设，而不是从第一天就做“万能数据助手”。

*表32-3：DataAgent 四种产品形态。来源：本书整理。*

| 形态 | 用户诉求 | 典型输出 | 核心依赖 |
|---|---|---|---|
| 问数 | “上周华东 GMV 多少？” | 数字、表格、口径说明 | 语义层、NL2SQL、只读 SQL |
| 分析 | “哪些品类导致下滑？” | 贡献度、统计摘要 | SQL + Python 沙箱 |
| 报告 | “给经营会写一份复盘” | 图表、洞察、报告草稿 | EvidenceRef、模板、HITL |
| 任务工作台 | “每周自动生成并送审” | 长 Run、待办、审批与归档 | Runtime、调度、多 Agent、Trace |

建设顺序应服从底座成熟度：语义层不稳定时先把问数做准；查询稳定后再开放 Python 分析；证据链和报告模板稳定后再做自动报告；只有流程反复发生，才值得做定时和任务工作台。

**越靠后的产品形态，自动化价值越高，但对证据、恢复和组织责任的要求也越高。**

## 32.4 Question Frame：自然语言和执行链之间的任务契约

DataAgent 不应从原始问题直接生成 SQL。先将问题转成结构化 Question Frame，可以把用户意图、默认值、已确认口径和后续路径固定下来。

```yaml
intent: diagnose
metrics: [gmv]
dimensions:
  region: EAST
time:
  primary: last_week
  compare_to: prior_week
grain: sku
task_type: diagnose
path: sql_then_python
semantic_view: sales_ops
```

这里的 `gmv` 仍是业务 token，第33章再把它链接到具体 `metric_id@version`；`path: sql_then_python` 说明先查询，再做贡献度或结构分析。

*表32-4：任务类型与首选路径。来源：本书整理。*

| 任务类型 | 示例 | 首选路径 |
|---|---|---|
| 查询 | 上周华东 GMV | 语义层 + NL2SQL |
| 对比 | 华东与华北同比 | SQL 聚合 |
| 诊断 | 哪些 SKU 导致下滑 | SQL + Python 拆解 |
| 归因 | 价格还是销量导致 | 受控分析 Tool/Python |
| 报告 | 写经营复盘 | 已验证结果 + 图表 + 模板 + HITL |

![图32-1：Planner 路径选择](../../images/part6/ch/ch32-planner-flow.png)

*图32-1：Planner 路径选择。来源：本书自绘。Alt text：决策树从问题类型分支，分别选择 NL2SQL、多步分析、Text-to-Python 等路径。*

Frame 还决定什么时候必须澄清。指标存在多个合法口径、缺少必要时间、主体或数据域时，不应让模型悄悄猜。若组织策略提供明确默认值，可以采用默认，但要把来源写进 Frame 和回答。

用户追问“那华北呢”时，系统只需要生成 Frame diff：继承指标、时间和比较方式，把区域从 EAST 改为 NORTH，再重新经过语义层和执行校验。

**自然语言交互可以是自由的，底层任务状态必须是结构化的。Question Frame 正是把两者分开的中间层。**

## 32.5 “华东下滑”案例：六章是一条 Run，不是六个孤立能力

Part VI 统一使用这条经营分析任务：

*表32-5：统一案例与章节映射。来源：本书整理。*

| 步骤 | 章节 | 关键动作 | 产物 |
|---|---|---|---|
| 问题建模 | 第32章 | 形成 Question Frame | `task_type=diagnose` |
| 口径绑定 | 第33章 | Schema Linking / 消歧 | `gmv_ops@2025Q1` |
| 查询执行 | 第34章 | 编译并执行只读 SQL | SKU 结果 Artifact |
| 分析计算 | 第35章 | Python 品类贡献度 | `category_contrib.json` |
| 报告生成 | 第36章 | 图表、EvidenceRef、报告 | 报告草稿 |
| 产品/生态评估 | 第37章 | 用业务样本评估组件与路线 | 选型/回归结论 |

用户最终看到的可以是：“华东上周运营 GMV 较前周下降 12.3%，主要下滑来自三个 SKU；指标为 `gmv_ops@2025Q1`，数据截至……”。普通用户不必看到所有 SQL，但系统必须能打开 SQL hash、Python Artifact、Metric 版本和报告证据。

失败路径同样属于产品能力：语义层没有安全口径就澄清/拒答；SQL 超时按结构化错误处理；Python 样本不足就降低结论强度；对外发布进入 HITL。

## 32.6 DataAgent 与数据平台、Agent 平台和 BI 的边界

![图32-2：DataAgent 与平台分层边界](../../images/part6/ch/ch32-platform-layers.png)

*图32-2：DataAgent 与平台分层边界。来源：本书自绘。Alt text：分层图区分 DataAgent 专属能力与平台共享能力，箭头表示 DataAgent 复用平台能力而非自建。*

DataAgent 应尽量复用已有平台能力：

- **数据平台**：湖仓/OLAP、元数据、质量、新鲜度、语义层；
- **Agent 平台**：Runtime、Registry、Gateway、Policy、Memory、HITL、Trace；
- **BI**：固定指标看板、正式报表、稳定监控；
- **DataAgent 应用层**：Question Frame、任务分型、解释模板、业务交互和领域 Playbook。

长期直连 ODS、在 Prompt 里复制指标公式、给 DataAgent 单独建权限系统，都会让早期 Demo 的速度变成后期治理成本。

组织上也需要三类 owner：数据团队维护口径和质量，平台团队维护运行与工具边界，业务团队提供真实术语、默认场景和验收样本。

## 32.7 MVP、发布与验收：先做窄而可信的数据任务

早期 MVP 建议限制一个业务域、少量核心 Metric、一组稳定 Dimension 和一条完整任务链。例如围绕经营周会，只支持销售、订单、库存和品类结构，而不是承诺“自然语言查询全公司所有数据”。

范围应显式公布：支持哪些指标、时间粒度、角色、数据新鲜度和报告类型；范围外问题应给出可行动的拒答，例如“当前支持运营 GMV，不支持财务收入”或“当前角色可看区域汇总，明细需申请权限”。

验收样本要来自真实业务问题，并为每条问题标出期望行为：回答、澄清、拒答、降级或转人工。不能只测管理员账号和成功 SQL。

至少检查：

1. Question Frame 是否正确；
2. Metric/View 是否正确绑定；
3. SQL 是否只读并受权限约束；
4. Python 结果是否可复现；
5. 报告结论是否都有 EvidenceRef；
6. Trace 是否能串起整个 Run；
7. 不支持/不确定时是否能安全停止。

发布可以按“问数 → 分析 → 报告 → 工作台”逐层放开，也要允许局部退回。报告人工退回率升高时，可以暂停自动报告而保留问数和分析；语义层覆盖不足时，可以只开放内部试点，而不是要求模型绕开正式口径。

**DataAgent 的自动化程度应该由证据完整度决定，而不是只沿着“功能越来越多”单向升级。**

## 本章小结

DataAgent 覆盖自然语言问题到可信查询、分析、图表、报告和组织流程的完整任务链。NL2SQL 是其中一个工具，不是产品本身。

Question Frame 把自然语言转成结构化任务，语义层再负责口径，SQL/Python 负责计算，EvidenceRef 与 HITL 负责交付和责任。DataAgent 应复用数据平台与 Agent 平台已有能力，并与固定 BI 报表互补。

**一个值得进入生产的 DataAgent，不在于“什么都敢回答”，而在于核心业务问题能稳定回答、边界问题会澄清或拒绝，且任何关键结论都能沿同一个 Run 回到口径、查询、分析和证据。**

## 参考文献

Liu, X., Shen, S., Li, B., et al. (2025). A survey of Text-to-SQL in the era of LLMs: Where are we, and where are we going? *IEEE Transactions on Knowledge and Data Engineering*, 37(10), 5735-5754.

Tang, Z., Wang, W., Zhou, Z., et al. (2025). *LLM/Agent-as-Data-Analyst: A survey*. arXiv:2509.23988.

Lei, F., Chen, J., Ye, Y., et al. (2024). *Spider 2.0: Evaluating language models on real-world enterprise text-to-SQL workflows*. ICLR 2025.

Huo, N., Xu, X., Li, J., et al. (2026). *BIRD-INTERACT: Re-imagining Text-to-SQL evaluation via lens of dynamic interactions*. ICLR 2026.

Cube. (2025). *Introduction: Cube semantic layer*.

Microsoft. (2024). *Copilot in Power BI*.
