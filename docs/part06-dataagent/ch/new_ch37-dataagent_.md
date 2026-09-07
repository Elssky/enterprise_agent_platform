# 第37章 DataAgent 对标与生态

---

DataAgent 生态很难用一张“谁最好”的排行榜说明。Vanna、WrenAI、DB-GPT、Defog、BI Copilot 等产品分别从 NL2SQL、语义层、分析工作台、Agent 框架或 BI 入口切入，覆盖的是 DataAgent 链路的不同位置。

企业选型真正需要回答的是：当前缺的是哪一段能力，外部组件接入后谁继续负责语义口径、执行权限、Run 状态、Trace 和 Eval，以及供应商或框架未来被替换时核心资产能否留下。

**DataAgent 生态选型不是挑一个“最像完整产品”的方案，而是决定哪些能力可以借用，哪些生产责任必须继续由企业自己的数据平台和 Agent 平台掌握。**

## 37.1 为什么 DataAgent 生态会分化

DataAgent 同时涉及自然语言入口、Text-to-SQL、语义层、Python 分析、报告、部署合规和组织治理，很少有单一产品在这些方面都处于同一成熟度。

*表37-1：生态分化轴。来源：本书整理。*

| 分化起点 | 典型能力 | 常见缺口 |
|---|---|---|
| ChatBI 入口 | 对话查数、图表 | Runtime、HITL、Trace |
| NL2SQL 库 | schema 检索、SQL 生成 | 语义层、权限和组织流程 |
| Notebook/分析 Agent | Python、探索和报告 | 多租户、数据准入、发布责任 |
| BI Copilot | 看板解释、改图 | 跨主题长任务、Agent 编排 |
| Agent/数据应用平台 | 工具链、插件、工作流 | 与企业现有底座可能重复 |

“华东下滑”任务正好跨越这些边界：Question Frame、Metric 消歧、SQL、Python、图表、报告、HITL 和 Eval。一个 SaaS 能流畅回答 Top SKU，只能证明它覆盖了其中一部分。

公开 benchmark 也在从单句 Text-to-SQL 走向企业 workflow 和多轮交互。Spider 2.0、BIRD-INTERACT 的变化说明：**DataAgent 的质量越来越取决于任务链，而不是单次 SQL 翻译。**

## 37.2 生态地图：把组件放回正确层级

![图37-1：DataAgent 生态能力地图](../../images/part6/ch/ch37-dataagent-ecosystem-map.svg)

*图37-1：DataAgent 生态能力地图。来源：本书自绘。Alt text：图中以偏库到偏平台、偏 NL2SQL 到偏完整任务两个维度放置 Vanna、WrenAI、DB-GPT、Defog、BI Copilot 和本书 mini-platform，说明各方案覆盖的能力边界。*

可以用“偏库/偏平台”“偏查询/偏完整任务”理解典型方案：

- **Vanna**：更接近 Question-SQL/schema 检索增强组件；
- **WrenAI**：语义建模 + 对话 BI，更靠近第33章；
- **DB-GPT**：提供更完整的数据 Agent/应用平台壳；
- **Defog 类方案**：更强调数据分析、Python/报告链；
- **BI Copilot**：嵌入已有 BI 语境，强在报表内辅助；
- **mini-platform**：本书用来说明 Runtime、Registry、Policy、Trace 等企业运行契约，而不是作为产品排行榜参赛者。

外部能力进入企业后，应尽可能被归一成现有对象：NL2SQL 能力作为 `sql_executor` 的生成后端，语义产品由 `semantic_layer client` 消费，分析组件包装成 Tool，BI Copilot 作为入口/展示层。

**能作为组件解决的问题，就不要为了引入组件顺带引入第二套 Runtime、第二套权限和第二套审计。**

## 37.3 开源方案对照：看覆盖链路，不看勾选数量

*表37-2：典型方案与 Part VI 能力对照。来源：本书整理。*

| 能力 | DB-GPT | Vanna | WrenAI | Defog | mini-platform 责任 |
|---|---|---|---|---|---|
| Runtime | 自有 | 无 | 部分 | 部分 | `core/runtime/` |
| Registry/工具治理 | 部分 | 无 | 部分 | 部分 | `core/registry/` |
| 语义层 | 可接 | 弱 | 强 | 中 | `infra/semantic_layer/` |
| NL2SQL | 强 | 强 | 强 | 中 | `tools/sql_executor/` |
| Python 分析 | 有 | 弱 | 弱 | 强 | `tools/python_sandbox/` |
| 图表/报告 | 部分 | 弱 | 中 | 强 | renderer + template |
| HITL/企业权限 | 需集成 | 需自建 | 需集成 | 需集成 | Part V Runtime/Policy |
| 企业 Eval/Trace | 需适配 | 需自建 | 需适配 | 需适配 | `core/eval/` / Trace |

