# 数据规范 v0.2

所有文件使用 UTF-8，机器字段使用 snake_case，时间为带时区的 ISO 8601。JSONL 每行一条记录。当前 corpus 为小规模种子数据，不是完整设备知识库。

## 物理隔离与来源

- `data/sources/manifest.json`：外部 PDF 的固定版本、项目已核验的型号范围 `models`、官方链接、文件大小、SHA-256、页数和授权状态。
- `data/raw/`：本地原文，Git 忽略；不得将忽略取消以便“直接推送全部数据”。
- `data/corpus/knowledge.jsonl`：项目编写的简短事实注释或合成干扰规则；带原始 PDF 页码的注释不是逐字原文，也不是厂商发布的独立文件。
- `data/corpus/work_orders.jsonl`：虚构历史维修事件。
- `data/corpus/alarms.jsonl`：与历史工单关联的虚构告警事件。
- `data/evaluation/`：输入、根因和证据标注。任何索引过程都必须显式排除此目录。唯一允许的语料入口是 `scripts/corpus_allowlist.py` 的显式 allowlist（`indexable_files()` / `assert_indexable()`）：构建器不得用目录递归（如 `rglob("*.jsonl")`）生成索引，路径必须逐个通过 allowlist 校验。该边界由 `tests/test_corpus_isolation.py` 守护。
- `data/graph/reference.json`：用于校验抽取的手工实体和关系；不得直接当作 LLM 抽取成果。
- `docs/reviews/`：人工审核材料，含评测答案与审核意见，禁止作为检索语料。

## 文档身份（M1-08）

`app/schemas/document.py` 从来源清单生成 `DocumentKey`，只依赖标准库。`source_id` 沿用清单的 `id`；文档主键 `document_key` 为 `source_id@revision:sha256`，使用完整 64 位小写 SHA-256，不截断摘要、不依赖来源列表顺序或解析页范围。例如固件手册的主键为：

```text
ABB-FW-H-ZH@H:e6ed9eab8c6a06afc0411a7ab11ace174e56385f9c554a221c3309571e4eb2b6
```

`source_id` 或修订变化、原文件字节导致 SHA-256 变化时，主键随之变化；重新下载同一文件或重新解析不同页面不改变主键。标题、下载链接和访问日期不参与主键计算。文档编号是业务元数据，不能单独区分修订或文件版本。

PDF 解析结果的 `source` 保留以下字段：

| 字段 | 来源与约束 |
| --- | --- |
| `document_key` | 按上述规则派生；`parse_key()` 可恢复来源 ID、修订和完整摘要，但不能代替来源清单校验或文件指纹核验。 |
| `source_id` | 清单 `id`；与 `revision` 均以英文字母或数字开头，其余只接受英文字母、数字、点、下划线、连字符，不能含主键分隔符。 |
| `document_code` | 非空且不含空白的厂商文档编号，原样保留。 |
| `revision` | 文档修订；不是固件版本。 |
| `firmware_scope` | 必须显式存在；`null` 表示明确不按固件限定，不能把缺失字段自动解释为不限固件；非空格式沿用 `ASCKX <数字>.<数字>`。 |
| `sha256` | 原文件完整的 64 位小写十六进制摘要，解析前必须与本地 PDF 匹配。 |
| `source_url` | 清单 `url`，保留 HTTP(S) 下载来源。 |
| `accessed_at` | 清单访问日期，严格使用 `YYYY-MM-DD`，不是诊断时间或生效日期。 |

`document_keys()` 拒绝重复主键、同一 `(source_id, revision)` 声明不同摘要，以及多个来源声明相同文件摘要；这些是来源清单冲突，不是数据库导入行为。不同修订、不同文件摘要可生成不同主键。现有种子校验与解析 CLI 仍要求清单 `id` 唯一，因此登记新版手册时使用独立来源 ID；不会静默覆盖同名来源。

数据校验命令也检查上述文档元数据。现有 corpus 的证据 ID 和来源定位器保持原格式；文档主键不是 Chunk 证据 ID，后者见下文 M1-11 规则，数据库幂等导入仍属于 M1-18。

## 故障码原值与规范化值（M1-09）

`app/schemas/fault_code.py` 的 `FaultCode.from_raw()` 接受当前 ABB ACS580 故障表所用的四位 ASCII 十六进制字符串。`raw_code` 原样保留输入（包括大小写与空白）；`normalized_code` 只去首尾空白并将 ASCII 字母转为大写。例如自造测试值 `" 00a1 "` 对应规范化值 `"00A1"`。不转成整数，不删除前导零，也不补零猜测丢失字符。

