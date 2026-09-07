# 第18章 向量数据库与索引算法

---

向量数据库承接 RAG 的检索执行：保存向量和 metadata，在给定权限、索引与过滤条件下返回近似最近邻。Embedding 生成、业务语义、最终权限裁决和答案正确性仍属于其他组件。

企业向量库事故很少表现为“数据库挂了”。更常见的是：无权文档进入候选、旧制度仍被召回、embedding 升级后新旧向量混在一起，或删除了源文件却没有删向量、缓存和评测样本。

**向量库不是一个可随时清空的缓存，而是 RAG 证据链的一部分。它必须同时管理召回、权限、版本、删除、回滚和成本。**

## 18.1 平台定位：先定义检索契约，再讨论产品

知识库、客服、法务和 DataAgent 都可能共享向量能力，但它们的权限、新鲜度和质量目标不同。平台至少要提供统一的写入、查询、版本和观测契约。

*表18-1：向量库在企业平台中的职责。来源：本书整理。*

| 职责 | 说明 | 不负责什么 |
|---|---|---|
| 向量索引 | 管理 embedding、metric、index type、namespace、版本 | 不负责生成 embedding |
| metadata 过滤 | 按租户、部门、权限、生效时间、文档状态过滤 | 不替代统一权限系统 |
| 近似检索 | 在延迟和召回之间折中 | 不保证最终答案正确 |
| 生命周期治理 | 重建、双写、灰度、回滚、压缩和归档 | 不替代数据血缘与审计 |
| 观测与成本 | QPS、p95、召回、过滤命中、索引大小 | 不解释业务语义错误 |

![图18-1：向量库在企业 Agent 平台中的位置](../../images/part4/ch/ch18-01-vectorstore-platform.svg)

*图18-1：向量库在企业 Agent 平台中的位置。来源：本书自绘。Alt text：分层图中向量库位于嵌入服务之下、RAG 与知识助手之上，存储向量与元数据并对外提供带权限过滤的检索接口，标出其"可检索知识存储"职责。*

![图18-2：企业向量库多租户控制台](../../images/part4/ch/ch18-02-vector-console-atlas.png)

*图18-2：企业向量库多租户控制台。来源：产品界面截图。Alt text：控制台界面展示按租户划分的集合列表、向量规模、索引类型与权限配置，体现向量库以租户为单位做隔离与配额管理。*

早期中小规模、强 SQL/事务需求可以从 pgvector 起步；当多个业务共享、大规模 ANN、高 QPS、多租户重建成为主要矛盾时，再评估专用向量系统。**共享平台的触发条件是复用和治理复杂度，不是“向量数量看起来很多”。**

## 18.2 ANN 算法：召回、内存、构建和更新之间没有免费午餐

少量向量可以做精确距离计算，规模扩大后通常使用 ANN。主流路线包括 HNSW、IVF、PQ/SQ 和磁盘索引。

*表18-2：ANN 索引算法谱系。来源：本书整理。*

| 算法路线 | 直觉 | 优势 | 代价 |
|---|---|---|---|
| HNSW | 多层近邻图中导航搜索 | 召回和延迟稳定、生态成熟 | 内存高、构建参数敏感 |
| IVF | 先聚类分桶，再搜索少量桶 | 大规模可控、易与压缩组合 | 需训练中心，参数不当会漏召回 |
| PQ/SQ | 低比特近似表示向量 | 显著降低内存/存储 | 分数精度下降，常需精排补偿 |
| DiskANN/磁盘索引 | 以磁盘和缓存承载大索引 | 降低内存压力 | 延迟抖动、冷热和硬件更敏感 |
| 精确检索 | 全量计算距离 | 结果明确、小规模 baseline 好用 | 大规模不可扩展 |

![图18-3：ANN 索引算法谱系图](../../images/part4/ch/ch18-03-ann-taxonomy-atlas.png)

*图18-3：ANN 索引算法谱系图。来源：本书自绘。Alt text：树状谱系把 ANN 索引分为基于图（HNSW）、基于量化（IVF-PQ）、基于树/哈希等分支，每个叶子标注召回、延迟、内存特征，展示索引家族关系。*

