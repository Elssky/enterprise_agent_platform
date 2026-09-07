# 第27章 Memory 系统

---

Agent Memory 不能简单理解为“把历史对话继续塞进 Prompt”，也不能把企业知识库换个名字就叫 Memory。生产系统真正要解决的是：一次 Run 如何恢复上下文，哪些历史信息值得跨任务复用，用户偏好怎样安全保存，组织规则怎样版本化注入，以及信息过期、被纠正或被删除后如何真正失效。

一个 DataAgent 场景可以说明差异。用户先问“上周华东区销售下滑的主要 SKU 是什么”，随后只说“华北呢”。第二轮需要沿用上一轮的时间范围和指标口径，这是 Working Memory；用户明确说“以后这类分析都用同比表格”，可能成为 Profile；历史上某次成功分析路径可以沉淀为 Episodic；“华东区包含哪些门店”则属于受治理的组织上下文，不能从个人对话里自然生长。

**Memory 的价值不在“记得越多”，而在于每条上下文都知道来源、作用域、有效期、权限和退出方式。无法删除、无法解释、无法判断过期的信息，不应成为长期记忆。**

## 27.1 四类 Memory：生命周期不同，不能混成一个向量库

![图27-1：Memory 生命周期与治理边界](../../images/part5/ch/ch27-memory-lifecycle.svg)

*图27-1：Memory 生命周期与治理边界。来源：本书自绘。Alt text：图中展示 Run 输入写入 Working、Episodic、Profile 和 Org Context 四类记忆，并通过来源、TTL、删除、权限、版本和审计进入治理动作，Planner 只按需读取最小上下文。*

*表27-1：四类 Memory 的边界。来源：本书整理。*

| 类型 | 生命周期 | 典型内容 | 主要风险 |
|---|---|---|---|
| Working | Run / 会话级 | 最近输入、Tool Result、当前计划 | 过长、恢复不完整 |
| Episodic | 跨 Run | 历史任务片段、成功路径、人工修正 | 错误经验长期放大 |
| Profile | 用户长期 | 报告格式、语言、稳定偏好 | PII、误推断、删除权 |
| Org Context | 组织级 | 区域、指标、审批、组织与权限口径 | 版本漂移、个人信息污染组织规则 |

这四类记忆的责任方也不同：Working 主要由 Runtime 管理；Episodic/Profile 需要明确晋升策略和用户/业务授权；Org Context 应来自语义层、主数据或正式配置。

**最危险的设计，是把聊天、用户画像、历史任务和组织规则全部写进同一个长期向量库，再靠相似度决定是否注入。相似度不能代替作用域和权限。**

## 27.2 Working Memory：属于 Runtime 的可恢复状态

Working Memory 保存当前 Run 中 Planner 继续工作所需的最小上下文，例如：

```python
wm.append(MemoryMessage(
    role=MessageRole.USER,
    content="华东 SKU 下滑？",
    metadata={"source": "user_input"},
))

wm.append(MemoryMessage(
    role=MessageRole.TOOL,
    content='{"rows":[{"sku":"A001","delta":-0.12}]}',
    metadata={"source": "tool_result", "tool_call_id": "tc-1"},
))
```

检查点不能只保存 `state=executing`。如果 SQL 已执行、报告尚未生成时 Pod 重启，恢复后的 Planner 必须知道已经看过哪组结果，否则可能重新查询，甚至因为数据变化得到另一组事实。

```python
checkpoint_payload = {
    "run_id": run_ctx.run_id,
    "state": sm.state.value,
    "step_index": run_ctx.step_index,
    "tool_calls": [...],
    "working_snapshot": wm.snapshot(),
}
```

大型 Tool Result 不应原样塞入 Working。十万行 CSV、PDF、日志和图表应进入对象存储或 Artifact 层，Working 只保留摘要、schema、样例、hash 和 `result_ref`。

**Working Memory 首先是运行时恢复资产，其次才是给模型“多看一些历史”的上下文。**

## 27.3 长期记忆：模型可以提议，平台决定是否晋升

Episodic 和 Profile 都不能默认从聊天自动落库。更稳妥的写入流程是：

`候选提取 → 去重/冲突检查 → 敏感信息检查 → 作用域判断 → 用户确认或策略批准 → 版本化写入`

例如：

- “这次临时看上月”——不应晋升；
- “以后这类分析都输出同比表格”——可以成为 Profile 候选；
- “上次这个任务先查活动档期再查销量更稳定”——可以成为带来源的 Episodic；
- “新的华东区定义是……”——不能因为一次对话直接覆盖 Org Context。

长期条目至少应包含：

```json
{
  "memory_id": "mem-p-001",
  "type": "profile",
  "value": {"report_format": "table_with_yoy"},
  "source": "confirmed_by_user",
  "scope": {"user_id": "u-001", "tenant_id": "t-001"},
  "created_at": "...",
  "expires_at": null,
  "confidence": 1.0,
  "source_run_id": "run-123"
}
```

来源可信度很重要。用户明确确认的偏好、模型从行为中推断的偏好、人工写入的组织配置，不能以同一权重使用。

**长期 Memory 的写入是一次受治理的数据动作，而不是“模型觉得这句话以后可能有用”。**

## 27.4 Org Context 与 RAG：组织规则、知识证据和用户记忆要分开

Org Context 属于企业事实空间。区域定义、指标口径、审批链、角色权限、业务术语应由正式资产维护，并带版本和有效期。

RAG 与 Memory 都会向模型注入信息，但解决的是不同问题：

*表27-2：Memory 与 RAG 的区别。来源：本书整理。*