非字符串、内部空白/断行、长度错误、非十六进制字符、`0x` 前缀、参数号、全角字符和 Unicode 相似字符均拒绝。首尾空白之外不拼接字符。全半角与查询侧精确匹配属于 M2-03；M1-13 回归检查断行码保留原文且不被识别或错误归属，不做自动断行修复。

解析命令在顶层新增 `fault_codes` 列表，每项包含 `raw_code`、`normalized_code`、`cell_ref`。识别器只处理同时具有“编码（hex）”和右侧相邻“故障/辅助代码”表头的编码列，两表头必须位于同一行；兼容表头空白、ASCII 括号及 HEX 大小写。不会扫描正文、辅助码列或未带表头的续表，普通数字表也不参与识别。编码列中的未匹配单元格保留在原始 `document`，不修复、不删除；空列表只表示未识别到符合这些条件的主故障码，不表示该页没有故障信息。

`cell_ref` 是相对于本次结果 `document` 的 JSON 引用，例如 `#/tables/0/data/table_cells/2`，可回到原始单元格及其所属表格的 provenance。它不是永久证据 ID，重新解析后可能变化；M1-11 在 Chunk 上另行生成物理定位 ID。重复出现的码值保留各自引用，不按规范化值合并。

四位格式匹配不证明该码真实存在，不赋予辅助码主故障码身份，也不证明适用型号或固件。使用时仍须结合父文档 `source` 和来源清单中的型号/固件范围；`normalized_code` 不能单独作为跨型号实体主键。现有 corpus 的 `alarm_code` 原值与评测输入不改写，本项不建立全量厂商故障码字典。

## 检索证据字段

三类 corpus 记录共用：`id`、`kind`、`text`、`model`、`synthetic`、`available_at`、`locator`。`id` 同时是初始化阶段的稳定证据 ID，不随检索排序变化。

`locator`：

- 官方知识注释：`source_id`、`pdf_page`（从 1 开始的整数，不接受布尔值或浮点数）、`printed_page`、`section`（后两项为非空白字符串）。指向原 PDF 的依据，不声称注释文字与原文逐字相同。
- 合成知识：`file`、`record_id`，定位本仓库记录，不伪造 PDF 页码。
- 工单/告警：`file`、`record_id`，`record_id` 必须等于记录 ID。

`model` 精确表达适用型号。`SIM-OTHER-DRIVE` 是虚构干扰型号，不能映射为真实 ABB 产品。

来源清单的 `models` 是非空、无重复的型号列表，表示项目当前核验并采用的范围，不宣称穷尽厂商兼容型号。非合成知识注释的 `model` 必须属于对应来源的 `models`；评测题只有该范围内的型号可以标为 `supported` 或 `insufficient`，范围外型号标为 `out_of_scope`。缺失或空白型号属于无效数据，不等同于已知范围外型号。

`available_at` 是诊断系统最早能使用该证据的时间：知识资料按出版/生效日期，闭环工单按关闭时间，告警按发生时间。数据编写日期另在数据卡记录。合成事件的历史时间仅为实验时间线。

知识附加字段：`document_revision`、`firmware_scope`。文档修订 H 不是固件 H；本次已核验 H 对应 ASCKX 2.16，硬件知识的固件范围为 `null`（不按固件限定）。未知固件与不适用固件均不能自动视为匹配。当前种子不支持判断真实固件间的差异。

当前种子校验接受的非空固件字段格式为 `ASCKX <数字>.<数字>`，如 `ASCKX 2.16`；这是字段格式约束，不表示其他版本已获兼容性验证。未知固件只使用 JSON `null`，不使用 `unknown`、空字符串、数字或文档修订号。`document_revision` 与 `firmware_scope` 分别对照来源清单校验，不互相替代。

固件适用性按证据逐条判断：

| 证据与诊断输入 | 结果 | 评测 gold 处理 |
| --- | --- | --- |
| 知识注释的 `firmware_scope=null` | `applicable`：明确不按固件限定 | 在型号、时间等其他条件有效时可用 |
| 有固件限定，双方版本已知且完全一致 | `applicable` | 可用 |
| 有固件限定，双方版本已知但不同 | `inapplicable` | 所有状态均拒绝，不把 `insufficient` 当作绕过条件 |
| 诊断输入或历史工单/告警的固件版本为 `null` | `unknown`（不限固件的知识注释除外） | 仅允许在 `insufficient` 中作为解释限制的上下文，不得支持 `supported` |

