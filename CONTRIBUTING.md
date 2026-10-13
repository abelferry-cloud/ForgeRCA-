# Contributing to ForgeRCA

感谢关注 ForgeRCA。目前处于**设计与数据初始化**阶段，欢迎按 [TODO.md](TODO.md) 的任务 ID 参与，尤其欢迎带真实来源证据的文档纠错、数据字段规范和可重复评测。

## 开始前

1. 阅读 [README](README.md)、[项目范围](docs/project-scope.md)、[数据规范](docs/data-spec.md) 与 [数据来源](docs/public-datasets.md)。
2. 使用一个 Issue 明确任务 ID、预期输入输出、依赖和验收用例；不承诺的功能不要写作已实现。
3. 从 `main` 切出功能分支，命名遵循下面的[分支与合并规范](#分支与合并规范)；**不要直接向 `main` 提交**。
4. 修改业务代码时同步添加测试；修改数据时同步更新数据卡 / 来源清单 / 证据映射。

## 分支与合并规范

`main` 是唯一的稳定主线。进入 `main` 的内容必须保持可校验、可复现。

- **禁止直接向 `main` 提交或推送。** 所有改动从 `main` 切出功能分支，通过 Pull Request 合并。
- **唯一例外**：极小且无风险的改动可以直接提交到 `main`，仅限错别字修正、注解里的笔误、失效链接修复、徽章或格式微调；或在取得维护者明确允许后提交。判断有争议时，一律按普通流程走 PR。
- **除此之外的改动都必须先建分支**，包括文档改写、数据字段调整、脚本与测试变更、依赖引入、CI 配置调整。没有明确授权不得绕过。

分支命名前缀：

| 前缀 | 用途 | 示例 |
| --- | --- | --- |
| `feat/` | 新功能或新能力 | `feat/M2-05-rrf` |
| `fix/` | 缺陷与数据错误修复 | `fix/M0-15-evidence-anchor` |
| `docs/` | 纯文档改动 | `docs/public-data-guide` |
| `chore/` | 工程维护、CI、依赖、许可证 | `chore/m0-license-and-branch-policy` |
| `data/` | 语料、来源清单与评测集调整 | `data/M0-13-abb-pdf-fingerprints` |

约定：

- 分支名建议带上 [TODO.md](TODO.md) 的任务 ID（如 `feat/M1-21-dense-retrieval`），便于与 Issue 对应。
- 一个分支只做一件事，不要混合无关重构；合并方式默认 squash，保持 `main` 线性可读。
- 合并前必须通过 `python scripts/validate_data.py` 与 `python -m unittest discover -s tests -v`。
- `codex/initialize-project` 是历史遗留分支，仅作存档，不再接收新提交；新工作一律从 `main` 切出。

## 在本地验收

```bash
python scripts/validate_data.py
python scripts/check_sensitive_files.py
python -m unittest discover -s tests -v

# 仅在已下载且拥有对应固定版本的 ABB 官方 PDF 时执行
python scripts/validate_data.py --check-raw

# 新增公开数据下载器的离线测试
python -m unittest discover -s tests -p 'test_download_public_data.py' -v
```

如果修改了新引入的构建依赖，请记录锁文件、Python 版本、复现命令和运行结果。当前不应假定 FastAPI / Neo4j / LangGraph 服务已可运行。

## Pull Request 格式

- **关联任务**：例如 `M1-11`。
- **背景**：修复什么问题、对应什么来源或错误案例？
- **变更摘要**：数据结构/API/行为的前后区别。
- **证据**：真实可运行命令、输出摘要、测试、必要时截图。
- **影响**：数据授权、模型/文档版本、评测泄漏、执行安全。
- **待办**：本 PR 未覆盖的边界条件。

## 数据和安全

- **不要**上传客户隐私、设备访问凭据、企业内部维修工单、ABB 完整官方 PDF 或任何未获许可的文件。
- 所有用于演示的虚构数据统一标注 `synthetic=true`；未经审核的标注不能写“专家认证”。
- GraphRAG 关系必须可定位到原始证据；`confirmed_cause` 仅限已确认的历史事件，不自动等于当前设备确诊。
- PR 不得把 `data/evaluation/` 或人工 gold labels 加入检索索引。
- 维修操作或诊断文本涉及设备安全时，保留“需由专业人员验证”的限制，不输出自动控制动作。

## 对实验结果的要求

如声称性能提升，请至少提供版本、样本数、gold 定义、模型、统计方法、基线配置、逐题结果和失败案例。暂不接受把目标数字（例如 89% Recall@5）写成未经运行的实测结论。

## 版权与授权

本项目原创代码、文档与合成数据采用 **[Apache License 2.0](LICENSE)**。据此，你的贡献一旦合并，即视为在 Apache-2.0 下授权；请在提交前确认你有权作出该授权。

Apache-2.0 **不覆盖第三方资料**：厂商 PDF 版权属于其权利人，MaintIE（MIT）、AI4I 2020 与 MetroPT-3（CC BY 4.0）等外部数据集继续适用各自授权。贡献前请确认所提交内容不会使仓库承受无法履行的再分发义务，且不要把未获再分发许可的材料（尤其是厂商 PDF 全文或截图）提交到公开仓库。
