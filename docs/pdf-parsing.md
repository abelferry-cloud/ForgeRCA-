# PDF 结构化解析、证据定位与质量检查（M1-07～13）

当前提供已登记 ABB 手册的物理页范围解析、章节/故障表行组切块、稳定证据 ID 及页码/表行定位元数据。使用 Docling 2.142.0，保留原生文档树、标题/正文标签、表格单元格与页码来源；尚无业务入库或检索。适用对象是带原生文字层的 PDF；OCR 关闭，扫描页不在本次验收范围。

## 准备与运行

在仓库根目录执行：

```bash
uv sync --frozen

# 原文已存在时只复核指纹，不会覆盖
python scripts/download_sources.py
python scripts/validate_data.py --check-raw

# 首次联网下载约 385 MB 的布局/表格模型，此后逐个验指纹并复用
uv run --frozen python -m scripts.download_parser_models

# START / END 均为从 1 开始、包含端点的物理 PDF 页码
uv run --frozen python -m scripts.parse_pdf --source ABB-FW-H-ZH --pages 536 538 --output data/processed/firmware-536-538.json
uv run --frozen python -m scripts.parse_pdf --source ABB-HW-D-ZH --pages 152 152 --output data/processed/hardware-152.json
```

输入只接受 `data/sources/manifest.json` 中的来源 ID；解析前复核大小、PDF 文件头和 SHA-256。必须显式指定页范围，不能用印刷页码猜测物理页码。输出限于 `data/processed/` 下的新 `.json` 文件，已有文件不会覆盖；再次运行时选择新文件名。

模型位于忽略的 `artifacts/docling-models/`，首次下载依赖 Hugging Face。下载器只取 `versions.lock.json` 中列出的五个文件，固定仓库 revision 并核对 SHA-256；已有缓存损坏时重新下载。解析入口在加载模型前再验指纹，缺失或不匹配就失败，不自动改成浮动版本。

所有推理在本机 CPU 上进行，固定 4 线程、OCR 关闭、表格结构识别开启、TableFormer accurate 模式。禁用远程模型服务和外部插件。Windows/Linux 的 PyTorch 使用官方 CPU index，避免 Linux 默认 CUDA 包；完整传递依赖在 `uv.lock`。不根据设备是否有 GPU 自动切换计算后端。

## 输出与读取

每份结果包含：

