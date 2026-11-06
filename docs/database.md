# PostgreSQL 业务表与迁移（M1-17）

PostgreSQL 保存来源、证据元数据、历史事件与任务记录，不承担向量检索。M1-17 提供七表结构、环境变量连接和 Alembic 迁移；M1-18 提供独立的幂等导入入口和业务事务回滚。诊断 API 仍待实现，迁移本身不会自动读取或导入 PDF、corpus、评测标签或审核资料。

## 安装与运行

`uv.lock` 锁定 Alembic 1.20.1、SQLAlchemy 2.1.6 和 psycopg / psycopg-binary 3.3.7；Alembic wheel 指纹与 M1-06 的 `versions.lock.json` 一致。使用项目已有 PostgreSQL 16.4-alpine 固定镜像。模型推理不参与数据库迁移。

```bash
uv sync --frozen

# 无数据库、无凭据也能生成 PostgreSQL SQL；不会连接服务或修改数据
uv run --frozen alembic upgrade head --sql
uv run --frozen alembic downgrade 0001:base --sql

# 先按本地服务说明启动 PostgreSQL；.env 中填写实际连接信息
uv run --frozen --env-file .env alembic upgrade head
uv run --frozen --env-file .env alembic current
uv run --frozen --env-file .env alembic check
```