例如 Q012 可引用 K008 解释为何需要确认版本，不能因此认定手册适用于当前设备。历史工单/告警的 `firmware_version=null` 表示未知，绝不表示“不限固件”。`required_checks` 是否准确指出缺失信息仍需人工语义复核。

校验器检查定位字段的结构、页码范围和已核验页列表，不自动证明章节或注释语义与原文相符。逐条原文定位及语义核对见 [种子人工复核清单](reviews/seed-v0.2-human-review.md)。

工单附加字段：`asset_id`、`incident_group`、`firmware_version`、`opened_at`、`closed_at`、`alarm_code`、`observations`、`confirmed_cause`、`action`、`outcome`。`confirmed_cause` 仅指合成历史事件中的设定，不是当前诊断的标签。

告警附加字段：`asset_id`、`incident_group`、`firmware_version`、`occurred_at`、`work_order_id`、`alarm_code`。关联工单、设备和型号必须一致，时间落在工单事件窗口内。

## 评测字段

`id`、`split`（`dev` / `demo`）、`incident_group`、`synthetic`、`model`、`firmware_version`（可空）、`as_of`、`query`、`observations`、`alarm_codes`、`expected_status`、`acceptable_cause_ids`、`gold_evidence_ids`、`required_checks`、`rationale`、`review_status`。

- `supported`：在教学场景的已知观察下，可支持一个最优候选；不是现场工程确诊。
- `insufficient`：不能唯一判定原因。`acceptable_cause_ids` 为空，必须有 `required_checks`；可以有用于解释候选原因的 gold evidence。
- `out_of_scope`：型号不在当前业务范围，不应给出本系统的确定诊断。
- `review_status=agent_checked_pending_human`：由初始化工具/AI 进行一致性检查，待人类复核；不得改写成“专家标注”。

同一 incident_group 不跨 split。开发集与演示集都不是盲测集；正式测试集后续独立建立。相同故障类型可以出现在不同事件组，但不能仅改写同一事件后拆分。

## 章节与故障表行组切块（M1-10）

`app/ingestion/chunking.py` 的 `chunk_document(document, document_key)` 只依赖标准库，按 Docling `body` 阅读树遍历文本、嵌套分组和表格，输出可重建的 `chunks` 列表；不扫描语料目录、不写检索索引。现有 `document` 原样保留，切块不替代原始结构或来源验证。

通用字段：`chunk_type`、父文档 `document_key`、按解析层级排列的标题文本列表 `section`、对应标题引用 `heading_refs`、内容引用 `source_refs` 和拼接文本 `text`。引用均相对于同一结果的 `document`，不是永久证据 ID。

| `chunk_type` | 切分与上下文规则 |
| --- | --- |
| `section` | 同一标题上下文中的连续正文与列表保持一块；按 `section_header.level` 维护标题层级，表格与新标题会结束当前正文块。保留列表标记，页眉/页脚不生成块、不打断连续正文。 |
| `fault_rows` | 已由 M1-09 识别的故障表中，从主码列非空行到下一个主码列非空行构成一组，辅助码行随所属组保留；块内包含原始/规范化故障码。 |
| `table_rows` | 已识别故障表中的未分类行组，包括第一个主码之前的内容或非空但格式不合法的主码行；`fault_codes=[]`，不继承上一组主码。 |
| `table` | 没有识别出主码的表格整体保留，不猜测普通表或无表头续表的故障语义。 |

表格块额外包含 `table_ref`、`row_range`（Docling 的零基行号，左闭右开）和 `fault_codes`。每组重复表头，并收集所有与其行范围相交的完整单元格；共享措施或原因每块保留一次，不把一个单元格截断。表格 `text` 用换行/制表符拼接原始单元格；行列跨度仍以 `source_refs` 指向的原单元格为准，不能把拼接文本当成完整表格结构。不同表不会自动合并；原表的多页 provenance 保留在 `document`，本项不推断跨表续行或印刷页码。

短标题“警告”“注意”“危险”（可带 `!`、`！`、`:`、`：`）保留为所在章节正文，不据此拆开警告、条件与后续列表；图片引用也随正文保留，但不会生成图像内容描述。这只是对当前解析形态的上下文保留，不等于 M1-16 的安全标签识别。没有正文的独立标题/纯图片不生成文本块，原项仍保留在 `document`。

