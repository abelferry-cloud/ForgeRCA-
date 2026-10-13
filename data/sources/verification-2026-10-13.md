# ABB PDF 获取与核验记录

日期：2026-10-13（Asia/Shanghai）。范围：M0-03、M0-13，以及配套的 M0-04、M0-05 本地检查。

核验基线：`main` 提交 `6787164`；工作分支：`data/M0-13-abb-source-verification`。本记录由 Codex 执行工具并检查页面后编写，未经过人类领域专家审核。

## 计划与验收

1. 按 [manifest.json](manifest.json) 从 ABB 官方链接下载两份固定版本 PDF；验收：文件大小、文件头和 SHA-256 均匹配。
2. 独立核对实际页数、文档编号、修订、生效日期、适用范围及清单指定页面；验收：PDF 工具输出和页面内容与来源清单一致。
3. 重跑下载器、离线校验和测试；验收：已有文件可复用，原始文件校验成功，现有测试通过。
4. 仅提交来源核验记录和相关说明，通过 PR 验收；PDF 原文、页面图像和提取文本不进入 Git。

前 3 项已在本地完成；本记录随第 4 项提交审阅。M0-06 人工领域复核与 M1 应用开发不属于本次范围。

## 环境与文件结果

- 下载器、校验器和单元测试：Windows，Python 3.12.10，仅使用项目已有标准库脚本。
- 独立页面检查：Codex 自带 Python 3.12.14、pypdf 6.10.0、Poppler 26.07.0（`pdfinfo`、`pdftoppm`）。这些是本次核验工具，未新增项目运行依赖。
- 两个官方链接均成功返回清单锁定的文件；未使用镜像、修改来源清单或放宽哈希检查。

| source_id | 本地文件 | 实际字节数 | 实际页数 | 结果 |
| --- | --- | ---: | ---: | --- |
| ABB-FW-H-ZH | `data/raw/abb/acs580-firmware-h-zh.pdf` | 13438874 | 614 | 大小、PDF 文件头、SHA-256 和页数均匹配 |
| ABB-HW-D-ZH | `data/raw/abb/acs580-01-hardware-d-zh.pdf` | 44371188 | 316 | 大小、PDF 文件头、SHA-256 和页数均匹配 |

经校验匹配的 SHA-256：

```text
ABB-FW-H-ZH  e6ed9eab8c6a06afc0411a7ab11ace174e56385f9c554a221c3309571e4eb2b6
ABB-HW-D-ZH  c2aa260efb335368930df8bd5ea44c8fd715fa1a845cc344fcfd089a870a2ece
```

## 页面检查

页码均为从 1 开始的 PDF 页序号。使用 pypdf 提取以下完整页面的文本，并用 `pdftoppm` 渲染同一批页面检查图像；`pdfinfo` 与 pypdf 返回的总页数一致。

| 来源 | PDF 页码 | 核验内容与结果 |
| --- | --- | --- |
| ABB-FW-H-ZH | 3 | 中文文档编号 `3AXD50000016430`、修订 H、生效日期 2024-03-30，与清单一致 |
| ABB-FW-H-ZH | 13 | 适用性说明包含 `ASCKX 2.16`，与清单及 K008 定位一致 |
| ABB-FW-H-ZH | 536 | 存在故障表 2310 条目，K001 定位一致 |
| ABB-FW-H-ZH | 537 | 存在故障表 3210 条目，K002 定位一致 |
| ABB-FW-H-ZH | 538 | 存在故障表 3220、3381、4210 条目，K003–K005 定位一致 |
| ABB-FW-H-ZH | 542 | 存在故障表 7081 条目，K006 定位一致 |
| ABB-HW-D-ZH | 3 | 中文文档编号 `3AXD50000044837`、修订 D、生效日期 2023-02-07，与清单一致 |
| ABB-HW-D-ZH | 25 | 适用性说明包含 `ACS580-01`，与来源说明一致 |
| ABB-HW-D-ZH | 152 | 存在散热器清洁小节及安全警告，K007 定位一致 |

上述正文页面的印刷页号与 PDF 页序号一致；两个第 3 页是版本信息页，未将其未印出的页号当作印刷页码。K009 为虚构干扰记录，没有厂商 PDF 锚点。本次未修改知识注释、工单、告警、图谱参考或评测标签，也未将来源核验视为维修结论审核。

## 复现命令与执行结果

在仓库根目录运行，所有命令均已成功执行：

```sh
python scripts/download_sources.py
# 首次：Downloaded and verified ABB-FW-H-ZH / ABB-HW-D-ZH

python scripts/download_sources.py
# 再次：Verified existing ABB-FW-H-ZH / ABB-HW-D-ZH

python scripts/validate_data.py
python scripts/validate_data.py --check-raw
python -m unittest discover -s tests -v
```

两个校验命令的计数均为：2 个来源、33 条证据、17 个问题、15 个图谱节点、14 条边。带 `--check-raw` 的命令返回 `Raw PDFs: verified`；18 项单元测试全部通过。下载器的重复执行复用了已核验文件。

在已安装 Poppler 并将其可执行文件加入 PATH 的核验环境中，可独立复现页数检查：

```sh
pdfinfo data/raw/abb/acs580-firmware-h-zh.pdf
# Pages: 614
pdfinfo data/raw/abb/acs580-01-hardware-d-zh.pdf
# Pages: 316
```

页面内容需按上表打开 PDF 检查，不能仅凭 SHA-256 或页数命令推导。当前 `--check-raw` 只校验路径、文件存在、大小、PDF 文件头与 SHA-256，不调用 PDF 解析工具。

## 发布与未完成项

`git check-ignore` 确认两份 PDF 命中 `data/raw/` 忽略规则；页面渲染仅存于被忽略的 `artifacts/source-verification-2026-10-13/`。公开记录只包含来源元数据、定位信息和核验摘要，不包含原文、页面图像或完整提取文本。

第三方原文的再分发状态仍为 `not_verified`。M0-06 人工领域复核仍待安排，现有 `review_status` 保持不变；本次没有完成完整 M0、检索服务或诊断功能。
