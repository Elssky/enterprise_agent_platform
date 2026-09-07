# 第16章 嵌入模型

---

企业做 RAG、DataAgent、客服或多模态检索时，真正的第一步不是选向量数据库，而是决定**什么内容要被表示成向量、哪些相似关系值得学习，以及向量检索只承担哪一段责任**。

员工问“出差回来多久要报销”，制度写的是“返回后十五个工作日内提交申请”；分析师说“高客单门店”，仓库里可能叫 `avg_order_value_store_segment`。Embedding 的价值，是先把这些不同表达映射成语义候选。它不负责判断事实是否正确，也不负责权限、引用和最终业务动作。

**Embedding 是候选召回器，不是事实裁判。** 企业平台要在向量召回之后继续使用 metadata filter、reranker、语义层、规则校验和人工复核，把“相似”收敛成“可用证据”。

## 16.1 企业场景：先定义语义候选，再决定是否平台化

企业知识库、客服、DataAgent、法务和多模态巡检的下游流程不同，但 embedding 在其中的职责高度一致：把问题、文档、字段、条款、图片等编码成可比较表示，找出可能相关的候选。

对 DataAgent，第一批高价值对象往往不是长文档，而是指标口径、维度说明、字段注释、表关系、历史 SQL、业务术语和报表截图。用户问“高客单门店的复购趋势”时，embedding 先给出指标和字段候选，语义层再确认口径，NL2SQL 才进入执行。

![图16-1：企业 embedding 能力链路](../../images/part4/ch/ch16-01-embedding-capability-chain.svg)

*图16-1：企业 embedding 能力链路。来源：本书自绘。Alt text：横向链路依次为文档/查询输入、嵌入模型编码、向量入库、相似度检索、结果返回，箭头表示原始内容经嵌入后进入可检索状态。*

![图16-2：企业级 Agent 平台中的语义接口层](../../images/part4/ch/ch16_enterprise_agent_platform.png)

*图16-2：企业级 Agent 平台中的语义接口层。来源：本书自绘。Alt text：分层图中嵌入服务作为语义接口层，向下对接向量库与文档源，向上为 RAG、知识助手等多个 Agent 提供统一的向量化与检索接口。*

平台投入应按风险和复用范围决定：普通制度问答可以先用商业 API 或轻量开源模型建立 baseline；合同、财务、人事等敏感场景优先评估私有化；多个业务共享知识库、DataAgent 和客服时才值得建设统一 embedding 服务。多模态只有在截图、票据、巡检照片等视觉证据真正影响任务时才有必要。

**上线前最重要的不是“模型分数够不够高”，而是 query、模型版本、索引版本、过滤条件、候选、重排结果和最终引用是否能被回放。**

## 16.2 向量表示：模型、维度、归一化和 metric 必须绑定

Embedding 输出固定维度向量，常见相似度包括 cosine、dot product 和 Euclidean distance。

*表16-1：常见向量相似度度量对比。来源：本书整理。*

| 度量 | 直觉 | 常见用法 | 工程注意点 |
|---|---|---|---|
| Cosine similarity | 比较向量方向 | 文本语义检索、相似案例、知识库问答 | 向量是否归一化要在模型服务和向量库中保持一致 |
| Dot product | 方向和长度一起参与 | 很多 embedding API 和向量库支持 | 不同模型、不同归一化策略不能混用 |
| Euclidean distance | 比较几何距离 | 聚类、传统机器学习、少量检索任务 | 高维空间中距离直觉容易失效 |

![图16-3：向量生成与相似度计算链路](../../images/part4/ch/ch16-03-vector-similarity-pipeline.svg)

*图16-3：向量生成与相似度计算链路。来源：本书自绘。Alt text：左侧文本经分词与编码生成向量，右侧查询向量与库中向量做相似度计算（余弦/点积）并排序，箭头展示从文本到相似度排序的完整过程。*

如果向量已经归一化，cosine 与 dot product 排序通常接近；未归一化时，向量长度会影响结果。生产系统至少要把 `model_name`、`model_version`、`dimension`、`normalized`、`metric` 和 `index_version` 绑定起来。

