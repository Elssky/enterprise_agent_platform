# 第19章 文档解析与多模态 OCR

---

很多所谓“RAG 幻觉”其实早在文档解析阶段就埋下了：双栏 PDF 阅读顺序错乱、页眉页脚混入正文、跨页表格丢表头、扫描件漏印章、截图里的指标注释没被识别。向量库和 reranker 只能在已经解析出来的内容里排序，无法找回根本没被提取的证据。

企业知识也不是纯文本集合。制度、合同、票据、PPT、报表、截图和手写材料包含标题层级、表格关系、页码、坐标、图注和签章，这些结构本身就是证据。

**文档解析的目标不是“把文件变成文本”，而是把文件变成可检索、可引用、可复核、可权限控制的知识对象。**

## 19.1 先按文档风险分流：不同材料不应共用同一解析策略

合同、票据、报表、制度和截图对“解析成功”的定义不同。合同关注主体、金额、日期、条款和签章；财务报表关注表头、单位、期间和跨页关系；知识文档关注标题层级、正文顺序和页码；截图则需要视觉语义和 OCR 协同。

*表19-1：企业文档解析的典型失败模式。来源：本书整理。*

| 失败模式 | 表现 | 下游影响 |
|---|---|---|
| 文本顺序错误 | 双栏、页眉页脚、脚注进入正文 | chunk 语义混乱，引用错位 |
| 表格结构丢失 | 合并单元格、表头、跨页表格被打散 | 指标口径和合同金额无法校验 |
| OCR 漏识别 | 印章、手写、低清扫描、截图字体 | 关键证据无法召回 |
| 版面语义丢失 | 标题、章节、图表、批注无层级 | 页码和区域不可复核 |
| 权限和来源缺失 | 无 source、版本、ACL | 越权检索、审计断链 |

![图19-1：企业文档解析流水线](../../images/part4/ch/ch19-01-document-parsing-pipeline.svg)

*图19-1：企业文档解析流水线。来源：本书自绘。Alt text：横向流水线依次为文件接入、格式识别、版面分析/OCR、结构还原（表格/标题/段落）、分块入库，箭头表示原始文档逐步转为带结构的可检索对象。*

![图19-2：企业文档类型矩阵](../../images/part4/ch/ch19-02-document-matrix-atlas.png)

*图19-2：企业文档类型矩阵。来源：本书自绘。Alt text：矩阵以"版式复杂度"和"是否扫描件"为轴，把合同、报表、手册、截图、票据等文档类型落入不同象限，各象限标注推荐的解析方式。*

上传阶段最好就携带文档类型、业务域、敏感等级和用途，据此选择 parser、OCR/VLM、质量门禁和人工复核路径。

**高风险材料宁可先进入 `review_required`，也不能因为“任务执行成功”就自动进入索引。**

## 19.2 解析产物：必须保留页面、区域和结构化对象

一个可用于企业 RAG 的解析结果至少应包含 Document、Page、Block、Table、Figure 和 Chunk。

*表19-2：解析对象的数据结构。来源：本书整理。*

| 对象 | 必要字段 | 用途 |
|---|---|---|
| Document | `source_id`、`source_version`、`acl`、`file_hash` | 版本、权限、审计 |
| Page | `page_no`、`width`、`height`、`rotation` | 页码引用、坐标换算 |
| Block | `block_type`、`bbox`、`reading_order` | chunk、视觉检索、引用高亮 |
| Table | `rows`、`cols`、`header`、`cell_bbox` | DataAgent、合同、票据 |
| Figure | `caption`、`image_ref`、`ocr_text` | 多模态检索、截图问答 |
| Chunk | `chunk_id`、`text`、`source_span`、`metadata` | embedding 和 RAG |

![图19-3：PDF 页面结构解析示意](../../images/part4/ch/ch19-03-pdf-layout-atlas.png)

*图19-3：PDF 页面结构解析示意。来源：本书自绘。Alt text：一页 PDF 被识别为标题、正文段落、表格、图、页眉页脚等区块，每个区块标注边界框与阅读顺序，体现版面分析还原文档结构。*

页码和 bbox 不只是前端高亮信息，而是生产证据。用户质疑合同条款、报表数值或 OCR 金额时，系统必须能回到原文件对应区域。

表格尤其不能简单拍平成文本。金额和指标的含义往往来自表头、行列、单位、期间、合并单元格和脚注；这些结构一旦丢失，后续模型会得到数值却不知道它是什么。

**好的 Chunking 从版面结构开始，而不是从固定字符数开始。**

## 19.3 工具链：PyMuPDF、OCR、Parser 与 VLM 各有边界

*表19-3：文档解析工具链取舍表。来源：本书整理。*

| 方案 | 优势 | 代价 | 适用场景 | mini-platform 选择 |
|---|---|---|---|---|
| PyMuPDF + 规则 | 轻量、可控、坐标清晰 | 复杂版面/OCR 需额外组件 | 可复制文本 PDF、简单合同 | 默认底层适配器 |
| unstructured | 多格式 element 抽取成熟 | 质量依赖文档类型和配置 | 批量知识库导入 | 通用 parser provider |
| LlamaParse | 面向 LLM/RAG、复杂 PDF 体验好 | SaaS 成本、数据出域 | 快速试点、表格较多文档 | 可选 provider |
| PaddleOCR/PP-Structure | 中文 OCR、版面、表格能力强 | 部署和调参成本 | 扫描件、票据、中文表格 | 私有化 OCR 候选 |
| VLM 解析 | 复杂视觉语义、图表理解 | 成本高、可重复性较弱 | 看板截图、巡检、复杂页面 | 高价值场景补充 |

选型应拿企业真实困难样本做评测，而不是看官方演示：倾斜扫描、跨页表格、盖章遮挡、双栏、低清截图、历史模板都要覆盖。

