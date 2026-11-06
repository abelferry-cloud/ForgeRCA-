# 版本锁定与复现范围（M1-06）

核验日期：2026-10-23。机器可读清单为 [`versions.lock.json`](../versions.lock.json)。清单锁定外部工件身份；运行验证范围分别见[本地服务](local-services.md)和 M1-07 [PDF 解析说明](pdf-parsing.md)。它不代表业务迁移、embedding 推理或检索已实现。

## 锁定内容

| 项目 | 固定身份 | 本次验证及后续边界 |
| --- | --- | --- |
| Python 开发环境 | `uv.lock`；uv `0.10.12` | `uv sync --frozen`，本机 Python 3.12.10；项目最低 3.11，开发工具版本以锁文件为准 |
| Docling | `docling==2.142.0`、`docling-slim==2.142.0` 的 wheel SHA-256 | M1-07 已引入运行依赖，完整依赖见 `uv.lock`，解析范围见 [PDF 说明](pdf-parsing.md)。Docling 此版本通过 `docling-slim[standard]` 提供实现 |
| DB migration 工具 | `alembic==1.20.1` 的 wheel SHA-256 | M1-17 安装并核对锁文件中的 wheel 指纹；SQLAlchemy 2.1.6、psycopg / psycopg-binary 3.3.7 及传递依赖锁在 `uv.lock`，迁移与验收见[数据库说明](database.md) |
| 初始向量模型 | `BAAI/bge-m3`，revision `5617a9f61b028005a4858fdac845db406aefb181` | 核对该 revision 下四份配置文件及 SHA-256；未下载权重或运行推理 |
| OpenSearch mapping | [`dense-v2.json`](../config/opensearch/dense-v2.json) 的完整字节 SHA-256 | M1-19 加入精确型号/版本/固件及来源字段，保留 1024 维、Lucene HNSW、cosine；字段契约和 CI 见[索引说明](opensearch.md) |
| 本地服务镜像 | 三个多架构 image index / manifest list digest | Compose 直接使用 `tag@sha256:…`，固定镜像集合；Linux CI 验证启动和保留卷重建 |