这类表只用于定位，不是固定版本评分。开源项目变化很快，实际选型必须用当前版本验证。

几个典型判断：

- Vanna 的历史 Question-SQL 检索可以帮助私有 schema 适配，但不能替代 Metric/View 和 Policy；
- WrenAI 的语义层方向适合评估为第33章后端，但企业仍需确认 Run、权限、审计如何接入；
- 已有 Part V 底座时，整包引入平台型框架要特别警惕双 Runtime；
- 分析/报告组件可以借鉴或接入，但 Python 沙箱和 EvidenceRef 仍需企业控制；
- 研究型多步分析 Agent 的推理策略可以参考，生产执行链仍需收敛到统一 Tool 和状态契约。

## 37.4 ChatBI、BI Copilot 和 DataAgent 可以共存

*表37-3：三种产品形态的职责。来源：本书整理。*

| 维度 | ChatBI | BI Copilot | DataAgent |
|---|---|---|---|
| 核心定位 | 对话查数 | BI 内嵌辅助 | 数据任务 Agent |
| 数据上下文 | 单主题/连接库 | 当前 BI dataset | 多 View/多 Tool/权限上下文 |
| 多步分析 | 较弱 | 中等 | SQL → Python → Report |
| 长任务/HITL | 通常弱 | 通常非核心 | 核心能力 |
| 证据/回放 | 依产品 | 依 BI 平台 | Run/Artifact/EvidenceRef |

固定正式看板继续由 BI 承载完全合理；BI Copilot 提高分析师操作效率；DataAgent 负责跨工具的探索、诊断和报告任务。最重要的是共享 Metric/语义层，而不是要求所有入口都被同一个产品替代。

**产品可以多入口，业务事实不应多口径。**

## 37.5 自研、采购还是混合：判断依据是责任和组织能力

*表37-4：常见路线。来源：本书整理。*

| 路线 | 更适合 | 主要风险 |
|---|---|---|
| SaaS ChatBI | 快速低风险试点 | 数据出域、口径/日志难接管 |
| 商业产品 + 企业语义层 | 已有数据治理底座 | 双平台集成成本 |
| 自研平台 + 外部组件 | 有平台工程团队 | 需要稳定接口与架构纪律 |
| 深度自研 | 高合规、强定制、长期规模化 | 初期投入和维护成本高 |

多数企业最终可能采用混合路线：

```text
业务入口 / BI / 第三方产品
          ↓
Enterprise Runtime + IAM + Registry
          ↓
DataAgent Planner
          ↓
semantic layer / NL2SQL component / Python / report tools
          ↓
Trace + Eval + Artifact + HITL
```

可以采购 SQL 生成器、语义引擎或 UI，但以下事实来源最好仍由企业掌握：

- 身份/租户和数据权限；
- Metric/version；
- Run/Tool Call/Artifact；
- Trace、Eval 和事故样本；
- 高风险发布/审批；
- 核心业务金标准集。

**采购降低的是某一段建设成本，不会替企业承担指标口径和生产责任。**

## 37.6 选型前先定义“准入样本”，不要用供应商 Demo 代替测试

一个统一试运行协议可以让自研、开源和商业产品在同一标准下比较。至少覆盖：

1. 核心正常问数；
2. 同一词命中多个 Metric；
3. 无权限用户请求敏感明细；
4. 空结果和数据延迟；
5. SQL 错误、自修复和高成本查询；
6. Python 分析/图表证据；
7. 正式报告 HITL；
8. 多轮追问继承 Frame；
9. 日志/Artifact/Trace 是否可导出；
10. 组件故障后能否把状态交回企业 Runtime。

若评估 NL2SQL 组件，就重点看 Linked Schema、SQL、只读和错误码；评估语义层就看 Metric/View/version；评估报告组件就看 EvidenceRef 和版本；评估平台型产品则必须看 identity、checkpoint、HITL、Trace 和退出能力。

**一个组件能回答漂亮问题，不等于它具备生产准入。真正的准入样本应该故意包含歧义、权限、失败和恢复。**

## 37.7 Eval：公开 benchmark 与业务金标准集双轨

产品选型不是一次性动作。引入后是否真的改善，需要同一套 Eval 持续比较。

*表37-5：DataAgent Eval 两类资产。来源：本书整理。*

| 层级 | 样本 | 作用 |
|---|---|---|
| SQL 技术能力 | Spider 2.0、BIRD | 比较 Text-to-SQL 能力下限 |
| 多轮交互 | BIRD-INTERACT | 评估澄清和动态任务 |
| 企业可信度 | 业务金标准集 | Metric、权限、报告和组织流程 |

