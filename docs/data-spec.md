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

数据校验命令也检查上述文档元数据。现有 corpus 的证据 ID 和来源定位器保持原格式；文档主键不是 Chunk 证据 ID，后者及数据库幂等导入分别属于 M1-11、M1-18。

## 故障码原值与规范化值（M1-09）

`app/schemas/fault_code.py` 的 `FaultCode.from_raw()` 接受当前 ABB ACS580 故障表所用的四位 ASCII 十六进制字符串。`raw_code` 原样保留输入（包括大小写与空白）；`normalized_code` 只去首尾空白并将 ASCII 字母转为大写。例如自造测试值 `" 00a1 "` 对应规范化值 `"00A1"`。不转成整数，不删除前导零，也不补零猜测丢失字符。

非字符串、内部空白/断行、长度错误、非十六进制字符、`0x` 前缀、参数号、全角字符和 Unicode 相似字符均拒绝。首尾空白之外不拼接字符。全半角与查询侧精确匹配属于 M2-03；断行修复及解析质量检测属于 M1-13。

解析命令在顶层新增 `fault_codes` 列表，每项包含 `raw_code`、`normalized_code`、`cell_ref`。识别器只处理同时具有“编码（hex）”和右侧相邻“故障/辅助代码”表头的编码列，两表头必须位于同一行；兼容表头空白、ASCII 括号及 HEX 大小写。不会扫描正文、辅助码列或未带表头的续表，普通数字表也不参与识别。编码列中的未匹配单元格保留在原始 `document`，不修复、不删除；空列表只表示未识别到符合这些条件的主故障码，不表示该页没有故障信息。

`cell_ref` 是相对于本次结果 `document` 的 JSON 引用，例如 `#/tables/0/data/table_cells/2`，可回到原始单元格及其所属表格的 provenance。它不是永久证据 ID，重新解析后可能变化；稳定证据 ID 仍属 M1-11。重复出现的码值保留各自引用，不按规范化值合并。

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

## 后续 PDF 解析与切分

保留 `source_id + sha256 + pdf_page + paragraph/table-row locator` 作为原始证据锚点。chunk 是可重建派生物，不能只用数组下标作为永久标注 ID。

初始建议按章节、故障表完整行切分，避免分开“原因/措施”两列。重叠片段在评测前归并到原始证据锚点；表格、跨页与扫描页需要抽样人工检查。真实 PDF 解析结果保存到忽略的 `data/processed/`，不凭空生成原文。

手册、工单、告警均通过稳定证据 ID 关联。未来从官方原文抽取的图谱可以引用这些锚点；当前只提供少量注释与参考图，不宣称完成全量入库。

## 授权和发布

官方文件公开下载不等于允许全文再分发。当前外部来源标记 `redistribution=not_verified`，只公开链接、指纹和简短项目注释，不提交 PDF 或大段提取文本。原创代码/合成数据的项目许可证尚待选择，不把它们自动套用为 ABB 的授权。

所有来源清单保留访问日期与核验方式。第三方数据集只是候选来源，尚未导入的不能写成已使用。
