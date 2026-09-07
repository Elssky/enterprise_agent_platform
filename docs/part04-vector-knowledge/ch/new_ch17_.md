# 第17章 嵌入微调与重排

---

第16章建立了 embedding baseline，真正上线后，长尾错误会集中暴露在企业术语、字段别名、合同条款和相似但不可替代的业务概念上。`customer_level`、`customer_segment`、`customer_risk_grade` 都和客户有关，但只有最后一个能回答风险问题。

此时最危险的反应，是把所有检索失败都归为“模型不够强”。问题可能来自解析、chunk、字段说明、权限过滤或 query rewrite；只有瓶颈确实落在语义匹配和排序阶段，微调和 reranker 才值得投入。

**先判断“正确证据有没有进入候选”，再决定改 embedding 还是上 reranker。微调改变向量空间，重排改变候选顺序，两者的发布风险完全不同。**

## 17.1 先归因：哪些错误值得训练

企业内部常同时存在业务语言、系统字段和历史叫法。领域适配真正要解决的是“哪些表达在本企业可以互相替代，哪些只是主题相近”。

*表17-1：领域语义适配的触发信号。来源：本书整理。*

| 触发信号 | 典型表现 | 优先动作 |
|---|---|---|
| 内部术语召回弱 | 用户问题和文档字段不共词，top-k 漏掉正确 chunk | 先补术语表、字段注释和 query 改写样本 |
| hard negative 混淆 | top-k 常出现“很相关但不能回答”的材料 | 构造 query-positive-negative，训练或重排 |
| 长尾表达多 | 客服、研发、门店输入口语化 | 从真实日志抽样做评测集 |
| 合规证据要求高 | 正确证据能召回但排位不稳 | 优先 reranker + 引用校验 |
| 跨语言/跨系统别名 | 缩写、字段和业务别名交叉 | 别名词表 + schema linking 样本 |

错误可以进一步拆成四类：

1. **召回不到**：可能需要补语义资产或微调 embedding；
2. **召回到了但排序靠后**：优先 reranker；
3. **召回的是相似但不可回答材料**：需要 hard negative、规则与证据校验；
4. **权限过滤后候选不足**：这是 ACL/metadata 问题，不能靠训练解决。

*表17-2：平台负责人微调与重排决策要点。来源：本书整理。*

| 决策问题 | 推荐判断 |
|---|---|
| 是否先微调 embedding | 只有错误稳定、样本可标注、baseline 可复现时才微调 |
| 是否先上 reranker | 正确证据已进入候选但排位靠后时优先上 reranker |
| 是否允许外部 reranker | 敏感合同、财务、人事优先私有化或脱敏 |
| 是否能进入生产 | 必须有 hard negative、失败样例、模型/索引版本和回滚 |
| 何时停止投入 | 根因在解析、chunk、权限时停止训练，先修链路 |

![图17-1：嵌入微调与重排在检索链路中的位置](../../images/part4/ch/ch17-01-finetune-rerank-architecture.svg)

*图17-1：嵌入微调与重排在检索链路中的位置。来源：本书自绘。Alt text：检索链路依次为查询编码、向量召回（嵌入模型负责）、重排精排（reranker 负责）、返回 top-k，标出微调作用于召回、重排作用于精排两个不同环节。*

**“先归因、后训练”是这一章最重要的工程纪律。**

## 17.2 对比学习与 hard negative：训练企业真正关心的边界

Embedding 微调不是把更多公司文档喂给模型，而是定义“什么应该相似、什么虽然像但不能替代”。

*表17-3：检索微调样本形态。来源：本书整理。*

| 样本形态 | 示例 | 适合任务 | 风险 |
|---|---|---|---|
| 正样本 pair | “报销多久到账” ↔ “财务付款周期说明” | FAQ、制度、字段别名 | 太容易的正样本学不到边界 |
| 三元组 | query、正确 chunk、相似但错误 chunk | 合同、工单、schema linking | negative 标错会打歪模型 |
| 多级相关性 | 相关、部分相关、不相关 | reranker 训练和评估 | 标注成本高、需一致性检查 |
| 伪标签 | LLM/历史点击生成标签 | 冷启动 | 必须人工抽检，防止放大旧偏差 |

Hard negative 是最有价值的训练资产。报销额度不能回答报销时限，续约通知不能证明自动续费责任，`customer_level` 也不能替代 `customer_risk_grade`。