当前按语义结构切分，不设置固定 Token 窗口，也不截短超长段落/表格。块的排序位置、逻辑行号和解析引用均不能作为稳定 ID；M1-11 使用下述物理定位生成 ID，M1-12 附加展示定位元数据，解析修复与业务入库仍在后续任务实现。

## Chunk 稳定证据 ID（M1-11）

`app/ingestion/evidence.py` 的 `identify_chunk(document, chunk)` 返回带 `evidence_id` 和 `evidence_locator` 的副本，不修改原文或输入块。解析 CLI 为每个块调用它；只使用标准库，不读取评测标签或参考图。现有人工编写的 corpus 记录 ID 不迁移到此格式。

`evidence_locator` 包含 `version=1`、父文档的 `source_id`、完整原文件 `sha256` 和非空 `elements`。每个元素指向一处物理位置：

| 字段 | 规范 |
| --- | --- |
| `kind` | `text`、`picture` 或 `table_cell`。 |
| `pdf_page` | 从 1 开始的原 PDF 物理页号，不是选定页范围内的序号。 |
| `bbox_milli` | `[left, top, right, bottom]`，统一为页面左上角原点；Docling 页面坐标乘 1000 后按 `ROUND_HALF_UP` 取整，精度为 0.001 页面坐标单位。`BOTTOMLEFT` 使用原页面高度换算，不按图片像素缩放。 |
| `charspan` | 仅文本携带原 provenance 的 `[start, end]` 字符范围；图片和表格单元格不伪造字符范围。 |

文本、图片保留全部 provenance，可覆盖多页。表格单元格用自身边界框及所属表的唯一物理页定位，不使用表序号、单元格序号或逻辑行列号。Docling 单元格没有独立页号，因此父表跨多页时不能唯一确定单元格页号，当前明确拒绝生成 ID；不把第一个表页号冒充单元格页号，也不合并跨表续行。

规范化步骤固定为：将每个元素按键排序、无额外空白的 JSON 序列化（`ensure_ascii=False`），按该字符串去重并排序组成 `elements`；整个定位器再按相同规则序列化并编码为 UTF-8，计算完整 SHA-256。`evidence_id` 为 `ev1:<64 位小写十六进制摘要>`，摘要不截断。版本号同时出现在定位器和 ID 前缀中；改变定位或序列化规则时应另立版本。

解析内部引用仅用于解析到物理位置，不进入摘要。相同来源、原文件和规范化物理覆盖范围下，块/引用重排、引用重编号、重复引用、检索排序、显示文本或继承标题变化均不改变 ID；相同字句位于不同页面或位置时不会合并。只有修订标签变化而来源 ID 和文件字节不变时，证据 ID 保持不变，父 `document_key` 仍按 M1-08 规则变化。

来源 ID、PDF 指纹、页号、规范化边界框、字符范围或覆盖元素集合变化会改变 ID。该规则不保证解析器升级、布局漂移或重新切分后的 ID 不变；坐标只有舍入到相同值时才视为相同位置。相邻/重叠但覆盖集合不同的块不会自动归并，后续去重不能仅依赖 ID 判断语义重复。

缺失 provenance、无法解析的引用、非法页号、非有限/越界/退化坐标、缺失单元格边界框或有歧义的表格页号都会失败，CLI 在写文件前停止，不回退为数组下标或内容哈希。继承的 `heading_refs` 仅提供显示上下文，不属于块的物理覆盖集合；警告正文与图片若在 `source_refs` 中，则参与定位。印刷页码与展示定位元数据见下文 M1-12。

## 页码、章节和表行元数据（M1-12）

`app/ingestion/metadata.py` 的 `locate_chunk(chunk, source)` 在已生成 ID 的块上附加展示定位，不修改 `evidence_id` 或 `evidence_locator`。字段契约如下：

| 字段 | 约定 |
| --- | --- |
| `locations` | 按物理页升序排列的非空列表，覆盖 `evidence_locator.elements` 中的全部唯一页。每项包含整数 `pdf_page` 和字符串或 `null` 的 `printed_page`；跨页块不压缩为第一页，也不补出未覆盖的中间页。 |
| `section` | 沿用切块时的标题层级列表，无可用标题时为 `[]`；不从相邻页猜测缺失章节。 |
| `table_row` | 表格块为 `{"table_ref": "#/tables/0", "row_range": [1, 10]}` 形式；非表格块为 `null`。行范围沿用 Docling 零基、左闭右开约定，只在指定表内有效，不能当成跨解析稳定锚点。 |
| `document_key` | 完整父文档主键，与顶层 `source.document_key` 相同；同时校验物理定位器的来源 ID 和摘要一致，防止混用其他文档的页码映射。 |