```json
{
  "source_id": "policy-2026-hr-001",
  "chunk_id": "policy-2026-hr-001#p12#c03",
  "text_hash": "sha256:...",
  "model_name": "bge-m3",
  "model_version": "2026-embedding-baseline",
  "dimension": 1024,
  "normalized": true,
  "metric": "cosine",
  "index_version": "kb-hr-v7",
  "metadata": {
    "tenant_id": "tenant-a",
    "department": "hr",
    "acl": ["hr", "finance_manager"],
    "source_version": "v3",
    "effective_at": "2026-01-01"
  }
}
```

同一索引不能混用不同模型空间。模型升级时应构建新索引或双写灰度，而不是让新 query 向量继续命中旧文档向量。维度也不是“越大越好”：它会直接增加存储、内存、重建时间和查询成本。

**向量相似不等于可回答，权限更不能隐含在相似度里。** 租户、部门、角色、文档状态和生效时间都应作为显式 metadata 参与过滤。

## 16.3 文本 embedding 选型：公开榜单筛候选，内部样本决定上线

企业模型选型应覆盖 SaaS、开源私有化、国产生态和行业专用路线。

*表16-2：文本 embedding 模型路线取舍表。来源：本书整理。*

| 方案 | 优势 | 代价 | 适用场景 | mini-platform 选择 |
|---|---|---|---|---|
| 商业 API，如 OpenAI Embedding、Cohere Embed、Voyage | 接入快、稳定性好、SDK 完整 | 数据出域、单价、配额和供应商锁定 | 非敏感知识库、快速试点 | 作为 SaaS baseline |
| 开源通用模型，如 BGE-M3、E5、GTE、Jina | 可私有化、长期可控 | 需要推理服务、评测和资源治理 | 中文/多语言知识库、客服、字段说明 | 默认私有化候选 |
| 国产生态模型，如 Qwen3 Embedding | 易与国产 LLM、私有云和硬件协同 | 需评估版本、推理适配和生态成熟度 | 国内企业、国产化要求 | 并行候选 |
| 行业专用模型 | 垂域术语可能更强 | 授权、迁移、泛化和评测成本高 | 金融、法务、医疗等专业领域 | 垂域评测胜出后采用 |

选型维度不只包括公开 benchmark，还要覆盖语言和术语、有效文本长度、部署方式、维度、吞吐/延迟、生态和版本治理。

*表16-3：文本 embedding 模型选型维度。来源：本书整理。*

| 维度 | 要问的问题 | 影响 |
|---|---|---|
| 语言和术语 | 中文、英文、行业缩写、内部黑话是否覆盖 | 召回质量和 hard negative 难度 |
| 文本长度 | 制度、合同、表格转写是否超出有效长度 | chunk 策略和长文档召回 |
| 部署方式 | API、私有云、离线、国产硬件是否支持 | 合规、运维、上线周期 |
| 向量维度 | 是否可降维、是否归一化 | 存储、内存、索引重建、延迟 |
| 推理性能 | batch、QPS、CPU/GPU、p95 | 在线查询和离线重建 |
| 版本治理 | 升级是否可控、旧索引能否回滚 | 线上稳定性 |

![图16-4：文本 embedding 模型选型流程](../../images/part4/ch/ch16-04-text-embedding-selection.svg)

*图16-4：文本 embedding 模型选型流程。来源：本书自绘。Alt text：决策流程从语言/术语覆盖、数据敏感度、延迟成本要求出发，逐步筛出 API 模型或私有化模型，并以评测基线收尾，体现按约束选型。*

*表16-4：文本 embedding 选型报告的分层结论。来源：本书整理。*

| 场景 | 推荐结论写法 |
|---|---|
| 普通知识库 | 选择召回质量和延迟都稳定的模型，先保证正确证据进入 top-k |
| 敏感数据 | 优先选择可私有化、可审计、可长期维护的模型 |
| 业务术语密集 | 先补术语表、字段注释和 hard negatives，再决定是否微调 |
| 高风险问答 | embedding 只做第一阶段召回，需要 reranker、引用校验和人工复核 |

**公开排行榜告诉你“值得测谁”，内部 query、golden docs 和 hard negatives 才告诉你“谁能上线”。**

## 16.4 多模态 embedding：视觉相似不能替代结构化证据

当知识藏在截图、扫描页、票据、图表和巡检照片中时，多模态 embedding 可以补纯文本检索的盲区。CLIP、SigLIP、ColPali 等路线说明图像和文本可以进入共享或可比较语义空间。

