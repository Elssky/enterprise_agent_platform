# 企业级 Agent 平台工程 · 优化阅读版

> 当前在线版仅收录已经完成编辑优化的中文内容。未优化章节暂不发布到本页面。

这一版本以“更高信息密度、更少重复、更适合连续阅读和快速扫读”为目标。原始章节仍保留在仓库中，在线阅读页优先展示经过精简、合并和重点标注后的版本。

**当前已完成：Part I 总论与平台观（第 1–4 章）、Part II 模型与推理（第 5–9 章）、Part III 数据基础设施（第 10–15 章）与 Part IV 向量、检索与知识工程（第 16–21 章）。**

## Part I 总论与平台观

- [Part I 导读](part01-overview/ch/new_index_.md)
- [第1章 Agent 的边界：从对话助手到任务执行系统](part01-overview/ch/new_ch01-agent_.md)
- [第2章 企业级 Agent 平台的边界](part01-overview/ch/new_ch02-agent_.md)
- [第3章 AI 原生业务系统：Agent 重塑企业软件](part01-overview/ch/new_ch03-ai-agent_.md)
- [第4章 全书地图：平台参考架构与阅读路径](part01-overview/ch/new_ch04_.md)

## Part II 模型与推理

- [Part II 导读](part02-model-inference/ch/new_index_.md)
- [第5章 大模型选型](part02-model-inference/ch/new_ch05_.md)
- [第6章 本地推理引擎的吞吐、延迟与部署边界](part02-model-inference/ch/new_ch06_.md)
- [第7章 推理优化技术](part02-model-inference/ch/new_ch07_.md)
- [第8章 结构化输出与提示工程](part02-model-inference/ch/new_ch08_.md)
- [第9章 模型能力定制与知识增强](part02-model-inference/ch/new_ch09_.md)

## Part III 数据基础设施

- [Part III 导读](part03-data-infra/ch/new_index_.md)
- [第10章 数据采集与集成](part03-data-infra/ch/new_ch10_.md)
- [第11章 数据湖与湖仓](part03-data-infra/ch/new_ch11_.md)
- [第12章 湖仓引擎与 OLAP](part03-data-infra/ch/new_ch12-olap_.md)
- [第13章 流式计算与实时数据](part03-data-infra/ch/new_ch13_.md)
- [第14章 数据编排与质量](part03-data-infra/ch/new_ch14_.md)
- [第15章 元数据、血缘、契约与指标](part03-data-infra/ch/new_ch15_.md)

## Part IV 向量、检索与知识工程

- [Part IV 导读](part04-vector-knowledge/ch/new_index_.md)
- [第16章 嵌入模型](part04-vector-knowledge/ch/new_ch16_.md)
- [第17章 嵌入微调与重排](part04-vector-knowledge/ch/new_ch17_.md)
- [第18章 向量数据库与索引算法](part04-vector-knowledge/ch/new_ch18_.md)
- [第19章 文档解析与多模态 OCR](part04-vector-knowledge/ch/new_ch19-ocr_.md)
- [第20章 RAG 工程与高级检索](part04-vector-knowledge/ch/new_ch20-rag_.md)
- [第21章 知识工程：本体、抽取与知识图谱](part04-vector-knowledge/ch/new_ch21_.md)

## 本版编辑原则

优化过程中遵循以下原则：保留核心定义、工程判断、重要案例、图片、表格、代码与参考文献；合并过细小节；删除同义反复和低信息量扩写；根据内容密度将章节整体压缩约 30%–50%；并用少量 **加粗结论句** 提升扫读效率。

技术密度较高的章节不会为了追求固定压缩率而硬删内容。模型推理、数据一致性、缓存、实时计算、Schema、契约、权限、故障恢复、检索、RAG 与知识图谱等工程关系会优先保留，重复的“发布门禁—运行台账—复审—证据”尽量合并成一条完整的生产化链路。

**目标不是做摘要，而是在尽量不损失有效信息的前提下，让正文更像人工精修后的专业技术书。**

后续每完成一个 Part 的优化，就会将对应章节加入此在线阅读页。