| 维度 | Memory | RAG |
|---|---|---|
| 主要对象 | 用户、Run、历史任务、组织上下文 | 文档、政策、知识库、数据说明 |
| 核心目标 | 连续性、恢复、偏好复用 | 找到可引用证据 |
| 权限边界 | 用户 / 租户 / 组织 / Run | 文档 ACL / 知识域 / 密级 |
| 删除 | 用户删除、过期、租户清理 | 文档下架、索引刷新 |
| 典型风险 | 跨用户污染、旧偏好 | 检索噪声、越权文档 |

DataAgent 可以先从 Org Context 得到当前组织和审批口径，再从 RAG 查指标说明文档，最后用 Working 保存本轮 SQL 结果。三者可以同时进入 Planner，但来源和可信等级不同。

不要把私人对话索引成公共 RAG，也不要用 Profile 覆盖语义层指标定义。**当前正式规则和当前证据始终优先于历史偏好。**

## 27.5 上下文压缩：压缩文本，不要压掉事实边界

多轮对话、RAG、工具结果和 Memory 很容易共同撑满窗口。解决办法不是把所有内容交给模型“总结一下”。LLM 摘要可能改写数字、丢引用或把旧版本和新版本混在一起。

更稳的做法是按类型裁剪：

- Working：保留当前目标、最后成功观察、关键错误、未完成事项；
- Tool Result：大对象转 `result_ref`，关键数字结构化保存；
- Episodic：top-k + 用户/租户过滤 + 时间衰减；
- Profile：只注入与当前任务相关的稳定偏好；
- Org Context：只注入当前版本；
- RAG：保留 EvidenceRef/citation，不让 Memory 摘要替代原证据。

关键数值、SQL、审批意见、artifact hash、Policy 决策不应被自然语言摘要重写。

**上下文压缩的目标是减少 token，而不是把结构化事实重新变成一段无法校验的自然语言。**

## 27.6 污染、冲突、过期和删除：Memory 必须允许“忘记”

长期运行后的主要风险不是召回率低，而是错误记忆持续生效：一次错误偏好、过期组织规则、被提示注入污染的事实或跨租户条目，可能在未来很多 Run 中被反复使用。

污染治理至少需要四个动作：

1. **定位**：找到 `memory_id`、来源 Run、写入策略版本和最近使用记录；
2. **判断**：是错误写入、错误召回、权限问题还是过期；
3. **修复**：删除、降权、重新摘要、缩小作用域或请求用户确认；
4. **回放**：在受影响样本上验证问题是否真正消失。

冲突也要有确定规则。例如用户新偏好应覆盖旧偏好；正式 Org Context 覆盖个人推断；同一来源的多个版本按有效期选择；无法自动裁决时应澄清，而不是把冲突记忆一起塞给模型。

删除必须覆盖主存储、向量索引、缓存和后续可检索副本。审计记录可以按法规和企业策略保留不可变证据，但**“历史上发生过”与“未来还能被模型使用”是两件事。**

## 27.7 用户控制面、评测与 mini-platform

用户不必看到所有内部状态，但长期 Memory 至少要做到可解释、可纠正、可删除。一个实用的控制面可以展示：

- 系统记住了什么类型的信息；
- 来源是用户确认、系统推断还是组织配置；
- 最近什么时候被使用；
- 作用范围；
- 删除/停用入口。

当 Memory 实际影响工具参数、报告格式或推荐时，产品可以适度解释，例如“沿用你上次确认的同比表格格式”，而不是静默改变任务。

Memory 评测不能只看“命中了多少”。至少要比较：

1. 该记住的信息是否被正确复用；
2. 不该记住的信息是否被阻止；
3. 过期/删除的信息是否真正不再影响行为；
4. 启用 Memory 后是否改变权限、指标口径或正式证据；
5. 同一任务开关 Memory 后，工具参数和结果是否出现不合理偏移。

评测环境应使用受控 Memory 快照，不能读取真实用户历史，否则不同版本结果不可比较。

mini-platform 当前最值得先做扎实的是 Working Memory + checkpoint：

```text
mini-platform/core/memory/
├── working.py
└── store.py

core/runtime/
├── run_models.py
└── run_loop.py
```

生产演进顺序建议是：Working/恢复 → 作用域与删除 API → Profile 候选/确认 → Episodic → Org Context 版本 → 污染回放与用户控制面。

**长期记忆如果还做不到查看、删除、过期和作用域隔离，宁可先不上，也不要悄悄永久保存用户对话。**

## 本章小结

Memory 是受治理的上下文系统，不等于聊天历史，也不等于 RAG。Working Memory 支撑 Run 恢复；Episodic 保存带来源的任务经验；Profile 保存用户确认或高置信的稳定偏好；Org Context 保存正式组织规则。

长期 Memory 的关键能力包括写入准入、作用域、版本、过期、冲突处理、污染修复和删除。上下文再丰富，也不能覆盖当前权限、语义层和正式证据。

**Memory 的成熟度，不看系统能“记住多少”，而看它是否知道哪些信息只能临时使用、哪些可以长期复用，以及用户或组织改变主意后能否真正停止使用旧记忆。**

## 参考文献

Wang, L., Ma, C., Feng, X., et al. (2024). A survey on large language model based autonomous agents. *Frontiers of Computer Science*, 18(6), 186345.

Chhikara, P., Khant, P., Yadav, P., et al. (2025). *mem0: Building production-ready AI agents with scalable long-term memory*.

Packer, C., Wooders, S., Lin, K., et al. (2023). *MemGPT: Towards LLMs as operating systems*.

Letta. (n.d.). *Letta documentation*.

Zhang, Z., Wang, Y., Fang, C., et al. (2024). *A survey on the memory mechanism of large language model-based agents*.

LangChain. (n.d.). *LangGraph Persistence*.