*表16-5：多模态 embedding 的企业场景与上线控制。来源：本书整理。*

| 场景 | 传统问题 | 多模态 embedding 的作用 | 发布控制 |
|---|---|---|---|
| 质检巡检 | 缺陷照片难完整文字化 | 找相似缺陷、批次和历史处理单 | 图片权限、拍摄规范、误判复核 |
| 合同和票据 | OCR 易丢印章、版式和表格关系 | 找相似条款、金额区域、审批痕迹 | 页码引用、金额校验、人工复核 |
| 数据看板截图 | 用户只有截图，不知道字段名 | 对齐指标说明、报表文档、字段注释 | 截图脱敏、版本识别、字段映射 |
| 商品检索 | 图片、标题、评论表达不同相似性 | 图文联合召回相似商品 | 类目、库存、价格约束 |
| 设备运维 | 现场照片和故障描述不一致 | 找相似设备状态和维修记录 | 设备权限、时间地点、图片质量 |

![图16-5：多模态检索数据流](../../images/part4/ch/ch16-05-multimodal-retrieval-flow.svg)

*图16-5：多模态检索数据流。来源：本书自绘。Alt text：图片与文本分别经各自编码器映射到同一向量空间，查询可跨模态检索，箭头表示以图搜图、以文搜图共享同一向量索引。*

![图16-6：企业多模态检索场景](../../images/part4/ch/ch16_企业多模态检索场景.png)

*图16-6：企业多模态检索场景。来源：本书自绘。Alt text：列举质检巡检、合同截图、商品图、工单照片等场景，各自标注用图像嵌入解决的检索问题，展示多模态嵌入的企业落点。*

OCR/版面解析仍负责把金额、日期、表格和页码变成可验证结构；多模态 embedding 更适合视觉相似和图文候选。两张图片相似，不代表根因相同；两页合同版式相似，也不代表风险条款相同。

## 16.5 企业评测：质量、权限、延迟和成本必须同表比较

最小评测集应包含真实 query、golden docs、hard negatives、metadata filter 和人工 judgment。

*表16-6：embedding 评估集的基本对象。来源：本书整理。*

| 对象 | 内容 | 示例 |
|---|---|---|
| Query | 真实问题、改写、口语、跨语言问题 | “出差回来后多久必须提交报销？” |
| Golden docs | 应召回的文档、chunk、字段说明或页面区域 | `travel-policy#p12#c03` |
| Hard negatives | 语义相近但不能回答的材料 | 报销额度制度、审批权限说明 |
| Metadata filter | 部门、租户、权限、时间、文档状态 | `department=finance` |
| Judgment | 相关、部分相关、不相关；是否支持答案 | `relevant / partial / irrelevant` |

*表16-7：企业 embedding 评估指标。来源：本书整理。*

| 指标 | 看什么 | 适合谁看 |
|---|---|---|
| recall@k | 正确证据是否进入前 k | 检索工程师、架构师 |
| MRR | 正确证据是否排得靠前 | 检索工程师 |
| nDCG | 多个相关结果的排序质量 | 评测负责人 |
| answer citation hit rate | 回答是否引用正确证据 | RAG/业务 Owner |
| p50/p95 latency | 查询延迟 | 平台负责人 |
| cost/query | 单次或千次查询成本 | 平台/财务负责人 |
| index size / rebuild time | 存储、灾备、升级成本 | 架构/运维 |
| permission violation rate | 是否召回无权内容 | 安全/合规 |

*表16-8：embedding 发布前工程检查项。来源：本书整理。*

| 检查项 | 要确认的内容 | 常见失败 |
|---|---|---|
| 权限过滤 | query 与召回都经过租户、部门、角色、状态过滤 | 无权候选进入日志或 trace |
| 模型版本 | 文档、查询、索引使用同一模型空间 | 查询模型升级后旧索引未重建 |
| 索引重建 | 全量、增量、续跑和回滚计划 | 文档更新后索引版本混乱 |
| 成本口径 | 离线建库、在线查询、reranker 分开统计 | 只看 embedding 单价 |
| 可观测性 | query、top-k、filter、citation、latency、版本 | 线上下降无法复盘 |
| 人工复核 | 高风险场景有审批、拒答和申诉入口 | 相似候选被直接当结论 |