参数调优必须使用企业真实过滤条件和长尾样本。无过滤公开 benchmark 上表现很好的 HNSW 配置，在“租户 + 部门 + 生效时间”强过滤下可能完全不同。`ef_search`、IVF probe 数、量化精度、top-k 和 reranker 应放到一条质量—延迟—成本曲线上比较。

**索引参数没有“最佳默认值”，只有在当前向量空间、数据分布、过滤和业务 SLO 下可接受的折中。**

## 18.3 数据库选型：看系统边界，不看品牌排行榜

*表18-3：主流向量库路线取舍表。来源：本书整理。*

| 方案 | 优势 | 代价 | 适用场景 | mini-platform 选择 |
|---|---|---|---|---|
| pgvector | PostgreSQL SQL、事务、权限和元数据统一 | 超大规模 ANN 能力有限 | 中小知识库、DataAgent 字段检索 | 默认 baseline |
| Milvus | 大规模向量检索、分布式和索引类型丰富 | 组件和运维更多 | 大规模共享向量平台 | 大规模候选 |
| Qdrant | payload filtering、服务化 API 友好 | 要额外治理与业务库一致性 | 多租户 RAG、强过滤 | 服务化候选 |
| Weaviate | schema、模块化向量化、检索 API 完整 | 既有平台集成需评估 | 快速知识应用 | 产品化候选 |
| Vespa | 搜索、推荐、多阶段 ranking 表达强 | 学习与部署复杂 | 大规模搜索/推荐、复杂 ranking | 高级搜索候选 |

真正需要比较的是：metadata filter 在 ANN 前后如何执行、索引能否不停服重建、租户隔离方式、备份恢复、删除语义、查询审计，以及能否稳定与 BM25、数据目录和 reranker 组合。

企业通常不应把传统搜索全部迁到向量库。编号、字段名、错误码和条款号更适合关键词检索，口语和同义表达更适合向量，后续再统一融合与重排。

**一个单库 recall 更高但难以接入 ACL、混合检索和版本回滚的方案，未必比轻量、可治理的方案更适合生产。**

## 18.4 Metadata filter 与多租户：权限要在候选空间里生效

向量相似度本身不理解租户、密级和生效时间。每条记录至少需要一套稳定 metadata。

*表18-4：metadata 字段设计。来源：本书整理。*

| 字段 | 用途 | 示例 |
|---|---|---|
| `tenant_id` | 租户隔离 | `tenant-a` |
| `acl` | 角色或部门权限 | `finance_manager` |
| `source_type` | 文档、字段、工单、图片 | `policy` |
| `source_version` | 文档版本 | `v3` |
| `effective_at` | 生效时间过滤 | `2026-01-01` |
| `index_version` | 索引治理 | `kb-hr-v7` |

![图18-4：metadata filter 与多租户权限边界](../../images/part4/ch/ch18-04-metadata-permission-atlas.png)

*图18-4：metadata filter 与多租户权限边界。来源：本书自绘。Alt text：检索请求带租户与权限标签进入向量库，过滤条件在 ANN 搜索阶段一同生效（而非先召回后过滤），箭头标出无权数据在检索时即被排除。*

Pre-filter 安全边界更强，但候选过窄可能伤召回；post-filter 召回空间更大，却可能让无权内容先进入检索、重排、日志或 Trace。高风险场景应优先把租户、密级等硬边界前置，时间、状态等软条件再按质量折中。

空结果也要区分“没有相关知识”和“当前权限下没有可见证据”。这两个状态对应完全不同的用户恢复路径。

## 18.5 索引生命周期：模型、Chunk、Parser、ACL 都会触发重建

索引应被视为可发布资产，而不是一次生成的缓存。

*表18-5：索引生命周期阶段。来源：本书整理。*

| 阶段 | 关键动作 | 质量门禁 |
|---|---|---|
| 构建 | 编码、写向量/metadata、记录 lineage | 维度、metric、model version 一致 |
| 离线评测 | query 集测 recall、MRR、filter、latency | 不低于 baseline，失败可解释 |
| 双写灰度 | 新旧索引接收更新，shadow query 对比 | 候选和权限差异可追踪 |
| 切流 | 小流量逐步全量 | p95、错误、引用稳定 |
| 回滚 | 保留旧索引和旧模型 | 回滚路径可用 |
| 归档 | 下线旧索引，保留审计元数据 | 历史 Trace 可解释 |

