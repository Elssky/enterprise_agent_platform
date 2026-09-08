# 第51章 Guardrails 与内容安全

---

Guardrails 常被理解成“模型调用前后各跑一次内容审核”。这只覆盖了很小一部分。企业 Agent 的风险会出现在输入、RAG Context、Tool Call、模型输出、Artifact、导出、日志和人工审批等多个位置；同一段文本是否允许，也取决于用户角色、数据域、动作类型和业务场景。

**Guardrails 的目标不是“拦截更多”，而是在正确控制点做出可解释、可恢复的决策。** 内容分类器负责识别风险，权限系统负责判断资源访问，Policy Engine 负责把用户、任务、工具、数据和风险组合成动作决策，Runtime 再根据 `allow / warn / mask / review / deny` 等结果推进或挂起任务。

NVIDIA NeMo Guardrails、Meta Llama Guard、OpenAI Moderation、Azure AI Content Safety，以及企业自有 DLP、PII 检测和审批规则都可以成为其中的组件，但没有任何一个安全模型能独立承担平台策略。本章重点讨论 Guardrails 怎样从过滤器升级为分布式控制系统，以及策略怎样被版本化、灰度、申诉和回归。

---

## 51.1 分层 Guardrails：不同风险必须在不同位置处理

输入安全、数据权限、工具越权和导出风险不是同一问题。把它们都压到一个“安全模型”里，会让结果不可解释，也无法明确责任。

*表51-1：Guardrails 分层职责。来源：本书整理。*

| 层级 | 检查对象 | 典型策略 | 失败动作 |
|---|---|---|---|
| 输入层 | 用户消息、附件、URL、语音转写 | 内容风险、恶意意图、速率限制 | 拒绝、澄清、降级 |
| 上下文层 | RAG chunk、网页、Tool Result、Memory | 来源信任、注入、敏感字段、时效 | 隔离、脱敏、降低权重 |
| 工具层 | 工具、参数、资源、动作 | RBAC/ABAC、风险、审批、幂等 | 拒绝、确认、短令牌 |
| 输出层 | 文本、SQL、代码、图表、Artifact | 内容、DLP、引用、Schema | 重写、脱敏、拒绝 |
| 观测层 | 命中、人工复核、用户反馈 | 误杀、漏杀、漂移、事故 | 告警、回归、策略修订 |

![图51-1：Guardrails 分层架构](../../images/part10/ch/ch51-01-guardrails-layered-architecture.svg)

*图51-1：Guardrails 分层架构。来源：本书自绘。Alt text：自上而下分为输入 Guardrail（检测用户输入）、检索 Guardrail（过滤检索内容）、工具 Guardrail（校验工具调用参数）、输出 Guardrail（审查最终回答）四层，每层标注控制点和典型策略。*

**最终答案安全，不代表整条执行链安全。** 例如工具返回已经包含完整客户手机号，最后回答虽然被 DLP 脱敏，原文仍可能已经进入模型、Trace 或浏览器。更稳的原则是：风险越早能够被确定，就越早裁剪；后面的 Guardrail 用来补充控制，而不是依赖末端擦除前面已经扩散的数据。

这也解释了第50章安全与本章 Guardrails 的关系：第50章从攻击者视角问“怎样突破”；本章从生产控制视角问“在哪些执行点做什么判断”。

---

## 51.2 分类器、DLP、权限与业务策略各司其职

### 内容分类器：识别风险，不直接决定全部业务动作

通用分类器通常覆盖暴力、自伤、色情、仇恨、违法、危险建议等类别；企业还需要客户隐私、员工隐私、未公开财报、合同底价、涉密信息、金融/医疗/法务高风险建议等内部类别。

*表51-2：内容分类到平台动作的示例映射。来源：本书整理。*

