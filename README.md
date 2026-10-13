# ForgeRCA

面向设备手册、维修工单与告警的工业故障诊断项目，计划采用 Agentic GraphRAG，实现可追溯的根因分析与排查建议。

**当前阶段：项目初始化。** 已准备业务与技术文档、官方资料来源清单、合成工单与告警、开发/演示问题、图谱校验样例和离线数据检查工具。尚未实现检索服务、LangGraph 工作流、API 或展示界面。

业务首期聚焦 **ABB ACS580-01 变频器及其电机负载**。原始官方手册仅保存在本地；仓库中的工单、设备实例、告警和诊断事件均为合成教学数据。项目与 ABB 无隶属或认证关系，样例不能作为真实设备操作依据。

## 从这里开始

需要 Python 3.11+；初始化工具只使用标准库，不需要 API Key、Docker 或数据库。

```sh
git clone https://github.com/abelferry-cloud/ForgeRCA-.git
cd ForgeRCA-
python scripts/validate_data.py
python -m unittest discover -s tests -v
```

获取固定版本的官方 PDF（需要访问 ABB 官方网站，约 58 MB；文件自动留在 Git 忽略目录）：

```sh
python scripts/download_sources.py
python scripts/validate_data.py --check-raw
```

下载器会验证文件头、大小和 SHA-256，不覆盖不匹配的现有文件。若官方链接或文件改变，按 [来源说明](data/sources/README.md)核验后更新清单。

## 文档导航

| 文档 | 解决的问题 |
| --- | --- |
| [项目范围](docs/project-scope.md) | 为谁诊断、输入输出、边界与验收 |
| [架构设计](docs/architecture.md) | 组件职责、数据流、补检与停止条件 |
| [数据规范](docs/data-spec.md) | 数据字段、证据定位、版本、时间与许可 |
| [知识图谱](docs/knowledge-graph.md) | 实体关系、抽取与实体消歧、遍历边界 |
| [评测规范](docs/evaluation.md) | 三类基线、消融、指标、成本统计与防泄漏 |
| [演示与里程碑](docs/demo-and-milestones.md) | 当前可检查的样例与后续实施顺序 |
| [数据卡](data/README.md) | 各类数据的性质、数量与局限 |
| [来源与许可记录](data/sources/README.md) | 原始资料链接、版本与获取方法 |

## 目录

```text
docs/                     设计、规范与验收说明
data/sources/             官方来源与文件指纹
data/corpus/              可检索的短知识注释、合成工单、合成告警
data/evaluation/          开发与演示问题、证据标注（禁止入索引）
data/graph/               人工编排的抽取校验参考（禁止作为生产图谱导入）
data/raw/                 本地下载 PDF（不提交）
scripts/                  下载与离线一致性校验
tests/                    数据校验器的异常场景测试
```

## 技术方向与真实状态

计划采用 LangGraph、FastAPI、Neo4j、OpenSearch、PostgreSQL、BGE-Reranker 和 Langfuse。首期按里程碑逐项引入，当前未安装这些运行时依赖，也未提供尚不可用的服务启动命令。

| 指标 | 当前状态 |
| --- | --- |
| 正式 200 条盲测样本 | 尚未建立、未冻结 |
| 证据 Recall@5 / 根因 Top-1 | 尚未运行实验 |
| 平均延迟 / P95 / Token / 成本 | 尚未测量 |

早期简历草案中的 76%→89%、68%→83%、4.2s→9.6s、3.2k→7.1k 是**待验证目标，不是项目结果**。开发样例验证通过仅表示数据一致，不表示诊断准确率达标。

## 贡献与授权

使用功能分支提交；提交前执行上述离线检查。来源指纹、事实校验状态或数据划分有变化时同步更新数据卡。当前原创代码与数据尚未选择统一开源许可证；公开可见不代表第三方资料可以再分发。第三方资料保留各自权利，详见来源记录。