*表17-4：hard negative 的来源与处理。来源：本书整理。*

| 来源 | 获取方式 | 使用建议 |
|---|---|---|
| baseline top-k 错误 | 现有 embedding 检索后人工标错候选 | 最优先，直接对应真实失败 |
| BM25 高分错误 | 关键词高分但语义不可答 | 处理共词误导 |
| 同类字段/条款 | 同表、同模板、同流程里的相邻对象 | DataAgent、法务高价值 |
| LLM 生成近似问题 | 改写 query 后挖混淆项 | 只做候选，不能免复核 |

![图17-2：企业语义适配样本工作台](../../images/part4/ch/ch17-02-generated.png)

*图17-2：企业语义适配样本工作台。来源：本书自绘。Alt text：界面分区展示查询、正样本、难负例标注列表与标注进度，右侧是样本质量统计，体现把线上日志转化为训练样本的人工工作台。*

![图17-3：hard negative 错误分析矩阵](../../images/part4/ch/ch17-03-hard-negative-matrix-atlas-v2.png)

*图17-3：hard negative 错误分析矩阵。来源：本书自绘。Alt text：矩阵按"语义相近但不相关"和"字面相近但语义无关"等维度归类难负例，每格给出典型例子，帮助定位难负例的来源类型。*

每条训练样本至少记录 `query_id`、positive/negative id、来源、业务域、ACL、标注人、复核状态和时间。点击日志和 LLM 伪标签都只是候选，不能直接变成真值。

**企业微调最缺的往往不是样本数量，而是能解释业务边界的高质量难负例。**

## 17.3 微调路线：先修资产，再动向量空间

合理路线通常是四步：

1. 固定真实 query 与 baseline，形成可复现失败清单；
2. 先补术语、字段说明、query rewrite、metadata；
3. 错误仍稳定存在时做小规模对比学习；
4. 只有高价值场景持续受益，才长期维护 LoRA/adapter 或专门 embedding。

*表17-5：嵌入微调路线取舍表。来源：本书整理。*

| 方案 | 优势 | 代价 | 适用场景 | mini-platform 选择 |
|---|---|---|---|---|
| 不微调，补 query/术语/metadata | 风险低、上线快 | 深层语义混淆改善有限 | baseline 初期 | 默认第一阶段 |
| sentence-transformers 小规模对比学习 | 生态成熟，适合 pairs/triplets | 需样本治理、训练和索引重建 | 内部术语有稳定失败样例 | 实验路线 |
| LoRA/adapter | 训练成本相对可控、易版本化 | 部署与维护复杂 | 已有私有化模型平台 | 后续扩展 |
| 不改 embedding，引入 reranker | 不改向量空间、回滚简单 | 增加二阶段延迟与成本 | 正确证据已进 top-k | 优先实现 reranker 插槽 |

如果补数据后 recall 已达阈值，就不必继续训练；如果微调提高平均分但高风险样本退化，也不能发布。

Embedding 微调意味着文档向量和查询向量同时改变，必须构建新索引。生产流程应是：离线新索引 → 回归评测 → shadow query → 小流量灰度 → 稳定后切流，并保留旧索引回滚。

![图17-4：embedding 微调版本灰度流程](../../images/part4/ch/ch17-04-embedding-rollout-atlas.png)

*图17-4：embedding 微调版本灰度流程。来源：本书自绘。Alt text：流程从新版本嵌入模型上线小流量，到回归评测对比基线、逐步放量、异常回滚，箭头表示按评测结果控制放量节奏。*

**微调 embedding 不是一次模型替换，而是一次“向量空间 + 索引”联合版本变更。**

## 17.4 Reranker：召回负责不漏，重排负责把证据放前面

二阶段检索中，bi-encoder/embedding 从全量文档召回几十到几百个候选，cross-encoder/reranker 再判断 query 与候选的精细匹配程度。

*表17-6：召回与重排的职责边界。来源：本书整理。*

| 环节 | 输入规模 | 模型形态 | 主要目标 | 常见指标 |
|---|---|---|---|---|
| 第一阶段召回 | 全量文档/字段/工单 | embedding、BM25、混合检索 | 正确候选不要漏 | recall@k、latency |
| 第二阶段重排 | top-50/100 | cross-encoder、reranker API | 正确证据尽量排前 | MRR、nDCG、citation hit |
| 生成前过滤 | top-3~10 | 规则、权限、引用校验 | 不把不可用证据给 LLM | policy violation、citation coverage |