| 分类 | 典型内容 | 平台动作 |
|---|---|---|
| 明确禁止 | 非法活动、严重伤害、凭证窃取 | 拒绝并记录安全事件 |
| 高风险敏感 | 医疗、金融、法务、人事等 | 限制结论，要求人工/专业流程 |
| 企业敏感 | 密钥、薪资、客户名单、未发布财报 | 脱敏、拒绝或按角色返回摘要 |
| 可回答但需边界 | 合规解释、内部制度、产品限制 | 附范围和证据 |
| 普通业务 | 低风险知识与分析 | 放行并留 Trace |

相同文字在不同场景可能得到不同处置。“导出客户手机号”对普通销售应拒绝，对有职责的主管也未必能直接放行，而可能进入审批。**内容分类器负责识别风险，Policy Engine 负责决定动作；二者不能混成一个安全模型。**

### DLP：保护数据，不替代资源授权

DLP/PII 检测回答“这里是否含敏感数据”，权限系统回答“这个人是否有权访问”，业务策略回答“即便有权，现在这个任务是否允许这样处理”。三者需要组合。

例如用户有权查看客户数据，不等于允许批量导出到外部文件；有权查看内部财务，不等于允许把内容送到外部模型。数据等级、用户身份、用途和输出渠道都应进入策略上下文。

### 业务安全与工程安全

Guardrails 还应覆盖：

- 是否必须先查询证据再给结论；
- 高风险动作是否需要审批；
- JSON/SQL/Tool 参数是否符合 Schema；
- 是否出现无界重试；
- 是否把不可执行输出传给下游；
- Artifact/导出是否仍满足当前权限。

这类问题不是传统内容审核能解决的，却直接影响企业 Agent 是否安全可用。

---

## 51.3 Policy Engine：把风险判断转成 Runtime 决策

策略引擎的输入应该是结构化上下文，而不是一段“请判断是否安全”的自由文本。

```json
{
  "trace_id": "trace_guard_001",
  "stage": "tool_call",
  "user": {
    "user_id": "u_1024",
    "tenant_id": "tenant_a",
    "roles": ["sales_manager"]
  },
  "request": {
    "tool_name": "query_customer_metrics",
    "action_type": "export",
    "resource": "dataset://crm/customer_profile",
    "fields": ["customer_id", "customer_phone", "region", "revenue"]
  },
  "risk": {
    "content_categories": ["enterprise_sensitive"],
    "sensitive_fields": ["customer_phone"],
    "risk_level": "high"
  }
}
```

响应同样应结构化：

```json
{
  "decision": "require_approval",
  "policy_id": "customer_pii_export_v3",
  "reason": "customer_phone export requires approval and masking",
  "actions": [
    {"type": "mask_field", "field": "customer_phone"},
    {"type": "require_human_approval", "approval_flow": "pii_export"}
  ],
  "audit": {
    "trace_id": "trace_guard_001",
    "severity": "high"
  }
}
```

![图51-2：可编程策略引擎流程](../../images/part10/ch/ch51-02-policy-engine-flow.svg)

*图51-2：可编程策略引擎流程。来源：本书自绘。Alt text：策略引擎从输入事件出发，依次经过规则匹配、分类器打分、风险评估、动作执行（拦截/降级/审批/放行），每步结果写入审计日志，体现策略可配置且全程可审计。*

*表51-3：Guardrails 策略实现取舍。来源：本书整理。*

| 方案 | 优势 | 代价 | 建议 |
|---|---|---|---|
| Prompt 规则 | 最快 | 不稳定、难审计 | 只作辅助说明 |
| 应用内 if-else | 简单 | 重复、版本散乱 | 非平台默认 |
| 配置化策略 | 易版本、灰度和审计 | 复杂表达有限 | 默认起点 |
| Policy Engine / DSL | 表达力强、可接 IAM | 运维成本更高 | 多租户高风险场景 |

早期不必追求复杂 DSL，但要先把策略从 Prompt 和业务代码中抽出来，形成稳定 `policy_id + version + scope + decision`。

### Policy 决策要驱动任务状态