- `source`：文档主键 `document_key`、`source_id`、文档编号 `document_code`、修订 `revision`、固件适用性 `firmware_scope`、完整 `sha256`、下载来源 `source_url` 和访问日期 `accessed_at`；来源登记了印刷页映射时，另保留 `printed_page_map` 快照。字段规则见 [文档身份](data-spec.md#文档身份m1-08) 和 [定位元数据](data-spec.md#页码章节和表行元数据m1-12)。
- `parser`：实际 Docling / docling-core / docling-parse 版本、页范围、选用参数及模型 revision/文件指纹。
- `document`：原生 `DoclingDocument` JSON，不将文本与表格转成一个丢失结构的字符串。
- `fault_codes`：明确故障表编码列中的主故障码；每项保留 `raw_code`、`normalized_code` 和相对于 `document` 的 `cell_ref`。原始单元格不改写；具体识别边界见 [故障码规范](data-spec.md#故障码原值与规范化值m1-09)。
- `chunks`：按阅读顺序输出的章节/表格块，保留标题上下文、父文档主键和解析内引用，并携带 `evidence_id` 与可检查的 `evidence_locator`；故障表的原因、措施及附属辅助码行保持在同一行组。字段与限制见 [切块规范](data-spec.md#章节与故障表行组切块m1-10) 和 [证据 ID 规则](data-spec.md#chunk-稳定证据-idm1-11)。

M1-08 为 `source` 增加元数据，保留原有 `source_id` / `sha256`；外层 `schema_version=1` 和 Docling 文档结构不变。旧的本地解析文件不会自动改写；需要文档主键时，用新文件名重新运行上述命令。主键仅随来源 ID、修订或文件摘要变化，同一 PDF 选择不同页范围仍属于同一文档。来源元数据缺失或冲突会在模型推理前失败。

M1-09 增加 `fault_codes` 列表，外层仍为 `schema_version=1`；旧文件缺少此字段不等于检测结果为空，需要该字段时重新运行解析命令并指定新文件名。它只识别当前已验证的故障表格式：正文和辅助码列不扫描，无表头续表不猜测。空列表不能用于断言该页没有故障码。

M1-10 增加 `chunks` 列表，外层仍为 `schema_version=1`。旧文件缺少此字段不表示没有可切分内容；需要完整新输出时使用新文件名重新运行上述命令。切块属于解析后的本地派生步骤，不会开放 `data/processed/` 的检索 allowlist，也不改变 `just ingest` 的未实现状态。

M1-11 为每个块增加 `ev1:` 前缀的证据 ID 和版本化物理定位器，外层仍为 `schema_version=1`。旧文件不自动补写，使用新文件名重跑可获得这些字段。相同来源、PDF 指纹和规范化物理覆盖范围的 ID 不随解析引用编号或块排序变化；来源文件或物理覆盖变化会得到新 ID。缺少定位信息或单元格所属页有歧义时整个命令失败，不写不完整结果。当前多页表格的单元格定位尚不支持；跨页文本保留全部物理锚点。

M1-12 在块上增加 `locations` 和 `table_row`，保留原有 `section` 与完整父文档 `document_key`。`locations` 逐页列出全部物理页和对应印刷页标签，未知标签为 `null`；表格保存表引用及原零基左闭右开行组范围，正文的 `table_row=null`。印刷页只读来源清单中绑定 PDF 摘要的已核验映射，不猜测页号或偏移；错误映射在推理前失败。映射快照保存在输出 `source.printed_page_map`，不进入稳定 ID 计算。外层仍为 `schema_version=1`，旧输出需用新文件名重新解析才能得到新增字段。

M1-13 在 Docling 返回结果后、故障码提取和切块之前运行显式文本/逻辑表格质量检查，不新增输出字段。坏字符、越界或重叠的单元格会停止 CLI，不生成结果文件；校验通过的原文和 ID 规则不变。空页允许存在，缺页继续失败；不会自动修复断行故障码或跨页单元格。检查范围见 [质量约束](data-spec.md#后续证据锚点与切分质量)。

文档中的 `body` 树保存交错阅读顺序，`texts` / `tables` 是按类型存储的集合，不能通过拼接这两个数组恢复阅读顺序。按 [Docling 文档模型](https://docling-project.github.io/docling/concepts/docling_document/) 遍历：

```python
import json
from pathlib import Path
from docling_core.types.doc import DoclingDocument

result = json.loads(Path("data/processed/firmware-536-538.json").read_text(encoding="utf-8"))
document = DoclingDocument.model_validate(result["document"])
for item, level in document.iterate_items():
    pages = [prov.page_no for prov in item.prov]
    print(item.label, pages, item.self_ref)
```

标题与段落分别保留上游的 `section_header` / `text` 等标签，列表、图片和页眉页脚也保留在原生结构中。`prov` 保留物理页号、边界框和字符范围；表格 `data.table_cells` 保留行列偏移、跨度和表头标记。多页元素保留完整 provenance 列表，不只取第一个页号。页内先后通过树中的顺序表达，`self_ref` 是本次解析的内部引用，不能当作永久证据 ID。

只有完整成功、返回全部请求页面、通过显式质量检查且所有块均能生成证据 ID 时才写输出；部分成功、缺页、源文件指纹错误、坏字符、无效表格结构和无效物理定位均失败，不发布为成功结果。解析成功仍不等于语义准确；表格重构、跨页内容和分类错误需要后续质量复核。

## 验收范围

`tests/test_pdf_parsing.py` 使用项目自造的 Docling 文档和临时输入，覆盖标题/段落/表格交错、跨页 provenance、合并单元格、前导零保留、部分失败/缺页、模型指纹、损坏缓存恢复、来源指纹和输出路径边界。`tests/test_pdf_quality.py` 补充标准库质量回归。测试不下载模型，不读取厂商 PDF，也不读取评测标签。

```bash
uv run --frozen python -m unittest discover -s tests -p 'test_pdf*.py' -v
```

`.github/workflows/pdf-parser.yml` 在 Linux / Python 3.11 安装锁定的 CPU 依赖，运行上述离线契约及质量测试；[首次 CI 运行](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/39929017180) 的 11 项测试全部通过。标准库数据 CI 仍可运行，没有 Docling 时明确跳过其十项契约测试（包括 M1-13 新增的原生中文、空页和缺页 CLI 回归）。质量检查本身及其测试只依赖标准库。Compose CI 只安装开发工具，不承担 PDF 推理验证。

2026-10-23 在 Windows / Python 3.12.10 上，通过上述 CLI 解析了已验原文件指纹的 4 个物理页；模型五个文件的 SHA-256 全部匹配，推理时设置 `HF_HUB_OFFLINE=1` 与 `TRANSFORMERS_OFFLINE=1`。对照本地渲染页面检查结构：

| 来源与物理页 | 本地观察 |
| --- | --- |
| `ABB-FW-H-ZH`，536 | 3 行 × 4 列表格（含表头），与页面标题按顺序保留。 |
| `ABB-FW-H-ZH`，537 | 14 行 × 4 列表格，措施列保留跨 9 行的合并单元格。 |
| `ABB-FW-H-ZH`，538 | 12 行 × 4 列表格，故障码含 `42F1`；未转成数字。 |
| `ABB-HW-D-ZH`，152 | 标题、正文、两处图标和 4 个列表项保留在阅读树中。 |

三个连续表格页的输出页号仍为 536、537、538，未按选定范围重新从 1 编号。这只是四页的技术抽查，不是全量手册准确率或领域专家验收。PDF 原文、页面渲染、模型权重和提取结果均留在忽略目录，不提交 Git。

M1-08 的专项测试位于 `tests/test_document_key.py`；解析命令测试另覆盖完整身份元数据、不同页范围主键相同，以及缺失字段和重复来源 ID 在推理前失败。以上测试使用来源清单元数据或项目自造输入，不增加厂商原文的公开副本。

2026-10-28 在 Windows / Python 3.12.10 上以离线模式重新解析硬件手册第 152 页，输出为本地忽略文件 `data/processed/m1-08-hardware-152.json`。回读确认 `source` 的全部 8 个字段与来源清单及主键规则一致，`schema_version=1`、请求页范围与物理页 152 保留；这是身份字段的集成验收，不新增解析质量或领域复核结论。

M1-09 的 `tests/test_fault_codes.py` 使用自造单元格检查前导零、ASCII 大小写、原值保留、非法值拒绝、主码/辅助码列隔离、普通表排除及本次解析内的引用解析；`tests/test_pdf_parsing.py` 检查 CLI 序列化同时保留两个码值和原文。

2026-10-28 在同一本地锁定环境、离线模型模式下重新运行固件手册 536–538 页解析，输出到忽略文件 `data/processed/m1-09-firmware-536-538.json`。回读得到 18 个主故障码（536 页 2 个、537 页 5 个、538 页 11 个），含 `42F1`；逐项 `cell_ref` 均能回到对应原始码值，父文档身份与物理页号匹配。辅助码列中的 `0001`、`0002`、`0004`、`0008`、`0010`、`0020`、`0040`、`0080` 未混入主码列表。该结果只覆盖三页样本，不是全量召回率。

M1-10 的 `tests/test_chunking.py` 覆盖阅读树顺序、标题层级、警告与列表上下文、原因/措施同行、九行共享措施、未识别主码隔离、前置无主码行、普通表保留和引用回读；PDF 契约测试另检查真实 Docling 数据结构和 CLI 的 `chunks` 序列化。自造测试不提交厂商原文。

2026-10-28 用上述 CLI 在离线模型模式下重新解析固件 536–538 页、硬件 152 页，分别保存为忽略的 `data/processed/m1-10-firmware-536-538.json` 和 `data/processed/m1-10-hardware-152.json`。固件形成 18 个故障行组，`2340` 的辅助行和跨九行措施保留在同一块；硬件形成 1 个章节块，保留两处警告、四个有编号的步骤和两处图片引用。19 个块的父文档主键、内容/标题引用及原文完整保留检查均通过；共享措施在所属块内仅出现一次。该检查覆盖既有四页样本，不代表全量切块质量或人工领域复核。

M1-11 的 `tests/test_evidence_ids.py` 覆盖引用/块重排、表和单元格重编号、重复定位、来源/指纹/位置变化、坐标原点与精度规范化、跨页文本、图片以及不完整或有歧义的定位拒绝。PDF 契约测试另覆盖 Docling 原生 provenance 的 JSON 往返、CLI 输出定位器和缺少定位时不写文件。

2026-10-28 在同一本地锁定环境中，对两次独立解析的固件 536–538 页、硬件 152 页结果重新切块并计算 ID，18 个故障行组和 1 个章节块的 ID 集合分别一致。随后离线单独重解析固件 538 页与硬件 152 页，保存为忽略文件 `data/processed/m1-11-firmware-538.json` 和 `data/processed/m1-11-hardware-152.json`；11 个固件块和 1 个硬件块的 ID 与之前结果中对应物理页一致，来源摘要及 ID 回算均通过。该抽查验证同一锁定环境下的稳定性，不代表解析器升级或全量手册的稳定性承诺。

M1-12 的 `tests/test_location_metadata.py` 用自造标签验证跨页全部保留、未知页为 `null`、标签原值保留、摘要过期/无效映射拒绝、父文档隔离和表内行范围；PDF 契约另覆盖原生 Docling 跨页正文、CLI 的映射快照及推理前失败。印刷标签来源于既有核验记录，不读取评测标签。

2026-10-29 回读既有四页解析结果，19 个块的页码、父文档与表行范围均匹配，证据 ID 未变。再以离线模型模式独立解析固件 537 页和硬件 152 页，分别保存为忽略文件 `data/processed/m1-12-firmware-537.json`、`data/processed/m1-12-hardware-152.json`：5 个故障行组和 1 个章节块的物理/印刷页标签均符合已核验映射，ID 与既有对应页一致；九行共享措施所在块保留 `[1, 10]` 行范围。跨页行为由合成 Docling 契约验证，不将这两页单页样本描述为真实跨页质量验收。

M1-13 新增 10 项标准库质量测试和 3 项原生 Docling 契约，覆盖中文/符号的完整往返、显式坏字符拒绝、空页保留、逻辑表格越界/跨度/重叠、合法共享单元格、断行码隔离、跨页单元格歧义拒绝，以及缺页或质量失败时不发布输出。2026-10-29 回读固件 536–538 页和硬件 152 页，100 个表格单元格及文本项通过新增检查，19 个块仍能生成，原始文档未改写。这是既有四页的兼容性抽查，不是全量手册乱码率或错行率测量。

同日以离线模型模式重新运行固件第 537 页 CLI，保存为忽略文件 `data/processed/m1-13-firmware-537.json`。5 个块的完整内容、故障码、证据 ID 和定位元数据均与 M1-12 的同页结果一致，九行共享措施所在块仍为 `[1, 10]`；新增质量检查没有改写该样本。

后续仍需实现：M1-14 增量识别，以及 M1-15 人工抽样和 M1-16 安全标签。此次技术检查不替代人工或领域专家复核。
