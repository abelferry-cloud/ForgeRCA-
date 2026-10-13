# Contributing to ForgeRCA

感谢关注 ForgeRCA。目前处于**设计与数据初始化**阶段，欢迎按 [TODO.md](TODO.md) 的任务 ID 参与，尤其欢迎带真实来源证据的文档纠错、数据字段规范和可重复评测。

## 开始前

1. 阅读 [README](README.md)、[项目范围](docs/project-scope.md)、[数据规范](docs/data-spec.md) 与 [数据来源](docs/public-datasets.md)。
2. 使用一个 Issue 明确任务 ID、预期输入输出、依赖和验收用例；不承诺的功能不要写作已实现。
3. Fork 后使用 `feat/M2-05-rrf`, `fix/M0-15-evidence-anchor`, `docs/public-data-guide` 等有语义的分支名。
4. 修改业务代码时同步添加测试；修改数据时同步更新数据卡 / 来源清单 / 证据映射。

## 在本地验收

```bash
python scripts/validate_data.py
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

仓库当前尚未统一选择原创内容的发布许可证。第三方资料继续使用各自的授权；请在贡献前确认贡献内容不会使仓库承受无法履行的再分发义务。开源许可证选定后，本节应同步更新。