Guardrails 不应该只返回一段拒绝文案。决策应映射到 Runtime：

```text
allow  -> 继续执行
warn   -> 继续，但展示限制
mask   -> 裁剪/脱敏后继续
review -> waiting_human
clarify-> waiting_user
 deny  -> terminal / policy_rejected
```

这样前端、Trace 和 HITL 都能理解“为什么停下来”。用户补权限、修改范围或通过审批后，Runtime 也知道应该从哪里恢复。

### 策略冲突必须有确定优先级

当同一请求同时命中脱敏、审批和拒绝时，不能让“最后执行的规则”碰巧决定结果。通常安全硬边界应高于体验策略，高风险 deny 高于普通 allow，审批可以在合法但高风险场景中作为恢复路径。

策略合并规则必须被测试，否则规则越多，系统越不可预测。

---

## 51.4 脱敏与输出校验：不要让敏感原文先扩散再清理

**脱敏发生在最终回答之前太晚了；敏感原文不应先进入模型、Trace 或浏览器，再期待末端清理。**

*表51-4：脱敏与输出校验位置。来源：本书整理。*

| 位置 | 检查 | 处理 |
|---|---|---|
| 模型输入前 | 密钥、身份证、客户信息 | 阻止、标记或脱敏 |
| RAG Context | 敏感字段、低信任内容 | 字段裁剪、来源标记 |
| Tool Result | 明细行、PII、跨租户数据 | 服务端过滤、只返回必要字段 |
| 输出生成后 | 文本、SQL、代码、图表 spec | 内容、引用、Schema、DLP |
| Artifact/导出 | 表格、报告、图片、CSV | 当前权限重检、重新脱敏 |

Guardrails 必须覆盖非文本产物。正文没有客户姓名，但 CSV 附件、图表 tooltip、SQL、JSON 字段或 Artifact 数据源仍可能泄露。

### 结构正确与内容合规是两种校验

- JSON 符合 Schema，不代表字段有权输出；
- SQL 可执行，不代表租户过滤正确；
- 图表 spec 合法，不代表分组维度允许展示；
- 邮件正文安全，不代表收件人范围合法。

结构化输出和业务安全需要同时通过。

### 导出是新的访问动作

用户能在页面看见某个结果，不自动意味着可以下载、转发或生成 PPT。导出和分享必须重新检查当前用户、Artifact 版本、字段等级、接收范围和审批状态。

这和第48章 Generative UI 的结论一致：前端组件只表达用户意图，最终授权由服务端执行。

---

## 51.5 误杀、漏杀、申诉与策略灰度

Guardrails 没有“准确率越高越好”的单一目标。误杀过多，业务会绕开平台；漏杀过多，安全边界失效。

*表51-5：Guardrails 治理指标。来源：本书整理。*

| 指标 | 含义 | 用途 |
|---|---|---|
| Block rate | 被拒绝/降级比例 | 判断攻击变化或策略过严 |
| False positive rate | 合法请求误杀 | 优化体验、例外与上下文 |
| False negative count | 风险请求漏过 | 安全回归与事故治理 |
| Approval conversion | 审批后最终通过比例 | 判断 HITL 是否过重 |
| Policy drift | 新业务/工具导致策略失效 | 触发复审和版本修订 |

![图51-3：Guardrails 策略治理闭环](../../images/part10/ch/ch51-03-policy-governance-loop.svg)

*图51-3：Guardrails 策略治理闭环。来源：本书自绘。Alt text：环形流程，策略定义、测试验证、灰度发布、线上监控、误杀/漏杀分析、策略修订，箭头表示每轮线上数据驱动下一轮策略优化，体现策略持续演进。*

**误杀与漏杀是同一套策略质量问题的两面。** 因此上线和复盘要同时看攻击样本和合法边界样本。

### 策略也需要版本、影子模式、灰度和回滚

