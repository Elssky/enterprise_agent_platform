# 第31章 框架横向对标

---

LangGraph、AutoGen、CrewAI、Dify、Coze、Bisheng 等工具都能快速搭出 Agent 应用，但它们覆盖的层次并不相同。技术选型如果只比较“有没有状态图、多少插件、能不能多 Agent”，很容易得到“大家都能做”的结论；真正进入生产后，差异会集中到另一组问题：谁保存 Run 状态，谁掌握工具执行权，谁处理审批和恢复，谁能导出审计证据。

企业通常不会只使用一种框架。数据团队可以用 LangGraph 做复杂 Planner，运营团队可以用 Dify/Coze 快速搭入口，平台团队维护统一 Runtime 和 Registry。混合本身没有问题，问题在于生产责任是否被拆成多套事实来源。

**框架负责提高表达和开发效率，企业平台负责接管执行责任。选型的核心不是“哪个框架最强”，而是它在整个平台中承担哪一层，以及出了问题由谁恢复和追责。**

## 31.1 先分清框架、平台和应用

*表31-1：三层职责。来源：本书整理。*

| 层次 | 主要解决 | 典型产物 | 主要维护方 |
|---|---|---|---|
| 框架 | 怎样组织模型、工具、图和角色 | LangGraph graph、Crew、AutoGen flow | 应用/数据团队 |
| 平台 | 怎样统一运行、治理、审计、恢复 | `/run`、Registry、Policy、Trace、HITL | 平台团队 |
| 应用 | 怎样服务具体岗位与流程 | DataAgent、客服、经营分析 | 业务 + 平台 |

框架可以成为 Planner 实现，低代码产品可以成为入口或运营台，但**任何会改变业务状态的动作，都不应因此拥有独立于企业平台的第二套权限和审计链。**

技术评审可以先问三个问题：

1. 能否映射到统一 `run_id` / Runtime？
2. 企业工具能否强制走 Central Registry/Policy？
3. 状态、Tool Call、Artifact 和日志能否进入统一 Trace？

这三个问题回答清楚后，再看画布、节点、插件和开发体验才有意义。

## 31.2 开源框架：更适合 Planner 与开发层

### LangGraph

LangGraph 适合有向图、状态、循环、子图和 interrupt。复杂 DataAgent 可以把“选表 → 生成 SQL → 执行 → 修正”建成图，但图内节点仍应折叠成平台 Run 状态。

合理位置是 Planner/Workflow 插件：`thread_id` 可映射 `run_id`，图工具节点调用企业 Registry，`interrupt()` 映射 `waiting_human`。这样图结构可以持续变化，前端、SLO 和审计接口保持稳定。

### AutoGen

AutoGen 强在多 Agent 实验、对话式协作和代码执行，适合 Lab 阶段探索角色如何分工。生产化时，自由 GroupChat 应收敛成显式 Handoff、工具白名单和终止条件，否则 token、权限和责任边界会迅速失控。

### CrewAI

CrewAI 的 Role / Task / Crew 抽象适合用业务语言描述岗位协作。进入平台后，角色和任务可以转为 AgentSpec/Workflow 配置；状态、Tool Call、HITL 仍由 Runtime 管。

**开源 Agent 框架最大的价值，是让团队更快表达 Planner 和协作结构；最常见的误用，是把框架自带的执行循环直接当成集团级生产 Runtime。**

## 31.3 低代码与应用平台：强在入口和运营，不自动等于治理底座

### Dify

Dify 在 Workflow、RAG、知识库和可视化编排上适合快速试点。一个合理组合是：业务人员在 Dify 中配置入口，核心查询/写操作调用企业 `/run` 或受控 Registry API。数据库和高风险工具不应被每个 Dify 插件各自直连。

### Coze

Coze 适合 Bot 渠道、营销、客服和快速触达。边缘 Bot 可以使用只读/低风险能力；涉及主数据、批量外发、敏感查询或高风险写操作，应回到企业 Runtime/HITL。

