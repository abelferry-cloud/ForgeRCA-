# PDF 结构化解析（M1-07）

当前提供已登记 ABB 手册的物理页范围解析。使用 Docling 2.142.0，保留原生文档树、标题/正文标签、表格单元格与页码来源；没有切块、稳定证据 ID、业务入库或检索。适用对象是带原生文字层的 PDF；OCR 关闭，扫描页不在本次验收范围。

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

- `source`：已验证的 `source_id` 和原文件 SHA-256，仅作来源追溯；文档主键规则仍属 M1-08。
- `parser`：实际 Docling / docling-core / docling-parse 版本、页范围、选用参数及模型 revision/文件指纹。
- `document`：原生 `DoclingDocument` JSON，不将文本与表格转成一个丢失结构的字符串。

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

只有完整成功且返回全部请求页面时才写输出；部分成功、缺页和源文件指纹错误均失败，不发布为成功结果。解析成功仍不等于语义准确；表格重构、跨页内容和分类错误需要后续质量复核。

## 验收范围

`tests/test_pdf_parsing.py` 使用项目自造的 Docling 文档和临时输入，覆盖标题/段落/表格交错、跨页 provenance、合并单元格、前导零保留、部分失败/缺页、模型指纹、损坏缓存恢复、来源指纹和输出路径边界。测试不下载模型，不读取厂商 PDF，也不读取评测标签。

```bash
uv run --frozen python -m unittest discover -s tests -p test_pdf_parsing.py -v
```

`.github/workflows/pdf-parser.yml` 在 Linux / Python 3.11 安装锁定的 CPU 依赖，运行上述离线契约测试；[首次 CI 运行](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/39929017180) 的 11 项测试全部通过。标准库数据 CI 仍可运行，没有 Docling 时明确跳过其四项契约测试。Compose CI 只安装开发工具，不承担 PDF 推理验证。

2026-10-23 在 Windows / Python 3.12.10 上，通过上述 CLI 解析了已验原文件指纹的 4 个物理页；模型五个文件的 SHA-256 全部匹配，推理时设置 `HF_HUB_OFFLINE=1` 与 `TRANSFORMERS_OFFLINE=1`。对照本地渲染页面检查结构：

| 来源与物理页 | 本地观察 |
| --- | --- |
| `ABB-FW-H-ZH`，536 | 3 行 × 4 列表格（含表头），与页面标题按顺序保留。 |
| `ABB-FW-H-ZH`，537 | 14 行 × 4 列表格，措施列保留跨 9 行的合并单元格。 |
| `ABB-FW-H-ZH`，538 | 12 行 × 4 列表格，故障码含 `42F1`；未转成数字。 |
| `ABB-HW-D-ZH`，152 | 标题、正文、两处图标和 4 个列表项保留在阅读树中。 |

三个连续表格页的输出页号仍为 536、537、538，未按选定范围重新从 1 编号。这只是四页的技术抽查，不是全量手册准确率或领域专家验收。PDF 原文、页面渲染、模型权重和提取结果均留在忽略目录，不提交 Git。

后续仍需实现：M1-08 文档主键、M1-09 故障码规范化、M1-10 切块、M1-11 稳定证据 ID、M1-12 印刷页码与段落/表行定位、M1-13 质量测试、M1-14 增量识别，以及 M1-15 人工抽样和 M1-16 安全标签。此次技术检查不替代人工或领域专家复核。