Reranker 不是万能纠错器：正确材料没进入候选，它无从修复；chunk 切坏了，它只能在坏候选里排序；权限过滤放在它之后，高风险内容可能已经进入外部重排服务。

```json
{
  "query_id": "q-2026-0617-00031",
  "retrieval_index": "policy-kb-v7",
  "retrieval_top_k": 80,
  "reranker": "bge-reranker-large",
  "reranker_version": "2026-06-baseline",
  "candidates": [
    {"chunk_id": "travel-policy#p12#c03", "retrieval_score": 0.74, "rerank_score": 0.91},
    {"chunk_id": "expense-limit#p02#c01", "retrieval_score": 0.78, "rerank_score": 0.21}
  ]
}
```

高风险知识库应支持 reranker 超时后的显式降级：普通场景可退回召回排序并降低置信，高风险任务应停止或人工复核，而不是静默忽略二阶段失败。

## 17.5 评测与发布：比较组合，而不是只比较模型

同一批 query 应至少比较四组：baseline embedding、微调 embedding、baseline + reranker、微调 + reranker。评测同时看质量、延迟、成本和风险。

*表17-7：嵌入微调与重排上线检查项。来源：本书整理。*

| 检查项 | 要求 |
|---|---|
| 样本治理 | 训练样本有来源、标注人、复核和权限范围 |
| 离线质量 | recall、MRR、nDCG 与 baseline 同集对比，输出失败样例 |
| 线上成本 | reranker p95、QPS、单请求成本可观测 |
| 版本隔离 | embedding、reranker、索引、chunk 分别版本化 |
| 回滚策略 | 旧模型和旧索引保留到新版本稳定 |
| 数据合规 | 敏感候选是否发往外部 reranker 必须显式审批 |

![图17-5：重排评测报告页面](../../images/part4/ch/ch17-05-rerank-report-atlas-v2.png)

*图17-5：重排评测报告页面。来源：本书自绘。Alt text：报告页展示加入重排前后的 recall@k、nDCG、延迟对比图表与逐条 case 差异，体现重排带来的质量提升与代价。*

发布报告必须列“变好样本”和“变坏样本”。一个合同续约条款从 top-1 掉到 top-7，不能被大量 FAQ 的平均提升抵消。

Shadow query 很重要：真实请求复制到新链路但仍用旧链路回答，平台先比较候选、权限、重排和延迟，再决定是否灰度。

## 17.6 生命周期：样本回流、索引迁移、责任和停止条件

上线后的失败反馈包括点踩、人工改引用、报告退回、schema linking 选错字段等。它们应进入候选样本池，但必须先判断根因，再决定是否训练。

发布资产最好以组合版本管理：

`embedding + index + chunk + metadata + reranker + eval_set + route`

这样问题发生时才能判断最近变化来自模型、索引重建、chunk、ACL 还是 query rewrite。

团队责任也应分开：数据/知识团队维护来源和文档，模型团队维护 embedding/reranker，业务 Owner 维护标注和业务边界，平台团队维护 Trace、灰度和回滚，安全团队维护数据用途与权限。

微调项目应有停止条件：

- 核心任务达到阈值且高风险样本不退化；
- 额外延迟、重建和维护成本能被业务价值覆盖；
- 模型、索引、样本和权限都能版本化和回放；
- 若根因转向文档、chunk 或权限，应立即停止继续训练。

**模型优化的成熟度也体现在“知道什么时候不该再训练”。**

## 本章小结

Embedding 微调适合稳定、可标注、可复现的领域语义差异；reranker 适合正确候选已被召回但排序靠后的场景。两者都不能修复解析、chunk、权限和知识版本问题。

Hard negative 应来自真实业务混淆并进入版本化样本资产；新 embedding 必须配新索引，重排则要把延迟、数据出域和降级策略一起纳入发布。

**检索质量优化的单位不是“模型”，而是整条召回—重排—权限—证据链。**

## 参考文献

- Sentence Transformers Training Overview: https://www.sbert.net/docs/sentence_transformer/training_overview.html
- Sentence Transformers Losses: https://www.sbert.net/docs/package_reference/sentence_transformer/losses.html
- Sentence Transformers Retrieve & Re-Rank: https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html
- Cohere Rerank: https://docs.cohere.com/docs/reranking-with-cohere
- BAAI bge-reranker model cards: https://huggingface.co/BAAI