```text
mini-platform/projects/embedding-vector-benchmark/
├── data/evals/retrieval_queries.jsonl
├── configs/openai.yaml
├── configs/bge_m3.yaml
├── configs/qwen3_embedding.yaml
├── reports/embedding_benchmark.md
└── src/{embed,index,retrieve,evaluate}.py
```

```json
{
  "query_id": "q-001",
  "query": "出差回来后多久必须提交报销？",
  "golden_chunk_ids": ["travel-policy#p12#c03"],
  "hard_negative_chunk_ids": ["reimbursement-guide#p02#c01"],
  "metadata_filter": {"department": "finance"},
  "risk_level": "medium"
}
```

![图16-7：embedding benchmark 数据流](../../images/part4/ch/ch16-07-embedding-benchmark-flow.svg)

*图16-7：embedding benchmark 数据流。来源：本书自绘。Alt text：评测流程从标注查询集出发，经各候选模型编码、检索、计算 recall@k 与延迟，输出对比报告，箭头表示同一评测集横向比较多个模型。*

*表16-9：embedding benchmark 报告结论示例。来源：本书整理。*

| 结论项 | 示例 |
|---|---|
| 默认模型 | BGE-M3 在中文制度问答中召回稳定，适合作为私有化 baseline |
| SaaS baseline | OpenAI Embedding 延迟和稳定性较好，适合非敏感知识库快速上线 |
| 高风险场景 | 合同和财务问答必须增加 reranker、引用校验和人工复核 |
| 主要失败原因 | “高客单”“账期”“返利”等业务词需要补术语表和 hard negatives |
| 下一步 | 扩充评测集，加入表格和多模态截图检索 |

## 16.6 生命周期：把失败样本、索引迁移和成本治理放在同一闭环

Embedding 上线后会因新术语、新政策、新字段、新产品和新文档格式发生业务退化。常见信号包括正确证据排名下降、hard negative 排名上升、权限过滤后候选不足、用户频繁改引用、DataAgent schema linking 选错字段。

失败样本应保存 query、用户角色、可访问范围、期望文档、错误候选、chunk id、文档版本和修复动作。进入训练或评测前还要完成脱敏、授权和用途登记。

模型、chunk、metadata 或索引参数变化时，应构建影子索引，使用同一批 query 横向比较，再按知识库/租户灰度。发布记录至少绑定：

`embedding_model + chunk_strategy + metadata_schema + index_version + reranker + eval_set`

旧索引在稳定窗口结束后应归档或删除，过期文档和失效 ACL 也要同步清理。容量治理不能简单删除低频文档：低频合规证据可能仍很重要，可以区分热知识、温知识和冷证据。

**Embedding 的长期资产不是某个模型，而是“业务样本 + 版本化索引 + 可解释发布”这套持续校准能力。**

## 本章小结

Embedding 解决语义候选召回，不负责事实判断和权限裁决。企业选型应从真实语料、敏感边界、成本和内部评测出发，而不是从排行榜开始。

模型、维度、归一化、metric 和索引版本必须绑定；多模态检索要与 OCR、版面和结构化校验协同；评测必须同时覆盖召回、排序、引用、权限、延迟和成本。

**稳定的语义检索依赖的不是一次“选对模型”，而是持续积累 hard negatives、业务失败样本，并让每次向量空间变化都可评估、可灰度、可回滚。**

## 参考文献

- Azure AI Search vector search overview：[https://learn.microsoft.com/en-us/azure/search/vector-search-overview](https://learn.microsoft.com/en-us/azure/search/vector-search-overview)
- Google Vertex AI Embeddings APIs overview：[https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings](https://cloud.google.com/vertex-ai/generative-ai/docs/embeddings)
- Amazon Bedrock Knowledge Bases overview：[https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- OpenAI Embeddings guide：[https://platform.openai.com/docs/guides/embeddings](https://platform.openai.com/docs/guides/embeddings)
- BGE-M3 model card：[https://huggingface.co/BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)
- MTEB leaderboard：[https://huggingface.co/spaces/mteb/leaderboard](https://huggingface.co/spaces/mteb/leaderboard)
- OpenAI CLIP：[https://openai.com/index/clip/](https://openai.com/index/clip/)
- SigLIP paper：[https://arxiv.org/abs/2303.15343](https://arxiv.org/abs/2303.15343)
- ColPali paper：[https://arxiv.org/abs/2407.01449](https://arxiv.org/abs/2407.01449)