评测也要按业务风险分层。普通知识文档允许少量排版损失；合同和票据中的金额、日期、主体和条款编号不能用普通段落的平均准确率来“稀释”错误。

## 19.4 OCR、版面分析与 VLM：视觉理解不能直接变成事实

OCR 负责文字和位置，版面模型负责区域和阅读顺序，VLM 负责图表、截图和视觉关系理解，结构化校验负责金额、日期、编号和指标等高风险字段。

*表19-4：OCR、版面模型与 VLM 的边界。来源：本书整理。*

| 能力 | 输入 | 输出 | 适合任务 | 风险 |
|---|---|---|---|---|
| OCR | 图片、扫描页、截图 | 文本和位置 | 发票、合同、截图文字 | 低清、旋转、印章、手写 |
| 版面解析 | PDF 页面、截图 | block、table、figure、reading order | chunk、引用、表格 | 复杂版式排序错 |
| VLM | 图片、页面、图表 | 描述、问答、区域解释 | 看板截图、视觉检索 | 成本高、输出不稳定 |
| 结构化校验 | OCR/VLM + 规则 | 字段、置信度、错误标记 | 金额、日期、编号、指标 | 规则维护成本 |

![图19-4：OCR 与 VLM 协作路径](../../images/part4/ch/ch19-04-ocr-vlm-flow-atlas.png)

*图19-4：OCR 与 VLM 协作路径。来源：本书自绘。Alt text：流程显示常规文本走 OCR 快速识别，复杂版面或图文混排转交 VLM 理解，结果合并后统一输出，箭头标出按难度分流到两条解析路径。*

VLM 输出最好作为 `visual_observation`，保留图像区域、模型版本和 Prompt；金额、日期、合同编号和指标值仍要回到 OCR、坐标、规则或人工确认。

**模型“看懂了一页”不等于这一页已经形成可审计字段。视觉解释与事实抽取必须分层。**

## 19.5 质量门禁：解析成功、可检索、可用于高风险回答是三个状态

```json
{
  "source_id": "contract-2026-001",
  "parser": "pymupdf+paddleocr",
  "parser_version": "2026-06-baseline",
  "pages": 18,
  "quality": {
    "ocr_confidence_avg": 0.93,
    "table_parse_pass_rate": 0.86,
    "low_confidence_blocks": 7,
    "requires_review": true
  }
}
```

*表19-5：解析质量门禁。来源：本书整理。*

| 门禁 | 指标 | 处理策略 |
|---|---|---|
| 文本完整率 | 文本 + OCR 覆盖 | 低于阈值人工复核 |
| 表格结构 | 表头、行列、跨页连接 | 失败不进 DataAgent 字段索引 |
| 坐标可追溯 | chunk 可映射页码/bbox | 不可追溯禁止高风险引用 |
| 权限完整性 | source、ACL、版本齐全 | 缺失不写向量库 |
| 低置信区域 | OCR/VLM/规则失败 | 标红并进入复核队列 |

![图19-5：文档解析质量报告](../../images/part4/ch/ch19-05-parsing-quality-report-atlas.png)

*图19-5：文档解析质量报告。来源：本书自绘。Alt text：报告页展示字符识别率、表格还原准确率、版面顺序正确率等指标，并列出失败样本缩略图，体现解析质量可量化、可抽检。*

状态可以显式区分：`parsed`、`review_required`、`approved_for_search`、`approved_for_high_risk_answer`、`rejected`。低置信文档可以允许人工搜索，但不能自动支撑正式财务、法务或合规结论。

人工复核也要聚焦高价值对象，而不是逐字校对：表格含义、合同责任、金额日期、指标口径、低置信区域最值得业务专家确认。

## 19.6 版本、回放与事故复盘：Parser 也是生产版本

OCR 模型、版面模型、后处理、VLM Prompt 和 Chunk 策略变化，会让同一文件生成不同的文本、表格和 citation span。因此解析产物必须版本化，不能直接覆盖。

发布前回放应覆盖：跨页表格、双栏、盖章合同、低清截图、附件、历史模板，以及近期真实失败样本。比较的不只是 OCR 分数，还包括文本顺序、表格结构、页码坐标、字段值和最终引用。

一次解析事故至少应保留：

`file_hash + parser_version + parse_run_id + page/bbox + chunk_id + index_version + answer_trace + manual_correction`

这样用户指出“引用错页”时，才能判断问题来自 parser、chunk、index 还是生成。

用户修正、审批退回和低置信复核都应沉淀进解析样本库。某类扫描件长期失败时，还应反向修改上传规范，而不是无限要求 OCR 模型兜底。

**解析质量治理的目标，是让重复错误逐渐在知识入口被消灭，而不是在 RAG 末端不断用 Prompt 补丁掩盖。**

## 本章小结

文档解析是知识证据链的入口。企业不能把复杂 PDF、表格、截图和扫描件压成一段纯文本，再期待下游模型恢复丢失结构。

生产解析应保留页面、bbox、标题、表格、图像、权限和版本；OCR、版面分析、VLM 与结构化校验各有边界；解析结果要经过质量门禁和人工复核，才能决定是否进入普通检索或高风险回答。

**一段知识是否“可被模型读到”不重要，重要的是它能否回到原文、说明解析过程，并在有争议时被重新验证。**

## 参考文献

- unstructured partitioning: https://docs.unstructured.io/open-source/core-functionality/partitioning
- LlamaParse documentation: https://docs.llamaindex.ai/en/stable/llama_cloud/llama_parse/
- PyMuPDF documentation: https://pymupdf.readthedocs.io/
- PaddleOCR documentation: https://paddlepaddle.github.io/PaddleOCR/
- ColPali paper: https://arxiv.org/abs/2407.01449
