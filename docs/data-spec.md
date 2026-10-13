# 数据规范 v0.2

所有文件使用 UTF-8，机器字段使用 snake_case，时间为带时区的 ISO 8601。JSONL 每行一条记录。当前 corpus 为小规模种子数据，不是完整设备知识库。

## 物理隔离与来源

- `data/sources/manifest.json`：外部 PDF 的固定版本、项目已核验的型号范围 `models`、官方链接、文件大小、SHA-256、页数和授权状态。
- `data/raw/`：本地原文，Git 忽略；不得将忽略取消以便“直接推送全部数据”。
- `data/corpus/knowledge.jsonl`：项目编写的简短事实注释或合成干扰规则；带原始 PDF 页码的注释不是逐字原文，也不是厂商发布的独立文件。
- `data/corpus/work_orders.jsonl`：虚构历史维修事件。
- `data/corpus/alarms.jsonl`：与历史工单关联的虚构告警事件。
- `data/evaluation/`：输入、根因和证据标注。任何索引过程都必须显式排除此目录。
- `data/graph/reference.json`：用于校验抽取的手工实体和关系；不得直接当作 LLM 抽取成果。
- `docs/reviews/`：人工审核材料，含评测答案与审核意见，禁止作为检索语料。

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
