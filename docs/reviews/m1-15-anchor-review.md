# M1-15 证据锚点人工核对

准备日期：2026-11-01。准备者：Codex（AI）。关联 [Issue #30](https://github.com/abelferry-cloud/ForgeRCA-/issues/30)。**33 个锚点已准备，全部待人工核对；M1-15 尚未完成。** 本材料不替代 M0-06 的种子领域复核，也不是最终 200 条诊断评测样本。

## 打开材料

- [公开审核清单](m1-15-anchors.json)：固定输入指纹、完整证据 ID、页码/表行定位和空白人工字段，不含块文本或标题。
- 本机阅读包：`artifacts/reviews/m1-15-anchors.html`。用本机浏览器打开，每项显示解析文本、原 PDF 物理页链接和可展开的定位器/引用；HTML 只读，不保存或自动同步审核结论。
- 原 PDF、解析快照和含厂商原文的 HTML 都在忽略目录。克隆仓库不会获得这些文件，需按下方命令准备自己的本地材料。不要上传 HTML、截图或完整提取结果。

所有材料均属于审核用途，`docs/reviews/` 与 `artifacts/` 不在检索 allowlist 内。

## 样本与边界

采用明确选页后的全块纳入：在现有固件 536–538 页、硬件 152 页样本上增加已核验过的固件 542 页，纳入这五个物理页的全部 33 个不同证据 ID。没有用同一锚点的多次解析凑数，也没有根据评测答案选样。这是针对已有页面的目的性抽样，不能据此估计全量手册准确率。

| 样本编号 | 来源 | 物理页 | 块类型 | 数量 |
| --- | --- | --- | --- | --- |
| A001 | ABB-HW-D-ZH | 152 | section | 1 |
| A002–A003 | ABB-FW-H-ZH | 536 | fault_rows | 2 |
| A004–A008 | ABB-FW-H-ZH | 537 | fault_rows | 5 |
| A009–A019 | ABB-FW-H-ZH | 538 | fault_rows | 11 |
| A020–A033 | ABB-FW-H-ZH | 542 | fault_rows | 14 |

样本包括九行共享措施的故障行组、故障码和硬件章节中的警告/列表上下文；以故障表为主，正文多样性有限。不覆盖扫描页、真实跨页表格或全量手册；OCR 当前关闭。印刷页只采用来源清单已核验的映射，不自行推断。

`sample_id` 仅是本次审核的导航编号；永久身份仍是完整 `evidence_id`。`input_index` 指向清单的 `inputs`，`chunk_index` 是对应固定快照中 `chunks` 的零基位置，不能脱离该快照 SHA-256 当作永久锚点。定位器和原始引用在本地 HTML 及解析快照中可查，定位坐标约定见 [数据规范](../data-spec.md#chunk-稳定证据-idm1-11)。

## 人工逐项核对

1. 核对 `inputs` 中的 PDF 和解析快照完整 SHA-256，确认实际打开的是清单指定文件。HTML 链接中的 `#page=` 是物理页号；若阅读器未跳页，手动跳转，不能用印刷页号替代。
2. 对照原 PDF，检查证据定位器的全部物理位置是否覆盖对应文本/单元格，`locations`、父文档、修订与表行范围是否一致；检查解析文本有无乱码、遗漏、错行或跨行内容归属错误。
3. 检查原因/措施是否仍属同一故障行组，共享措施是否完整；章节标题、条件、警告与列表是否保留必要上下文。记录不确定项，不将结构校验当成语义正确证明，也不据此给出设备维修结论。
4. 在公开清单对应 `items` 行填写真实 `reviewer`、`review_date`（`YYYY-MM-DD`）、`decision` 和 `notes`。不复制厂商长段原文，用字段名、页码和问题描述记录发现。

| `decision` | 使用条件 |
| --- | --- |
| `pending` | 尚未实际核对；初始审核人、日期和备注为 `null`。 |
| `accepted` | 人工已逐项核对且无待处理问题；备注可填“已核对，无需修改”。 |
| `needs_changes` | 发现具体问题；备注注明错误字段/页码、理由、修复 Issue 或提交。 |
| `uncertain` | 暂不能判断；注明缺少的资料或需要的复核。 |

AI 不代填人工身份、日期或结论。审核不能只用“PR 通过”替代逐项记录。M1-15 收口时至少 30 个不同锚点应有真实人工记录；`pending` / `uncertain` 不计入已完成核对，有问题的项需留下修复及复核记录。维护者通过后续 PR 核实记录后再勾选 TODO、关闭 Issue #30。本准备 PR 保持该 Issue 开放。

## 准备与复现

脚本仅依赖标准库；模型只用于生成解析快照。先按 [PDF 解析说明](../pdf-parsing.md) 安装锁定环境、获取已登记原 PDF 与固定模型，然后执行：

```bash
python scripts/validate_data.py --check-raw
uv run --frozen python -m scripts.parse_pdf --source ABB-FW-H-ZH --pages 536 538 --output data/processed/review-firmware-536-538.json
uv run --frozen python -m scripts.parse_pdf --source ABB-FW-H-ZH --pages 542 542 --output data/processed/review-firmware-542.json
uv run --frozen python -m scripts.parse_pdf --source ABB-HW-D-ZH --pages 152 152 --output data/processed/review-hardware-152.json
python -m scripts.prepare_anchor_review --inputs data/processed/review-firmware-536-538.json data/processed/review-firmware-542.json data/processed/review-hardware-152.json --inventory docs/reviews/m1-15-anchors-new.json --output artifacts/reviews/m1-15-anchors-new.html
```

命令只接受显式指定的 `data/processed/` JSON；回算 ID，核对来源身份、原 PDF 文件头/大小/指纹和展示定位，拒绝缺少 ID、过期定位、重复输入或重复 ID。纳入全部输入块，少于 30 个不同锚点即失败，不随机补样。公开清单仅可写入 `docs/reviews/` 的新 JSON，HTML 仅可写入 `artifacts/` 的新文件；验证失败不发布结果，已有审核清单或阅读包不会覆盖。

本次解析代码基线为 `1bd452e`（PR #29 合并结果）。固件两份快照于 2026-11-01 在锁定环境、`HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` 下重新解析；硬件复用已保存的 `m1-12-hardware-152-with-map.json`，生成审核包时再次核对原 PDF 指纹和锚点。清单记录三个快照、原 PDF、来源清单及解析配置指纹；复现时应以自己的输出生成新清单，不能假定重新解析的字节指纹或样本编号与本次相同。

重新解析或修改切块/定位后，旧审核仍绑定旧快照。先使用 M1-14 的比较命令识别变化，再创建新审核记录并明确复核受影响锚点，不按 `sample_id` 或数组序号搬运旧结论。

## 准备阶段验证

2026-11-01：11 项合成输入专项测试通过，覆盖公开清单与原文分离、HTML 转义、人工字段初始为空、原文指纹变化、缺少/错误定位、重复或不足 30 个样本、路径边界及拒绝覆盖已有审核记录。全量 pytest 为 231 passed / 394 subtests passed；系统 Python unittest 为 227 项、12 个跳过记录（11 项 Docling 契约及缺少 just 的测试类）；Ruff、种子数据校验和两份原 PDF 指纹校验通过。

从清单指定的本地输入重新生成，公开清单及 HTML 与已保存结果完全一致；结构检查得到 33 个不同 ID、33 个待审项和 33 个原页链接，审核路径仍被检索 allowlist 拒绝。这些结果只验证准备流程，不计为人工核对。