### Bisheng

Bisheng 更偏企业/政企部署，可承担知识管理、部分流程 UI 和本地化集成。是否进入核心生产链路仍需逐项验证 IAM、Run 映射、日志、审批、数据边界和导出能力。

低代码平台并非“不适合生产”，而是**它必须证明自己的运行语义能与企业底座对齐，而不能因为 UI 完整就默认承担核心治理责任。**

## 31.4 能力矩阵：比较“责任覆盖”，不要做产品排名

*表31-2：mini-platform 与典型框架/平台的职责侧重点。来源：本书整理。*

| 能力 | 企业 Runtime / mini-platform | LangGraph | AutoGen | CrewAI | Dify / Coze / Bisheng |
|---|---|---|---|---|---|
| Planner/编排表达 | 中 | 强 | 强 | 强 | 强 |
| 快速 Bot/业务入口 | 弱 | 弱 | 中 | 中 | 强 |
| Run 状态/SSE/恢复 | 强 | 可映射 | 需适配 | 需适配 | 产品各异 |
| Tool Registry/版本 | 强 | 需接入 | 需接入 | 需接入 | 需验证/适配 |
| 企业 Policy/租户 | 强 | 非核心 | 非核心 | 非核心 | 需验证 |
| HITL 责任链 | 强 | 可实现 | 可扩展 | 可扩展 | UI 有不等于引擎级 |
| Trace/合规回放 | 强 | 需集成 | 需集成 | 需集成 | 需验证导出 |
| 低代码运营 | 弱 | 弱 | 弱 | 弱 | 强 |

![图31-1：框架/平台选型决策树](../../images/part5/ch/p5-12-framework-selection-tree.png)

*图31-1：框架/平台选型决策树。来源：本书自绘。Alt text：决策树从团队工程能力、治理与多租户要求、上线时间压力等问题分支，引向自研、采购或混合三条路线。*

这张表不是说“企业底座强于所有框架”，而是说明职责不同。框架可以让 Planner 更好写，低代码让应用更快交付，平台底座则确保工具权限、状态和证据不因上层工具不同而分裂。

## 31.5 自研、采购与混合：多数企业最终会组合使用

### 适合自研/深度掌握的部分

通常包括：

- 统一 `/run` 与状态契约；
- Central Tool Registry；
- IAM/Policy/HITL；
- Trace、审计、Eval、成本；
- 语义层/核心数据/ERP 等深度集成；
- 统一 Artifact/事件/错误模型。

这些能力与企业责任和已有基础设施耦合较深。

### 适合采购/直接使用的部分

包括标准 Bot、低风险 RAG、业务运营界面、营销触达、开发框架和部分可视化编排。采购重点不是“插件数量”，而是数据驻留、IAM、日志导出、工具权限、私有化、SLA、退出能力和 API 开放程度。

### 混合路线

常见形态是：

```text
Dify / Coze / 企业前端
        ↓
Enterprise Runtime / API Gateway
        ↓
Planner (LangGraph / 自研 / CrewAI)
        ↓
Registry + Policy + HITL
        ↓
Tools / MCP / Data / SaaS
        ↓
Trace / Eval / Artifact
```

**混合架构可以有多个开发工具和入口，但最好只有一个生产执行事实来源。**

## 31.6 已有框架怎样被“收编”，而不是推倒重来

迁移可以按风险从高到低分三步：

1. **先统一工具**：框架内部不再直连数据库/外部系统，改走 Registry；
2. **再统一运行事件**：把框架节点、工具结果和中断映射成 Run/Step/Tool Call/HITL；
3. **最后统一控制面**：Console、发布、评测、成本和合规逐步接管。

先收工具是因为副作用风险最高；先统一 UI、却让底层工具继续各自执行，意义有限。

已有 LangGraph 原型可以保留图，只替换工具执行入口；Dify Workflow 可以继续作为业务入口，但调用企业 Agent Run；Coze 可以继续负责渠道，却不拥有核心写权限。