`table_row` 表示切块的逻辑行组；重复表头和跨组的合并单元格可能超出该行组范围，完整单元格仍通过原有 `source_refs` 与物理定位器回读，不将其截断。段落也通过 `source_refs` 和元素中的页号、边界框、字符范围定位。支持跨页正文及文本元素的多页 provenance；无法唯一定位单元格页号的跨页表格仍按 M1-11 拒绝，不推断跨表续行。

来源清单 schema 0.3 增加可选 `printed_page_map`：包含与该来源一致的完整 `sha256`、已有核验记录的 `verification_ref`，以及 `pages` 对象（键为规范的正整数物理页字符串，值为非空、无空白的印刷页标签）。标签原样保留，例如 `vii`、`A-1`、`007`，不转换成数字。映射页必须在来源总页数内且已列入 `verified_pdf_pages`；非法字段或摘要不匹配会在推理前失败，种子校验器也执行相同校验。

当前只转录 [既有页面核验记录](../data/sources/verification-2026-10-13.md) 明确支持的 7 页：固件 13、536、537、538、542，硬件 25、152。未登记页、未印页号或没有映射的旧来源统一输出 `printed_page=null`；不能将其解读为“该页一定没有印刷页号”，也不使用物理页号、页差或页眉数字补齐。映射是项目核验元数据，不是厂商另行提供的页码数据库或人工领域复核结果。

解析结果的 `source.printed_page_map` 原样保留本次采用的映射及核验记录引用，便于回查；原来源无此字段时不补写。映射校验验证结构和指纹绑定，不自动证明印刷标签内容正确。修改已核验的显示标签不改变物理证据 ID；变更 PDF 时必须重新核验映射。该步骤不读取 corpus 注释、评测标签或参考图。

## 后续证据锚点与切分质量

M1-13 的 `app/ingestion/quality.py` 在解析 CLI 切块前检查显式文本损坏及表格逻辑结构。文本项和表格单元格出现 `U+FFFD`，或 `U+0000–0008`、`U+000B–000C`、`U+000E–001F`、`U+007F–009F` 控制字符时失败；制表符、回车、换行及正常中文/符号保留。表格行列总数必须为非负整数，每个单元格的零基左闭右开范围必须非空且位于表内；显式 `row_span` / `col_span` 须与范围一致，逻辑格不能重叠，避免拼接时静默覆盖。未占用的空白格、合法合并单元格和空表允许存在。失败信息指出解析内引用，CLI 不写部分结果。

空页保留原物理页但不生成虚构内容块；它与“请求页根本未返回”不同，后者仍失败。空页测试不能判定页面是否本应含文字，OCR 关闭时也不能证明扫描页完整。跨页单元格页号有歧义时仍拒绝生成证据 ID；断行故障码保留在原表和未分类行组中，不拼接成主码，不继承前一主码。

上述检查不读取评测标签、不改写源文档，不检测所有编码错误，也不证明单元格的中文语义与其逻辑行号相符；没有替换字符的乱码、逻辑结构合法但内容错行等情况仍需对照原页及人工抽样复核。通过检查不等于全量解析质量验收。

保留 `source_id + sha256 + pdf_page + paragraph/table-row locator` 作为原始证据锚点。chunk 是可重建派生物，不能只用数组下标作为永久标注 ID。

M1-10 已按章节、故障表完整行组切分，避免分开“原因/措施”两列。重叠片段在评测前仍需归并到原始证据锚点；表格、跨页与扫描页需要抽样人工检查。真实 PDF 解析与切块结果保存到忽略的 `data/processed/`，不凭空生成原文。

手册、工单、告警均通过稳定证据 ID 关联。未来从官方原文抽取的图谱可以引用这些锚点；当前只提供少量注释与参考图，不宣称完成全量入库。

## 授权和发布

官方文件公开下载不等于允许全文再分发。当前外部来源标记 `redistribution=not_verified`，只公开链接、指纹和简短项目注释，不提交 PDF 或大段提取文本。原创代码/合成数据的项目许可证尚待选择，不把它们自动套用为 ABB 的授权。

所有来源清单保留访问日期与核验方式。第三方数据集只是候选来源，尚未导入的不能写成已使用。