触发重建的不只是 embedding 模型，还有 parser、chunk、metadata schema、ACL 和索引参数。生产版本最好用组合 ID 描述：

`parser + chunk + embedding + metadata_schema + index_params + acl_policy`

删除同样是全链路动作。一份文档撤回后，需要同步处理原文、chunk、向量、倒排索引、reranker 缓存和相关评测样本；租户删除、ACL 撤回也一样。

向量库应提供诸如 `delete_by_source`、`delete_by_acl`、`rebuild_by_source` 的平台接口，而不是让各应用写临时清理脚本。

## 18.6 Benchmark 与运行回放：静态快不够，动态也要稳

选型 benchmark 应同时覆盖质量、系统和治理指标。

```yaml
experiment: vectorstore_benchmark
query_set: data/eval/enterprise_queries.jsonl
models:
  - name: bge-m3-baseline
  - name: bge-m3-finetuned
stores:
  - provider: pgvector
    index: hnsw
  - provider: qdrant
    index: hnsw
metrics:
  quality: [recall@10, mrr@10, ndcg@10]
  system: [p50_latency_ms, p95_latency_ms, qps, index_size_mb]
  governance: [filter_hit_rate, acl_violation_count, rebuild_time_min]
```

![图18-5：向量库 benchmark 报告总览](../../images/part4/ch/ch18-05-vector-benchmark-atlas.png)

*图18-5：向量库 benchmark 报告总览。来源：本书自绘。Alt text：报告页对比多个向量库在召回率、P95 延迟、写入吞吐、内存占用上的指标曲线，并标注不同索引参数下的取舍点。*

除了静态查询，还要测试高频写入、批量删除、ACL 更新、夜间重建和紧急回滚。否则最漂亮的只读 benchmark 可能掩盖真实生产瓶颈。

一次检索回放至少应保存：原 query、query rewrite、embedding 版本、索引版本、filter、top-k、reranker、最终 chunk 以及被过滤候选数量。

**“被过滤掉了多少、为什么被过滤”同样是检索证据。候选从 80 条过滤到 3 条，不能被误诊为 embedding 召回差。**

缓存也必须绑定索引版本、用户权限和过滤条件。知识库重建或权限变化时，旧缓存必须失效，否则同一会话可能混用两套证据空间。

## 18.7 容量、灰度与退役：控制知识基础设施的长期复杂度

容量会因为文档版本、chunk 副本、多模型、多租户、灰度索引和缓存快速增长。成本治理不能只按“低频就删”，因为低频知识可能是关键合规证据。

可以按热知识、温知识、冷证据分层：高频知识保持在线高性能；温知识降低副本或使用更慢索引；冷证据保留原文与 metadata，需要时再进入在线检索。

索引变更应采用 shadow retrieval：线上继续用旧索引回答，新索引后台跑同一请求，比较候选、分数、权限和引用。稳定后按租户或知识域切流。

退役旧索引前要扫描调用日志、配置、缓存、评测和历史报告，确认是否仍有依赖。历史 Trace 需要保留旧版本参数，当前检索则停止引用旧资产。

**向量平台的成熟度，不是“索引越来越多”，而是每个索引都知道为什么存在、谁在用、何时重建、怎样退出。**

## 本章小结

向量数据库负责在受控候选空间里执行高效检索，不负责生成 embedding 或决定最终事实。HNSW、IVF、PQ 和磁盘索引需要在召回、内存、延迟、更新与过滤条件下联合评测。

Metadata filter 是企业检索的安全边界；索引版本必须绑定模型、解析、chunk 和 ACL；删除、灰度、回滚和缓存也要进入同一生命周期。

**企业选向量库最终选的不是 ANN 算法，而是一套能稳定管理候选证据、权限和版本变化的知识基础设施。**

## 参考文献

- pgvector: https://github.com/pgvector/pgvector
- Milvus Index Documentation: https://milvus.io/docs/index.md
- Qdrant Filtering: https://qdrant.tech/documentation/search/filtering/
- Weaviate Documentation: https://weaviate.io/developers/weaviate
- Vespa Approximate Nearest Neighbor Search: https://docs.vespa.ai/en/nearest-neighbor-search.html
- Azure AI Search Vector Search: https://learn.microsoft.com/en-us/azure/search/vector-search-overview