包来源：[Docling 2.142.0](https://pypi.org/project/docling/2.142.0/)、[Docling Slim 2.142.0](https://pypi.org/project/docling-slim/2.142.0/)、[Alembic 1.20.1](https://pypi.org/project/alembic/1.20.1/)。清单记录实际下载 wheel 的 URL 和实算 SHA-256，并与 PyPI JSON 元数据一致。M1-07 已安装并锁定 Docling 的传递依赖；M1-17 已安装 Alembic 及数据库依赖，锁定 wheel 与既有指纹一致。清单不能替代 Python 依赖锁文件。

模型的 [固定 revision](https://huggingface.co/BAAI/bge-m3/tree/5617a9f61b028005a4858fdac845db406aefb181) 保留权重和配置身份。配置显示 1024 维、CLS pooling、Normalize 模块与 8192 最大序列长度；这些是上游配置事实，不是本机推理结果。M1-20 仍需锁定并实测推理库、计算精度、归一化调用、截断策略与批大小；不得仅靠模型名或 `main` 下载来复现实验。

M1-07 已在 `pdf_parser_models` 中固定 Docling 布局/表格模型的完整 revision 与五个文件指纹，解析结果记录选用参数，OCR 当前关闭。M1-14 的[比较命令](pdf-parsing.md#重解析结果比较m1-14) 对输出中记录的包版本、参数和模型身份计算配置指纹；配置变化单独报告，再按稳定证据 ID 比较实际块变化，不将配置变化直接等同于所有内容变化。该指纹不涵盖全部运行环境、硬件或应用代码，不能仅靠它或 wheel 指纹承诺逐字复现。生成模型与 reranker 尚未选择，不列为已锁定项。

## Mapping 边界

`dense-v1` 是 M1-06 的历史最小基线，只有 `evidence_id` 和 `embedding`，文件保持不变。M1-19 新建 `dense-v2` 并更新当前指纹，增加正文、来源身份、精确型号/修订、显式合成标识、可用时间和固件语义字段。`dynamic: strict` 禁止自动添加字段；`_meta` 记录 mapping 版本、模型完整名与 revision，用于追溯，不会自动下载模型或检查向量来源。

字段类型和距离定义依据 [OpenSearch 2.17 文档](https://docs.opensearch.org/2.17/field-types/supported-field-types/knn-vector/)。单分片、零副本是本地验收设置，HNSW 参数不是调优结果。CI 创建一次性索引、回读 mapping 和人工向量，检查字段精确筛选、空值语义、跨修订身份及错误输入拒绝；没有调用 embedding 模型或索引语料。

M1-19 已提供字段和写入前校验；真实模型推理、语料转换/批量索引及检索仍须在后续任务完成，不能直接把种子 JSONL 写入此 mapping。任何 mapping 变更须新建版本文件并更新清单 SHA-256；模型维度或身份改变时必须同时审查 mapping、重建索引，不能复用旧向量。

## 容器身份

沿用 M1-04 的标签，但执行时以清单和 Compose 中的 digest 为准。多架构 digest 允许 Docker 按宿主架构选择固定子镜像；本次运行验收仅覆盖 Linux amd64。

| 标签 | 本次核验的 Linux amd64 子镜像 digest |
| --- | --- |
| `postgres:16.4-alpine` | `sha256:f5aa7cac1dc299a77761ada5a5cf9c6ef4064bc85c89fed49c587dd2381d6f05` |
| `opensearchproject/opensearch:2.17.1` | `sha256:ab6db8c14062060cda5f0428364e76ffe2a6f03ad265589b70182c0cecb7f9d7` |
| `neo4j:5.26-community` | `sha256:85527686017fdea46d83cf40c34093b39a3796b46c22ba9e54dbdb2821296693` |

以上由 `docker buildx imagetools inspect` 查询 Docker Hub 得到，不要求本机 daemon 启动。Neo4j 的 `5.26-community` 标签在本次快照实际指向 `5.26.32-community-trixie`，不能把可变系列标签视作精确补丁版本。digest 固定下载内容，不是最新版本或安全审计结论；Windows 本机容器启动限制仍见[本地服务说明](local-services.md)。

## 复验与更新

仓库根目录执行：

```bash
uv sync --frozen
uv run --frozen just lint
uv run --frozen just test
uv run --frozen just data-check

# 显式联网：仅在内存下载三个 wheel 和四份模型配置并验 SHA-256
# 不安装包，不下载权重，不修改清单或本地环境
python scripts/verify_version_artifacts.py
```

网络失败会返回非零，不算核验成功；离线单元测试不会尝试访问 PyPI、Hugging Face 或 Docker Hub。镜像复验可对清单内完整 `tag@sha256:…` 执行 `docker buildx imagetools inspect`；不要用当前标签的最新解析结果覆盖历史快照。

2026-10-23 验收记录：Windows 本地 Python 3.12.10 / uv 0.10.12，pytest 93 passed + 86 subtests、uv 环境 unittest 93 项通过，Ruff、数据校验与 66 个跟踪文件的敏感文件扫描通过。联网脚本实算 7 个文件指纹均匹配。[Linux CI #39892392668](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/39892392668) 在提交 `36ef2cd` 上用固定 digest 完成三服务启动、mapping 正反例、保留卷重建后的记录回读与测试卷清理，任务耗时 1 分 32 秒。

更新任一版本时，在新分支核验上游文件，更新清单和实际使用处，运行测试并在 PR 记录原因与证据。新增运行依赖时先验证安装/调用，再更新 `pyproject.toml` 与 `uv.lock`；完整推理/解析环境必须包含传递依赖与模型工件版本。本清单不提交 wheel、权重、第三方 PDF、数据库卷或索引。