新策略可以先 Shadow：记录“如果生效会怎样”，但不阻断用户。人工确认命中质量以后，再按租户、Tool 或风险等级逐步放量。

每次发布至少绑定：

```text
policy_version
classifier_version
scope
sample_set
expected_FP/FN
latency_budget
rollback_version
owner
```

安全策略升级不能比模型发布更随意。

### 申诉不是旁路，而是校准数据

用户认为拦截错误时，应产生结构化 Appeal：用户角色、任务目的、触发策略、原始决策、人工裁定、最终动作和是否需要修改规则。

人工裁定通常有四类：

1. 策略正确，用户需要权限/审批；
2. 策略误杀，需要修规则或分类器；
3. 产品入口缺少必要上下文，需要修 UI/任务模板；
4. 合法业务例外，需要范围、owner 和到期时间。

把所有申诉都当成“放行请求”，会快速侵蚀策略边界；把所有申诉都忽略，业务则会绕开平台。

### 用户反馈要可行动，但不能暴露绕过细节

比“请求不合规”更好的提示是：“当前请求包含受限客户字段，可改用聚合结果，或提交 PII 导出审批。” 用户知道如何继续，攻击者又不会获得具体检测阈值和内部规则。

---

## 51.6 策略资产与生产验收

Guardrails 规则一多，很容易积累成没人敢删的配置层。每条策略都应该是有生命周期的资产：

```text
id / version
owner
scope
stage
samples
exceptions
latency_budget
gray_status
last_reviewed_at
retirement_condition
```

**策略数量不是成熟度；能否解释谁负责、为什么存在、哪些样本证明它有效，才是成熟度。**

高频误杀还应反向推动产品设计。例如用户不断请求超范围导出，可能需要提供范围选择和审批入口；不断触发敏感字段拦截，可能应该提供脱敏数据产品，而不是只增加更多拒绝规则。

原稿中的 `mini-platform/projects/configurable-guardrails-gateway/` 可作为后续实验设计；当前仓库没有该目录，因此示例配置用于解释契约，不表示已有可运行模块。

### 最小运行验收

上线前建议固定回放：

- 正常业务请求；
- 合法但权限不足请求；
- 恶意 Prompt Injection；
- 敏感字段 Tool Result；
- 高风险导出；
- 需要 HITL 的写动作；
- 分类器不可用；
- Policy 冲突；
- 用户申诉与例外到期。

验收不仅看 decision，还要看：

```text
Runtime state
用户可见提示
Tool 是否真正被阻断
敏感原文是否进入 Trace/Browser
审批和恢复路径
策略版本与回滚
```

线上则定期复审长期低命中、长期高误杀、无人 owner 和例外过多的策略。必要时合并、退役或把问题转回产品/数据层解决。

**Guardrails 的长期价值，是把风险判断从一组隐藏规则变成可测试、可灰度、可申诉、可恢复的运行系统。**

## 本章小结

Guardrails 不是单个内容审核 API，而是分布在输入、上下文、工具、输出和观测层的一组控制点。内容分类器负责识别风险，DLP 识别敏感数据，权限系统判断资源访问，Policy Engine 综合场景决定 `allow / mask / review / deny`，Runtime 再执行对应状态迁移。脱敏应尽量前移，Artifact 和导出也必须重新校验。策略本身要像模型和代码一样经历版本、影子、灰度、回滚和样本回归；误杀、漏杀和申诉共同驱动策略修订。**安全平台真正要优化的不是拦截率，而是在不突破底线的前提下，让合法任务仍然有清楚的继续路径。**

## 参考文献

- [NVIDIA NeMo Guardrails Documentation](https://docs.nvidia.com/nemo/guardrails/latest/)

- [Meta Llama Guard Model Card](https://huggingface.co/meta-llama/Llama-Guard-3-8B)

- [Azure AI Content Safety](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview)

- [OpenAI Moderation Guide](https://platform.openai.com/docs/guides/moderation)

- [OWASP Top 10 for Large Language Model Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