业务金标准集应包含同义说法、角色差异、错误口径、HITL 和拒答期望。例如“销售额 / GMV / 流水”“华东 / 苏皖大区”等都可能是实际用户表达。

线上再看：核心任务完成率、口径投诉、人工退回、EvidenceRef 缺失、SQL/Python 失败、Run 成本和建议采纳。不能只看调用量和“用户是否点过一次答案”。

失败要回到具体层：口径 → Glossary/Metric；SQL → Linker/生成/执行器；图表 → renderer；报告过度推断 → template/Eval；权限 → View/Policy。

**“优化 Prompt”不应该成为所有 DataAgent 失败的默认结论。链路分层之后，每种失败都应有明确 owner。**

## 37.8 成本也要按完整任务比较，而不是只比模型单价

DataAgent 的成本来自模型、SQL 扫描、向量/语义查询、Python 沙箱、图表、报告、存储和人工复核。

对标组件时，可以按 Run 记录：

```text
model tokens
LLM calls
OLAP scanned bytes / compute time
python cpu/memory/time
artifact storage
retry count
human review time
final accepted / rejected
```

一个组件单次调用便宜但错误率高，后续人工和查询重试可能更贵；另一个组件成本高却显著降低正式报告返工，可能更适合高价值任务。

因此更值得比较的是“**完成一项被业务接受的任务所需总成本**”，而不是厂商 API 单价。

## 37.9 退出和替换：核心证据资产必须能迁移

产品能力、开源维护和商业条款都会变化。生态治理从第一天就应回答：如果明年替换这个组件，哪些资产还能继续使用？

核心可迁移资产包括：

- 业务问题和金标准样本；
- Metric/Glossary/View；
- SQL 与执行日志；
- ToolSpec / AgentSpec；
- Python/分析模板；
- Trace、Artifact、EvidenceRef；
- 用户反馈和报告模板。

外部组件应有退出说明：配置如何导出、历史 Run 如何保留、接口替代方案、迁移影响和回滚方式。

替换也需要灰度。用同一批真实任务跑旧/新组件，比较 Metric、SQL、权限、结果、证据、成本和失败语义。新组件即使平均分更高，只要关键 Evidence 字段缺失或权限无法映射，也不应直接扩大流量。

**采用外部生态能力没有问题；让业务样本、指标口径和运行证据只能存在于供应商私有控制台，才会形成真正的锁定。**

## 37.10 Part VI 的统一走读：六章最终是一条责任链

“上周华东区销售下滑，主要 SKU 是哪些？和品类结构有没有关系？”完整路径是：

*表37-6：Part VI 统一案例。来源：本书整理。*

| 章 | 做什么 | 关键平台对象 |
|---|---|---|
| 32 | 形成 Question Frame | task type / path / context |
| 33 | 绑定 `gmv_ops@2025Q1`、View 和可信上下文 | Linked Schema |
| 34 | 编译、校验并执行只读查询 | SQL Tool Result / Artifact |
| 35 | 在 SQL 结果上计算品类贡献 | Python Artifact |
| 36 | 生成图表、EvidenceRef 和报告草稿 | Report / HITL |
| 37 | 用业务样本和生态组件评估下一版 | Eval / selection record |

无论底层某一步使用自研代码、Vanna、WrenAI 还是商业产品，这些责任对象都不应消失。

## 本章小结

DataAgent 生态中的产品和框架从不同入口切入，不能仅按“是否支持 NL2SQL、图表、多轮”做排名。先明确企业自身缺口，再把外部能力放回语义层、Tool、入口或 Planner 等正确层级，通常比直接采用第二套完整平台更容易治理。

公开 benchmark 用来比较技术能力，业务金标准集决定企业是否可用；选型还要同时检查权限、HITL、Trace、成本和退出路径。业务 Metric、样本和证据资产应尽量留在企业可控范围。

**生态对标最终应该输出的不是“选哪个产品”，而是一张责任地图：哪一段外采、哪一段自研、数据和证据在哪里、失败由谁处理，以及未来替换时平台主线能否保持不变。**

## 参考文献

Liu, X., et al. (2025). NL2SQL survey. *IEEE TKDE*.

Tang, Z., et al. (2025). *LLM/Agent-as-Data-Analyst: A survey*.

Lei, F., et al. (2024). *Spider 2.0*. ICLR 2025.

Huo, N., et al. (2026). *BIRD-INTERACT*. ICLR 2026.

eosphoros-ai. (2024). *DB-GPT*.

Canner. (2024). *WrenAI*.

vanna-ai. (2024). *Vanna*.

Defog.ai. (2024). *Defog*.

Microsoft. (2024). *Copilot in Power BI*.

Cube. (2025). *Semantic layer docs*.