命令在仓库根目录执行。`app/db/connection.py` 沿用 `Settings`，要求非空 `POSTGRES_PASSWORD`；host、port、db、user 沿用已有默认值与环境变量。模块自身不读取 `.env`，上面的 `uv --env-file` 是调用者显式加载方式。`URL.create` 保留密码中特殊字符，URL 常规显示隐藏密码；engine 隐藏 SQL 绑定参数、启用连接检查，连接超时为 10 秒。不打印完整连接串或调用 URL 的明文密码渲染方法。配置依据 [SQLAlchemy 连接说明](https://docs.sqlalchemy.org/en/21/core/engines.html)。

首次 `upgrade head` 建立七表和 `alembic_version`，再次执行不会重建或清空记录。首个迁移为 `0001`，位于 `migrations/versions/0001_initial_schema.py`；该文件冻结 DDL，不导入会继续演进的应用 schema。`app/db/schema.py` 是当前 SQLAlchemy Core 元数据，供应用访问和 `alembic check` 比对。后续字段变动应新增迁移，不改写已发布的 `0001`。流程依据 [Alembic 官方教程](https://alembic.sqlalchemy.org/en/latest/tutorial.html)。

`alembic downgrade base` 会删除本项七表及其中数据，仅对明确可丢弃的一次性测试库执行；本项目不会对现有本地库自动降级。PostgreSQL 的事务 DDL 用于单次迁移，不能代替 M1-18 的业务导入事务。

## 七表及身份

| 表 | 主键 | 保存内容与关系 |
| --- | --- | --- |
| `document` | `document_key` | 来源 ID、文档编号、修订、完整 PDF SHA-256、型号数组、固件适用范围、来源 URL、访问日期和来源元数据快照。 |
| `chunk` | `(document_key, evidence_id)` | 文本、块类型、物理定位器、全部页码、章节/原始引用、表行、故障码及安全标签；外键关联父文档与同一父文档的 `ingest_run`。 |
| `asset` | `asset_id` | 设备实例、型号、显式 `synthetic`；不把设备实例当成型号，也不把某次固件版本写成永久设备属性。 |
| `work_order` | `work_order_id` | 已关闭历史工单的设备、型号、合成标识、事件组、当时固件、原始告警码、时间、观察、历史确认原因、动作、结果、文本与定位。 |
| `alarm` | `alarm_id` | 事件时间、可用时间、设备、型号、合成标识、事件组、当时固件、原始码值、文本与定位；工单关联可为 SQL `NULL`。 |
| `ingest_run` | `ingest_run_id`（UUID） | 输入路径与完整字节 SHA-256、解析配置、任务状态、起止时间和错误分类；父文档可为空，以记录尚未建立文档时的失败。 |
| `diagnosis_run` | `diagnosis_id`（UUID） | 可选设备、型号/固件、`as_of`、请求、响应、运行配置、任务状态、诊断状态、起止时间和错误分类；此表存在不代表诊断功能已实现。 |

文档主键由来源 ID、修订和摘要构成，数据库检查三者与主键一致，并约束 `(source_id, revision)` 唯一。不同修订允许相同 PDF 字节并存；因此不对 `sha256` 或 `evidence_id` 单独施加全局唯一约束。块在同一父文档中不可重复，同一物理证据在另一修订下可独立保存。M1-18 在这些约束上执行下述事务导入。

每块必须关联同一文档的导入记录，通过该记录回查输入快照路径/指纹与解析配置。`source_refs`、`heading_refs`、`table_row.table_ref` 等仅对那个固定快照有效；它们不是永久 ID。`evidence_locator` 可直接回到原 PDF 物理位置。外键采用默认的阻止悬空引用行为，不自动级联删除证据或审计记录。

`work_order` 的 `(asset_id, model, synthetic)` 必须与设备表一致；已关联工单的告警，其设备、型号、合成标识、事件组也必须与工单一致。未关联工单的告警仍必须指向一致的设备。固件未知保留 SQL `NULL`，不填造版本；文档 `firmware_scope=NULL` 仍按现有规范表示不按固件限定，不能与事件中的未知固件混淆。

## 约束与尚需应用校验的范围

- 时间使用带时区类型：工单 `opened_at <= closed_at <= available_at`，告警 `occurred_at <= available_at`。这些是同一行约束；M1-18 的种子导入另外校验告警处于工单窗口内、关联固件一致，以及现有种子规范的「关闭/发生时可用」等式。
- 结构字段使用 JSONB 并校验对象/数组外形，必要页码和原始引用数组不能为空。`table_row`、响应等可空字段使用 SQL `NULL`；`JSON null` 不冒充对象。
- `run_status` 为 `running` / `succeeded` / `failed`：运行中无结束时间，终态必须有不早于开始的结束时间。诊断完成时还需非空响应和 `supported` / `insufficient` / `out_of_scope` 状态；其他任务状态不能带最终响应。
- `runtime_config` 预留保存实际模型、语料、索引、代码、提示词和检索配置的对象，当前不制造这些运行值。`error_code` 保存错误分类，不存凭据或原始 traceback。
- SQL 约束不回算证据 SHA、不打开 PDF、不证明中文语义或合成身份真实，也不逐个验证 JSON 数组元素。物理定位、完整来源映射、内容校验与导入路径隔离仍由相应应用入口负责；数据库表存在不会放宽检索 allowlist。

约束与可空外键行为依据 [PostgreSQL 16 约束说明](https://www.postgresql.org/docs/16/ddl-constraints.html)。跨表规则不能伪装成只检查当前行的 `CHECK`。

## 验证

```bash
# 离线契约，无数据库也可执行
uv run --frozen python -m unittest discover -s tests -p test_db_schema.py -v
```

`tests/test_db_postgres.py` 只在显式设置 `FORGERCA_TEST_POSTGRES=1` 时运行，并要求数据库名为 `forgerca_test` 且初始没有业务表；它会执行降级和清空测试表，不能指向保留数据的数据库。测试覆盖真实七表、合成记录往返、跨修订 ID、重复升级保留数据、错误关联/JSON/时间拒绝、降级及再次升级；使用 `alembic check` 比对实际 schema。

`.github/workflows/postgres.yml` 创建无持久化挂载的独立 PostgreSQL 容器，使用已固定镜像、随机临时密码和回环端口，执行上述集成测试后删除该容器及其匿名测试卷。测试只使用自造记录。

2026-11-06 的 [Linux PostgreSQL CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/42207835074) 实测 7 项测试全部通过；升级、重复升级保留数据、错误关联/时间/JSON 拒绝、降级及重建均通过，三次 `alembic check` 未发现结构漂移。本地锁定环境 pytest 为 248 passed、1 skipped、430 subtests passed；系统 Python unittest 为 245 项、14 项跳过，Ruff、数据与敏感文件检查通过。本机 Docker Engine 当前不可用，Windows 的真实数据库运行验收尚未完成。

## 幂等导入（M1-18）

```bash
# 先完成上文的 upgrade head，再显式导入一个解析快照
uv run --frozen --env-file .env python -m scripts.ingest --snapshot data/processed/<snapshot>.json
# 等价的 just 入口；文件名含空格时用引号包住路径
uv run --frozen --env-file .env just ingest data/processed/<snapshot>.json

# 只读取现有白名单的 work_orders.jsonl / alarms.jsonl
uv run --frozen --env-file .env python -m scripts.ingest --seed-events
```

导入不运行模型，不自动启动服务或迁移；缺少路径/模式时失败。CLI 先完成本地输入验证再创建数据库连接，数据库异常只输出不含行内容或连接串的简短失败信息。

**PDF 快照**：只接受显式指定的 `data/processed/` 内 JSON，不扫描目录。先检查完整页范围、解析配置、父文档与证据 ID，再与当前来源清单逐字段对齐、校验本地原 PDF 指纹；用现有切块/物理定位/展示定位代码重建每块，拒绝文本、标签、定位和原始引用与快照不一致的输入。旧版本缺字段或旧切块规则产生的快照需重新解析。不把原 PDF 验证描述为语义审核通过。

- `document.sha256` 是 PDF 字节摘要；`ingest_run.input_sha256` 是本次 JSON 输入文件的完整字节摘要。相同父文档、相同输入摘要重跑时复用成功运行，文档/块/运行数均不增加；文件改名不改变该判断。
- 相同 PDF 可追加尚未导入的页；重复块保持原来的导入来源。不同 JSON 字节（例如格式化不同）可留下新的成功运行记录，但不会重复业务块。
- 相同文档身份下来源元数据变化、相同证据 ID 下内容/引用变化，以及在已导入页上产生新的块 ID，均拒绝整批导入。这里不执行重解析替换、删除或跨页重新分组；这些更新策略留待 M1-24。
- 修订升级使用新的 `document_key`，旧文档与块继续保留。同一来源/修订换了 PDF 字节会触发冲突。当前 manifest 内依然拒绝重复摘要；集成测试用先后登记的两个修订验证数据库并存，不放宽清单规则。
- 在一个事务里插入文档、运行及全部块，成功后更新运行状态；任何异常都回滚该事务，包括运行记录。不会留下半批块，也不在回滚后额外保存失败审计行。
- 插入文档后以父文档行锁串行化同文档写入，并在锁内检查已成功的输入，避免两个同时启动的导入各建一条运行。依赖 PostgreSQL 默认 `READ COMMITTED`、[行锁](https://www.postgresql.org/docs/16/explicit-locking.html#LOCKING-ROWS) 与 [ON CONFLICT](https://docs.sqlalchemy.org/en/21/dialects/postgresql.html#insert-on-conflict-upsert)；未提供跨数据库后端兼容层。

**合成历史**：只读取两个固定白名单文件，使用与离线校验器相同的 `validate_seed_events`。设备、型号、合成标识、事件组、原始码值、固件与时间窗口必须一致；未知固件保留 `NULL`。资产、工单和告警按固定顺序在一个事务中插入，同身份且全字段相同则复用，冲突则整批回滚。此入口仍要求 `synthetic=true`，不能用来登记真实现场历史；文件定位器保留，未伪造运行审计或领域审核签署。

`knowledge.jsonl` 是项目知识注释，不导入为厂商 `document/chunk`。导入器不调用会读取评测/参考图的 `load_data()`；不读取 `data/evaluation/`、`data/graph/`、审核资料，也不改变检索 allowlist。原 PDF 和解析快照仍留在忽略目录，数据库不会保存原 PDF 文件。

本地已核验硬件手册第 152 页的 M1-16 快照（1 块、`warning` 标签）以及现有 8 条工单和 16 条告警的导入准备；这不是本机数据库写入验收。真实事务、并发重跑及中途故障回滚由独立 Linux PostgreSQL CI 验证，结果在 PR 完成后记录。