**平台化不是要求所有团队使用同一个 SDK，而是要求不同 SDK 最终遵守同一套生产契约。**

## 31.7 采购和技术验收：用一条真实基准链路测试

产品演示很难暴露生产问题。采购/框架评估可以使用 Part V 已建立的基准任务：

`用户问题 → Run → Planner → Tool Registry → 工具失败/恢复 → Handoff → waiting_human → approve/resume → Artifact → Trace`

至少询问和验证：

- 是否有稳定 `run_id`？
- 能否导出每次 Tool Call 和版本？
- 工具能否强制走企业 Registry？
- 人工审批是真实引擎挂起，还是前端按钮？
- 重启/断线后能否恢复？
- 是否支持用户/租户权限传播？
- 日志、Prompt、ToolSpec、Eval 样本能否导出？
- 框架升级后旧 Run 是否还能解释？
- 供应商退出后核心资产能否迁走？

内部自研平台也要回答同一组问题。**自研并不会天然等于可治理。**

## 31.8 版本、升级与退出：避免被早期工具选择长期锁死

框架升级可能改变消息模型、callback、工具格式、Memory 默认行为和 streaming 事件。生产 Agent 使用框架后，升级不再只是 `pip install -U`，而是运行契约变更。

升级前应固定核心样本：多轮工具调用、错误、HITL、长任务、取消、Artifact、Trace。新版本先 shadow/灰度，验证平台事件语义没有被破坏。

选型时也要提前设计退出：Prompt、ToolSpec、Eval 集、运行日志、用户反馈和业务流程尽量存放在企业可控资产中；无法导出的供应商私有能力应限制进入核心流程。

一个实用的框架治理账本可以记录：

```text
framework/product
version
responsibility_layer
owner
business_scenarios
registry_integration
trace_export
identity_boundary
non-portable_assets
upgrade_policy
exit_condition
next_review
```

**采用框架不是问题，把核心运行资产和治理主权一起锁在某个框架里才是问题。**

## 31.9 试点转生产：业务价值和平台接管是两套验收

试点结束时应该分别回答：

**业务价值**：用户是否真正使用、解决了哪些任务、减少多少返工、哪些样本仍失败。

**生产接管**：工具是否进 Registry、身份是否接 IAM、日志是否进 Trace、HITL 是否可恢复、成本/SLO 能否统计、资产能否导出和回滚。

业务效果很好但平台无法接管，说明适合继续试点，不一定适合直接扩大生产；平台治理完整但无人使用，也不能证明项目成功。

进入生产后，框架中的可复用成果还应逐步沉淀成平台资产：Prompt 进模板库、Tool wrapper 进 Registry、失败样本进 Eval、审批规则进 Policy/HITL、事件模式进入 Runtime 契约。

## 本章小结

框架、平台和应用承担不同职责。LangGraph、AutoGen、CrewAI 等适合提升 Planner/协作开发效率；Dify、Coze、Bisheng 等更擅长应用入口、低代码和运营；企业 Runtime 则应掌握状态、工具执行、权限、审批、Trace 和恢复。

多数企业会采用混合路线。关键不是技术栈是否统一，而是写操作和运行证据最终是否收敛到同一个事实来源。框架应能被接入、升级、替换和退出，而不破坏核心生产契约。

**框架选型的最终判断标准，是它能否让团队更快交付，同时不让企业失去对身份、工具、状态、证据和退出路径的控制。**

## 参考文献

NIST. (2023). *AI RMF 1.0*.

LangChain. (n.d.). *LangGraph*; *Persistence*.

Microsoft. (n.d.). *AutoGen*.

Wu, Q., et al. (2024). *AutoGen*.

CrewAI. (n.d.). *Documentation*.

Dify. (n.d.). *Documentation*.

Coze. (n.d.). *开放平台文档*.

Bisheng. (n.d.). *DataElem Bisheng*.

Model Context Protocol. (2024). *Specification*.
