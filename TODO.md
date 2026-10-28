# ForgeRCA · Engineering TODO / Roadmap

> **版本**：v0.5.7（2026-10-28） · **当前**：M0 的工程项与数据项均已完成——仓库基线、分支保护、CI 三门禁、安全文档在 v0.4.1 收口；M0-17～M0-22 于 v0.5.0 完成并留下实测证据。**M0 仍未整体收口**：唯一剩余项是 **M0-06 人工领域复核**，按其定义不能由 AI 代劳，`docs/reviews/seed-v0.2-human-review.md` 的审核人、日期与决策仍待填写。**M1 已启动**，M1-01～09 的底座、命令入口、版本清单、PDF 页范围解析、文档主键与故障表主码规范化完成（容器运行验收在 Linux CI，真实解析本地抽查 4 页），下一项为 M1-10 章节与故障表行切块；入库与向量模型推理仍待实现。
> **首期设备**：ABB ACS580-01（沿用仓库现有来源清单和数据协议）；后续多品牌扩展单独列入 Backlog。  
> 本清单是**工作计划，不代表实际已完成**。以下默认任务未勾选；可在 GitHub PR 验收后逐项勾选。

## 使用约定

- **优先级**：`P0` 阻塞端到端功能 / 正确性，`P1` 必做的健壮性与评测，`P2` 体验及可扩展性。
- **任务 ID**：`M1-01` 等，用作 Issue / PR 标题；建议 label：`area:data`, `area:retrieval`, `area:graph`, `area:agent`, `area:eval`, `priority:P0`。
- **DoD / 验收**：每个里程碑完成须提供 *可运行命令、测试证据、输入输出样本和风险说明*；仅添加代码文件不算完成。
- **禁止事项**：禁止将 `data/evaluation/*` 用于在线索引或训练；禁止将厂商原文 PDF 上传公开仓库；未审核的合成工单不能被写成真实历史数据。

## 当前里程碑一览

| 里程碑 | 目标 | 依赖 | 当前状态 |
| --- | --- | --- | --- |
| **M0** | 数据/文档/安全基线 | 无 | 工程与数据项已完成（22/23）；仅 M0-06 人工领域复核待签署 |
| **M1** | 基础 Dense RAG 与可信引用 | M0 | 进行中（M1-01～09 底座、版本清单、PDF 解析、文档主键与故障表主码规范化完成） |
| **M2** | 混合检索 + 版本过滤 + Reranker | M1 | 未开始 |
| **M3** | 证据约束的 Neo4j GraphRAG | M1/M2 | 未开始 |
| **M4** | LangGraph 动态补检与 Langfuse | M2/M3 | 未开始 |
| **M5** | 盲测、消融、部署与展示 | M1–M4 | 未开始 |

---

## M0｜仓库与数据基线（**优先先做完**）

### M0-A · GitHub 工程准备

- [x] **M0-01 · P0** 仓库名称维持 `ForgeRCA-`（末尾连字符保留），不改名；clone、CI、Issue 与徽章 URL 保持现状。*(2026-10-13 决定)*
- [x] **M0-02 · P0** 已选定 **Apache-2.0**，添加根目录 `LICENSE`（版权行 `Copyright 2026 abelferry-cloud`）；README 与 CONTRIBUTING 均声明**第三方数据不受项目许可证覆盖**。*(2026-10-13)*
- [x] **M0-03 · P0** 审核当前 `data/sources/manifest.json` 的 ABB 文档编号、修订、SHA-256、页码与可访问链接。*([PR #3](https://github.com/abelferry-cloud/ForgeRCA-/pull/3) 已合并)*
- [x] **M0-04 · P0** 在本地运行 `python scripts/validate_data.py`，保存失败信息、修复数据关联问题。*(PR #3 已记录通过)*
- [x] **M0-05 · P0** 在本地运行 `python -m unittest discover -s tests -v`，记录 Python 版本和测试摘要。*(PR #3 已记录通过)*
- [ ] **M0-06 · P0** 对 9 条知识注释、8 条合成工单及 5 条 demo 场景进行至少一次人工领域核对；记录审核人、日期、变更。*([待填写的逐条审核清单](docs/reviews/seed-v0.2-human-review.md) 已备好)*
- [x] **M0-07 · P1** GitHub 仓库 About、topics、description、homepage 与 Issue / PR 模板完善。*(2026-10-13 已设 description 与 10 个 topics，新增 `.github/pull_request_template.md` 与 `.github/ISSUE_TEMPLATE/config.yml`；**homepage 留空**——尚无演示站点，不指向不存在的页面，待 M5-18/19 产出后再填)*
- [x] **M0-08 · P1** 确认 CI 在 PR 与默认分支运行：离线数据校验、unittest、敏感文件扫描。*(2026-10-13 新增 `scripts/check_sensitive_files.py` 并接入 `.github/workflows/validate.yml`；触发条件为 `push` 与 `pull_request`，覆盖 `main` 与 PR)*
- [x] **M0-09 · P1** 已确立分支管理：`main` 为唯一稳定主线并设为默认分支；**禁止直接向 `main` 提交**，改动一律从 `main` 切出功能分支走 PR，仅错别字、失效链接等极小改动或经维护者明确允许可直接提交。命名前缀 `feat/` `fix/` `docs/` `chore/` `data/`，建议携带任务 ID。详见 `CONTRIBUTING.md`《分支与合并规范》。*(2026-10-13)*
- [x] **M0-10 · P1** 建立 `.env.example`（只提供非机密参数名），核实 `.gitignore` 忽略 `.env`、密钥、数据库卷和原始 PDF。*(2026-10-13 新增根目录 `.env.example`，只含参数名与空值；`.gitignore` 补充密钥材料（`.pem`/`.key`/`.p12`/`secrets/`…）与数据库卷（`docker/volumes/`/`postgres-data/`/`*.sqlite`…）；忽略规则本身由 `scripts/check_sensitive_files.py` 的回归检查守护)*
- [x] **M0-11 · P1** 新增 `SECURITY.md`（漏洞报告路径与安全边界），定义数据泄漏排查流程。*(2026-10-13 新增根目录 `SECURITY.md`；上报走 GitHub 私有漏洞通道，定义 5 类安全问题、明确的非范围项，以及「先轮换凭据、再清理历史、最后补门禁」的 6 步处置流程)*
- [x] **M0-12 · P2** 选择 Python 包管理方案（uv / pip），首次添加依赖时生成可复现的锁文件，不提前虚构已装依赖。*(2026-10-13 选定 `uv`，依据与边界记入 `CONTRIBUTING.md`《Python 环境与包管理》；**当前无第三方依赖故无锁文件**，`uv.lock` 与 `pyproject.toml` 待 M1-01 引入首个依赖时生成——该待办仍属 M1-01，不在本项内)*

### M0-B · 公开数据与来源管理

- [x] **M0-13 · P0** 将 ABB 官方固件和硬件 PDF 下载到 `data/raw/abb/`，运行 `--check-raw` 校验大小、PDF 文件头和 SHA-256；使用 PDF 工具独立核验实际页数。*(PR #3 已合并)*
- [x] **M0-14 · P0** 对设备型号、固件版本、文档修订定义三套独立字段；补全 `firmware_scope` 适用性逻辑和“未知”分支。*([PR #5](https://github.com/abelferry-cloud/ForgeRCA-/pull/5) 已合并：来源清单升为 schema 0.2 并新增已核验 `models`；校验器区分“明确不匹配 / 未知 / 明确不按固件限定”三态，未知固件只允许用于 `insufficient` 场景的限制说明，明确不匹配一律拒绝；固件字段格式受 `ASCKX x.y` 约束)*
- [x] **M0-15 · P0** 为每个注释确认 `source_id + pdf_page + locator` 可指向指定 PDF 的实际信息，修复不可追溯项。*([PR #5](https://github.com/abelferry-cloud/ForgeRCA-/pull/5) 已合并：`validate_data.py` 强制 `source_id` 必须存在、`pdf_page` 落在来源总页数内**且属于 `manifest.json` 的 `verified_pdf_pages` 白名单**、`printed_page`/`section` 非空。**边界**：以上只证明锚点在结构上可解析到已核验页面；“该页内容确实支持这条注释”属语义判断，仍在 M0-06 人工复核范围内，未在此项宣称完成)*
- [x] **M0-16 · P0** 在 `data/raw/` 与 `data/processed/` 保持原始数据不入 Git；记录来源许可证与归属。*(2026-10-13 核实：二者均在 `.gitignore` 中，且由 `scripts/check_sensitive_files.py` 的忽略规则回归检查持续守护——本地已下载的两份 PDF 不入库；来源许可与归属记录在 [来源说明](data/sources/README.md)《发布边界》（`redistribution=not_verified`）与 README《许可、来源与安全边界》)*
- [x] **M0-17 · P1** 验证可选下载脚本：`python scripts/download_public_data.py --list` / `--dataset maintie-gold`；下载失败须输出清楚的错误。*(2026-10-19 实测：`--list` 离线执行、返回 0 且不发起网络请求；`--dataset maintie-gold` 成功写入 `data/raw/public/maintie-gold/`（817,880 字节，SHA-256 `ef811cf4…d7d6e0`）。失败路径覆盖非白名单 URL、超体积、损坏响应与哈希不符，错误以 `Download/validation failed: …` 输出到 stderr 并返回 1，见 `tests/test_download_public_data.py`)*
- [x] **M0-18 · P1** 下载 MaintIE gold 后验证 JSON 的 tokens/entities/relations，作为**独立**信息抽取数据集。*(2026-10-19 实测：1,076 条记录、3,397 实体、2,341 关系、155 类层级实体、6 类关系；实体 `start/end` 为 token 下标且全部通过越界检查，按 token 复原的片段与原文一致；**关系的 `head`/`tail` 是 `entities` 数组下标而非 token 偏移**，该结论已写入 [公开数据指引](docs/public-datasets.md)，供 M3-12 使用。数据仍属独立数据集，未混入 ABB 语料)*
- [x] **M0-19 · P1** 下载 AI4I 后确认是合成的预测性维护表格数据，仅用于扩展情境，不赋予 ABB 工单 ID。*(2026-10-19 实测：10,000 行 × 14 列，`UDI` 为 1–10,000 连续唯一整数，`Machine failure=1` 339 行（TWF 46 / HDF 115 / PWF 95 / OSF 98 / RNF 19）；无 `WO`、`ABB` 或任何工单编号字段；上游声明为合成数据，本项目未为其生成 ABB 工单 ID，也未映射到 ABB 故障码)*
- [x] **M0-20 · P1** 编写第三方数据署名、版本、URL、下载时间、SHA-256、用途和禁止混用说明。*(2026-10-19：`data/sources/public-datasets.json` 升至 schema 2，为两份已下载数据写入机器可读 `verified_snapshot`（URL、下载 UTC 时间、归档/处理后 SHA-256、字节数、记录数）；[公开数据指引](docs/public-datasets.md) 增加实测结果、数据卡与「绝对不要」混用清单。快照代表一次具体核验，不是上游永久 pin，更新时新增条目而不覆盖)*
- [x] **M0-21 · P1** 确保 `data/evaluation/` 永不被数据构建器递归扫描；设置显式 allowlist 测试。*(2026-10-19：新增 `scripts/corpus_allowlist.py` 作为唯一索引入口——`indexable_files()` 只返回 3 个显式列出的语料文件、不做目录扫描，`assert_indexable()` 拒绝 `data/evaluation/`、`data/graph/`、`docs/reviews/`、`data/raw/` 等前缀以及 `..` 路径穿越；`tests/test_corpus_isolation.py` 提供 7 项守护，其中一项实证 `rglob("*.jsonl")` 会扫到 dev/demo 标签，另一项锁定 `validate_data.py` 的 `CORPUS_FILES` 不得与该 allowlist 漂移)*
- [x] **M0-22 · P2** 制定数据卡模板：来源、字段、规模、合成标记、授权、已知偏差、标注状态、预处理版本。*(2026-10-19：新增 [数据卡模板](docs/data-card-template.md)，含 10 个必填小节与完成检查清单，并要求写清「是否进入检索索引」与 allowlist 登记；MaintIE gold、AI4I 两张卡已按模板填写在 [公开数据指引](docs/public-datasets.md)，种子语料沿用既有 [数据卡](data/README.md))*
- [x] **M0-23 · P1** 在 GitHub Settings → Branches 为 `main` 启用分支保护规则：禁止直接推送、要求经 PR 合并、要求 CI 检查通过。*(2026-10-13 已启用：要求经 PR 合并（批准数 0，适配单人维护）、必需状态检查 `validate`、禁止强推与分支删除、要求解决会话；`enforce_admins=false` 保留维护者的紧急通道，与 CONTRIBUTING 的例外条款一致。未开启 `strict`（不强制分支先同步 main），如需收紧可在仓库设置中打开)*

2026-10-13 本地执行记录：M0-03、M0-04、M0-05、M0-13 的来源核验与测试结果见 [ABB PDF 核验记录](data/sources/verification-2026-10-13.md)，已随 PR #3 合并。M0-14、M0-15 的校验规则与逐条定位见 [数据规范](docs/data-spec.md) 和 [审核清单](docs/reviews/seed-v0.2-human-review.md)，已随 PR #5 合并并在 v0.4.1 核实后勾选。M0-16 于 v0.4.1 核实勾选。

2026-10-19 本地执行记录：M0-17～M0-22 完成。公开数据的下载命令、文件大小、完整 SHA-256、结构校验结论与数据卡见 [公开数据指引](docs/public-datasets.md)，机器可读快照见 [公开数据清单](data/sources/public-datasets.json)；索引隔离入口为 `scripts/corpus_allowlist.py`，守护测试为 `tests/test_corpus_isolation.py`。**M0-06 人工领域复核仍未完成**，它是 M0 唯一未勾选项。

**M0 DoD**：新贡献者按 README 的现有命令可完成校验；每条种子事实都能追到真实页码或明确的合成记录；未来的第三方数据和盲测答案没有混入主语料；所有改动均经功能分支与 PR 进入 `main`，`main` 历史保持可校验。

---

## M1｜PDF → Evidence Store → Dense-only RAG

### M1-A · 系统底座

- [x] **M1-01 · P0** 建立 `pyproject.toml`、开发/生产依赖分组、Python 最低版本和 Ruff / pytest 配置。*(2026-10-19：`pyproject.toml` 声明 `requires-python >=3.11`、运行时 `dependencies = []`（仍只用标准库）、`[dependency-groups] dev = pytest + ruff`、`[tool.uv] package = false`；Ruff `target-version=py311`、`line-length=120`、规则集 `E,F,W,I,B,UP`；pytest `testpaths=tests`、`pythonpath=["."]`（沿用 `scripts.*` 导入方式）。`uv.lock` 已提交（pytest 9.1.1 / ruff 0.17.1），`uv sync --frozen` 通过。实测：`uv run ruff check .` 无告警（含对既有 16 处超长行的折行）、`uv run pytest` 62 passed + 41 subtests。**CI 接入 lint 属 M5-14，本项未声称完成**)*
- [x] **M1-02 · P0** 建立 `app/` 分层：`ingestion/`, `retrieval/`, `db/`, `api/`, `schemas/`；保持路由不直接处理业务。*(2026-10-19：五个包已建立，`app/__init__.py` 写明依赖方向（任何层不得导入 `app.api`，`schemas` 不依赖其他层）。新增 `tests/test_app_layers.py` 作为 ratchet：用 AST 检查禁止方向（含相对导入解析）、要求 `__init__.py` 存在、并验证各层可导入。当前各层只有职责说明，业务代码按 M1-07 起逐层填充；「路由保持薄」是评审约定，当前没有路由可测)*
- [x] **M1-03 · P0** 建立配置模块：环境变量、类型检查、缺少必填项时失败、日志中的密钥脱敏。*(2026-10-19：`app/config.py` 提供 `Settings.from_env(env=..., required=(...))`、`Secret` 与 `Settings.redacted()`。端口逐项解析并校验 1–65535，错误只报变量名、不回显原值；必填变量缺失或为空白时一次性列出全部缺失项；`Secret` 的 `repr`/`str` 恒为 `Secret(***)`，`redacted()` 把已配置密钥显示为 `***`、未配置显示为 `None`，便于区分「没配」和「配了」。14 个测试覆盖默认值与 `.env.example` 双向漂移、类型与范围、缺失必填、密钥不外泄。当前无服务读取配置，实际接入在 M1-17/M1-19)*
- [x] **M1-04 · P0** 本地 Docker Compose 提供 PostgreSQL / OpenSearch / Neo4j；健康检查和端口可配置。*(2026-10-22：`compose.yaml` 提供回环绑定、四个可配置端口、必填凭据与命名数据卷；4 项配置边界测试通过。[Linux CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/39783749818) 实测三服务全部 healthy，写入后重建容器、回读记录通过。本机 Docker Desktop 启动失败，Windows 运行时验收仍待完成；详见 [本地服务说明](docs/local-services.md)。不代表业务表、索引或图谱已实现)*
- [x] **M1-05 · P1** 增加 `Makefile` / `justfile`：`lint`, `test`, `data-check`, `up`, `down`, `ingest`；只有实测能运行后再在 README 展示。*(2026-10-22：`justfile` 提供六个入口，`rust-just==1.58.0` 仅列入开发依赖并锁定；Windows 实测 lint / data-check 通过，test 为 88 passed + 83 subtests。4 项行为测试覆盖默认只列命令、含空格路径与子目录执行、失败即停止、ingest 明确返回非零；[Linux CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/39795723492) 通过新 up/down 入口完成三服务健康检查与重建后记录回读。README 已记录实测命令。**这里只完成入口；实际 ingest 仍待 M1-07～18**)*
- [x] **M1-06 · P1** 版本锁定：Docling、向量模型、OpenSearch mapping、DB migration 工具；提交可重现版本清单。*(2026-10-23：[版本清单](docs/version-lock.md) 固定 Docling / Docling Slim 2.142.0、Alembic 1.20.1 的发布文件指纹，BGE-M3 完整 revision 与配置指纹，`dense-v1` mapping 字节哈希及三服务镜像 digest。7 个上游工件实算 SHA-256 匹配；本地 pytest 93 passed + 86 subtests、unittest 93 项及 Ruff / 数据 / 敏感文件检查通过。[Linux CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/39892392668) 通过固定镜像启动、卷保留回读和 mapping 正反例。**这里只锁定工件身份；完整运行依赖、解析模型资产、业务迁移/索引和 embedding 推理配置仍在后续对应任务实现和验收**)*

### M1-B · 文档解析与证据锚点

- [x] **M1-07 · P0** 选择 PDF 解析器（优先 Docling），保留标题、段落、表格、页码和页内顺序。*(2026-10-23：[PR #16](https://github.com/abelferry-cloud/ForgeRCA-/pull/16) 引入 Docling 2.142.0 与锁定的 CPU 依赖、布局/表格模型；按来源 ID 校验原文指纹并解析物理页范围，输出保留原生阅读树、表格跨度与完整 provenance。11 项专项测试及本地全量 unittest 104 项通过，pytest 104 passed + 97 subtests、Ruff / 数据 / 敏感文件检查通过；[Linux Python 3.11 CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/39929017180) 安装锁定依赖并通过 11 项离线契约测试。固件手册 536–538 页、硬件手册 152 页已在本地离线推理并对照渲染检查结构，详情见 [PDF 解析说明](docs/pdf-parsing.md)。**仅验收 4 个原生文字层样本页，OCR 关闭；未完成全量质量评测、人工领域复核、切块或入库**)*
- [x] **M1-08 · P0** 建立文档主键：`source_id`、文档编号、修订、固件适用性、文件 SHA-256 与下载来源。*(2026-10-28：`app/schemas/document.py` 按 `source_id@revision:sha256` 生成完整摘要主键，校验文档元数据并拒绝清单冲突；PDF 解析结果新增文档主键、编号、修订、固件范围、来源 URL 与访问日期，保留原有 `source_id` / `sha256`。18 项主键专项测试、14 项解析契约测试通过；锁定环境全量 pytest 为 128 passed + 176 subtests，系统 Python unittest 为 124 项、5 个跳过记录（4 项 Docling 测试及缺少 just 的测试类），Ruff 与数据/原 PDF 指纹校验通过。字段与兼容性见 [数据规范](docs/data-spec.md#文档身份m1-08) 和 [解析说明](docs/pdf-parsing.md)。**没有新增依赖；Chunk 证据 ID、数据库导入仍分别属于 M1-11、M1-18**)*
- [x] **M1-09 · P0** 识别故障码模式并保留原始码值 / 规范化码值，避免将前导零、字母或大小写损坏。*(2026-10-28：[Issue #18](https://github.com/abelferry-cloud/ForgeRCA-/issues/18)；新增标准库码值契约与故障表编码列识别器，解析输出保留 `raw_code` / `normalized_code` 和本次解析内的 `cell_ref`。仅接受四位 ASCII 十六进制字符串，去首尾空白并统一大写，不做数值转换；辅助码列、正文及无表头续表不扫描。11 项专项测试及 CLI 集成回归通过，全量 pytest 140 passed + 216 subtests，系统 Python unittest 136 项、5 个跳过记录；Ruff 与数据校验通过。本地固件手册 536–538 页的 18 个主码及引用已核对，含字母的 `42F1` 保留，辅助码未混入。规则与限制见 [数据规范](docs/data-spec.md#故障码原值与规范化值m1-09)。**不代表全量手册覆盖或代码有效性字典；断行修复、查询侧全半角匹配和永久证据 ID 仍待后续任务**)*
- [ ] **M1-10 · P0** 按章节和故障表行进行切分，原因与措施尽量保持在同一语义单元。
- [ ] **M1-11 · P0** 为 Chunk 生成稳定证据 ID（基于 `source_id + sha256 + page + locator`），不得用排序索引。
- [ ] **M1-12 · P0** 保留 `pdf_page`、`printed_page`、`section`、`table_row` 和父文档映射；允许跨页片段。
- [ ] **M1-13 · P0** 加入解析质量测试：中文乱码、空页、表格错行、跨页单元格、故障码断行与缺页。
- [ ] **M1-14 · P1** 记录解析器版本和参数；同一原文重新解析时能识别增量变更。
- [ ] **M1-15 · P1** 采样人工核对 ≥ 30 个证据锚点（不是最终 200 条诊断样本）。
- [ ] **M1-16 · P1** 处理 PDF 中的警告 / 注意 / 危险标签，不把安全指令与条件脱离上下文。

### M1-C · PostgreSQL / Dense 基线

- [ ] **M1-17 · P0** PostgreSQL 建表与迁移：document、chunk、asset、work_order、alarm、ingest_run、diagnosis_run。
- [ ] **M1-18 · P0** 实现幂等导入：同 SHA 不重复，修订升级并行存储，导入异常可以回滚。
- [ ] **M1-19 · P0** OpenSearch 配置 embedding 字段、精确 keyword 字段和 `model / revision / firmware` 元数据。
- [ ] **M1-20 · P0** 选择初始 embedding 模型并固化完整名称、维度、归一化策略；记录计算批大小。
- [ ] **M1-21 · P0** Dense-only Retriever：查询向量化、Top-k、metadata filter、证据 ID 去重。
- [ ] **M1-22 · P0** 从 Retriever 结果回查原始引用来源并验证文档版本，输出 `evidence_id + locator`。
- [ ] **M1-23 · P0** 实现第一版受约束生成：只根据返回证据解释候选原因，没有证据则 `insufficient`。
- [ ] **M1-24 · P1** 为检索、索引增量更新、失败回滚与文档删除添加单元/集成测试。
- [ ] **M1-25 · P1** 确认任何 eval gold label、`reference.json` 不进入向量索引。
- [ ] **M1-26 · P1** 导出逐题 `retrieved_ids`, `rank`, `score`, `citations` 作为 Dense-only 基线产物。

**M1 DoD**：对至少一条 ABB 手册诊断问题，Retriever 能输出真实证据、对应 PDF 页码和有效适用性；数据导入重复执行不产生重复证据。

---

## M2｜混合检索、适用性与精排

### M2-A · BM25 + Dense + RRF

- [ ] **M2-01 · P0** OpenSearch 为中英术语、型号和故障码设计可测试的字段映射（keyword 与 text 分离）。
- [ ] **M2-02 · P0** 实现 BM25 Retriever，默认初始候选数按实验配置，记录每条命中及来源排名。
- [ ] **M2-03 · P0** 明确故障码精确匹配规范：全半角、大小写、空格；不能盲目删除区分语义的前导零。
- [ ] **M2-04 · P0** BM25 与 Dense 采用相同设备适用性过滤，错误型号候选必须在精排前被剔除。
- [ ] **M2-05 · P0** 实现 RRF，`k=60` 作为可配置初始值；按稳定证据 ID 去重。
- [ ] **M2-06 · P0** 避免单路内同一个证据多次计分，记录各路 rank、RRF 总分和融合排名。
- [ ] **M2-07 · P0** 加入 BGE-Reranker-v2-m3（或复核选择后同等级模型），批量重排结果并保留原始分数。
- [ ] **M2-08 · P0** 实现型号/手册修订/固件范围三级策略：不适用→排除，未知→标注不确定，不凭“最新”强行替换。
- [ ] **M2-09 · P0** 设置适用性对照表，至少包含同码异型号干扰和同型号不同文档修订场景。
- [ ] **M2-10 · P0** 候选过长时进行层级去重与证据片段压缩，不能截断引用的关键限定语。
- [ ] **M2-11 · P1** 记录 BM25、Dense、融合、精排四个阶段的 Top-k 命中与时延。
- [ ] **M2-12 · P1** 设计查询扩展：故障码、设备别名、部件名、现象同义词；避免搜索其他型号事实。
- [ ] **M2-13 · P1** 增加空结果、模型下线、OpenSearch 超时和单路降级策略。
- [ ] **M2-14 · P1** 性能剖析：召回数、rerank batch、P50/P95 及向量维度对成本的影响。

### M2-B · 检索消融与基线验证

- [ ] **M2-15 · P0** 统一检索评测文件格式、问题、gold evidence anchor、适用设备和 cut-off 时间。
- [ ] **M2-16 · P0** 定义 Evidence Recall@5 和 MRR@10（包括多证据 gold 的匹配规则）。
- [ ] **M2-17 · P0** 实验 B0（Dense）、B1（BM25 + Dense + RRF）、B2（B1 + Reranker），固定其他条件。
- [ ] **M2-18 · P0** 核实每组使用同一版本语料、同一 dev 问题集，避免索引泄漏和参数偏差。
- [ ] **M2-19 · P1** 输出 `artifacts/retrieval_ablation.csv` 与错误分析样例，展示具体故障码排名变化。
- [ ] **M2-20 · P1** 保留没有提升的案例与失败原因，不强行报告预设的 89%。

**M2 DoD**：一份逐题消融结果能证明召回策略差异；异型号证据不进入最后 Top-k；每条结果可溯源。

---

## M3｜Neo4j Knowledge Graph / GraphRAG

### M3-A · 故障本体和图谱构建

- [ ] **M3-01 · P0** 固定本体版本：Equipment、Component、FaultCode、Symptom、RootCause、Action、Document、Evidence、WorkOrder。
- [ ] **M3-02 · P0** 定义 `MAY_BE_CAUSED_BY` 与 `CONFIRMED_CAUSE` 的语义边界，禁止当作同一关系。
- [ ] **M3-03 · P0** 为实体定义稳定 ID、别名、语言、设备型号与来源；对未知实体设立审核队列。
- [ ] **M3-04 · P0** 定义关系来源：`source_evidence_id`、抽取方法、版本、时间、人工审核状态。
- [ ] **M3-05 · P0** 以 JSON Schema/Pydantic 限制 LLM 结构化抽取，不允许任意关系类型。
- [ ] **M3-06 · P0** 设计规则+LLM 混合抽取：故障码与结构化表格优先规则，原因/措施使用语义抽取。
- [ ] **M3-07 · P0** 抽取结果对齐原文，任何无法定位来源的三元组进入隔离区而非正式图谱。
- [ ] **M3-08 · P0** 实体消歧：别名归一、型号/部件作用域约束、多义词禁止跨型号合并。
- [ ] **M3-09 · P0** Neo4j 创建唯一约束与索引，节点/边 Upsert 幂等，重复导入不膨胀。
- [ ] **M3-10 · P0** 撤销/版本替换策略：某来源移除时能找到受影响关系并重新核验。
- [ ] **M3-11 · P1** 使用 `data/graph/reference.json` 只做预期对照，不得直接作为 LLM 抽取结果发布。
- [ ] **M3-12 · P1** 单独对 MaintIE gold 测试实体/关系抽取，标注其不是 ABB 根因真值。
- [ ] **M3-13 · P1** 为图谱抽取加入可重复的提示词版本、模型记录、样本错误分析与成本统计。

### M3-B · 图谱检索与归一化证据池

- [ ] **M3-14 · P0** 实体链接：输入型号、故障码、症状→具体 Neo4j 节点，处理找不到/多候选。
- [ ] **M3-15 · P0** Cypher 模板参数化并采用只读账户，禁止让 LLM 直接执行任意 Cypher。
- [ ] **M3-16 · P0** 限制遍历范围：默认 ≤2 跳、≤50 节点、≤100 边，实际阈值可配置并记录。
- [ ] **M3-17 · P0** 图路径应携带来源证据 ID，映射为 OpenSearch/PostgreSQL 可验证的原始片段。
- [ ] **M3-18 · P0** 图与双路检索结果合并去重，并进入统一精排；不能因为路径数多而重复加分。
- [ ] **M3-19 · P0** 将历史工单的 `confirmed_cause` 保留为**历史事件**，不能据此推断当前资产已确诊。
- [ ] **M3-20 · P1** 添加不存在路径、反向关系、循环、错误型号、过多路径和断开证据测试。
- [ ] **M3-21 · P1** 输出图谱覆盖率、关系精度（人工样本）、路径映射成功率和成本。
- [ ] **M3-22 · P1** 消融实验：混合检索 vs 混合检索+GraphRAG，对照相同 query 和模型。

**M3 DoD**：至少一个跨文档示例能展示完整图谱路径，路径每条用于诊断的边均有真实证据或合成来源；重复导入不产生重复节点。

---

## M4｜LangGraph Agentic 补检、可信诊断和 Observability

### M4-A · 状态机

- [ ] **M4-01 · P0** 定义 typed state：query/model/firmware/as_of/observations/queries/evidence/gaps/rounds/usage/stop_reason。
- [ ] **M4-02 · P0** 编排 `normalize → plan → retrieve → verify → supplement? → generate → validate_citations → end`。
- [ ] **M4-03 · P0** 明确第 1 次初始检索是否算轮次，并在所有策略中保持一致（当前设计：算）。
- [ ] **M4-04 · P0** 证据验证分维度：故障码、设备适用性、候选原因、维修证据、冲突证据、缺失检查。
- [ ] **M4-05 · P0** 输出机器可读 `missing_evidence`，用最小缺口驱动下一次检索而非自由发散。
- [ ] **M4-06 · P0** 补检工具：`rewrite_query`, `retrieve_work_orders`, `expand_graph`；每次记录选择理由。
- [ ] **M4-07 · P0** 停止条件：`sufficient / max_rounds / no_new_evidence / source_unavailable / budget_exhausted`。
- [ ] **M4-08 · P0** 定义“新增证据”：必须是此前未见的、适用型号、有效稳定 ID；同段重排不算新增。
- [ ] **M4-09 · P0** 设置最大轮次、Token 预算、超时和 Graph 展开阈值；禁止依赖 LangGraph recursion_limit 做唯一退出机制。
- [ ] **M4-10 · P0** 单元测试三种关键路径：证据已充分、补检无新增、到轮次上限；加入服务不可用路径。
- [ ] **M4-11 · P1** 保持 Agent 可重放：状态转移记录、输入、查询、工具入参、证据 ID、终止原因。
- [ ] **M4-12 · P1** 添加有限重试和幂等 Checkpointer，防止重复执行昂贵补检。

### M4-B · 可信生成与 API

- [ ] **M4-13 · P0** Pydantic 诊断输出：`status`、`root_causes`、`citations`、`next_checks`、`missing_evidence`、`stop_reason`、`usage`。
- [ ] **M4-14 · P0** 根因项按依据强弱排序，不能将未经校准的模型分数伪装成客观概率。
- [ ] **M4-15 · P0** 引用后处理：引用必须属于已检索证据，定位器真实有效，并符合型号和时间限制。
- [ ] **M4-16 · P0** 对无支持断言降级为“待验证假设”或从答案移除；禁止补造手册页码或工单 ID。
- [ ] **M4-17 · P0** 对危险维护步骤标识需专业人员审核，不发出设备控制指令。
- [ ] **M4-18 · P0** FastAPI `POST /diagnoses`，严格按照 `docs/project-scope.md` 的字段契约校验。
- [ ] **M4-19 · P0** 提供 `GET /healthz` 和文档来源跳转方式，避免直接公开系统本地 PDF 原文。
- [ ] **M4-20 · P1** API 异常类型、请求 ID、结构化日志、限流/响应超时与正确 HTTP 状态码。
- [ ] **M4-21 · P1** 安全测试：提示注入（恶意文档）、越权 Cypher、SQL 注入、HTML 转义、隐私脱敏。

### M4-C · Langfuse & 动态补检实验

- [ ] **M4-22 · P0** 集成 Langfuse；每条诊断记录 prompt、检索、重排、图谱扩展与 LLM usage。
- [ ] **M4-23 · P0** 区分入库/索引成本和单次在线诊断成本；每次请求的输入/输出 Token 统计完整。
- [ ] **M4-24 · P0** 固定策略：每题初始检索 + 固定三轮（明确轮次定义），与 Agent 策略可在同配置切换。
- [ ] **M4-25 · P0** 固定模型、语料、温度、最大输出、样本和时间窗口；记录随机性与失败重试。
- [ ] **M4-26 · P0** 汇报 Token 平均值/中位数、延迟 P50/P95、平均补检数、终止原因分布与诊断质量。
- [ ] **M4-27 · P1** 对出现低成本但漏证据的案例单独披露，避免以 Token 下降代替诊断有效性。
- [ ] **M4-28 · P1** 如果复测值不同于目标 -22%，保留真实值、置信区间与实验版本。

**M4 DoD**：从一个真实请求中可以看到每一跳决策、所有证据、停止原因及引用结果；三种终止规则可自动测试。

---

## M5｜独立评测、发布与作品展示

### M5-A · 200 条盲测与防泄漏

- [ ] **M5-01 · P0** 建立独立盲测标注协议：问题、型号、固件、as_of、acceptable causes、gold evidence、needs-checks。
- [ ] **M5-02 · P0** 测试集约 200 条，涵盖故障码精确匹配、跨文档、异型号、适用性未知、信息不足等场景。
- [ ] **M5-03 · P0** 对同一个 `incident_group` 的改写问题统一划分，防止 train/dev/test 跨组泄漏。
- [ ] **M5-04 · P0** 明确真实数据 / 由真实手册支持的合成案例 / 完全模拟案例的不同层级与占比。
- [ ] **M5-05 · P0** 进行双人或独立人工审核与分歧解决；记录 `reviewer`、`review_date`、`decision`，不伪造专家身份。
- [ ] **M5-06 · P0** 冻结测试集版本与 SHA-256；正式评分前不可基于该集合修改检索规则或提示词。
- [ ] **M5-07 · P0** 建立切分隔离自动测试：`data/evaluation/*`、图谱参考和 gold labels 不进入索引或模型上下文。
- [ ] **M5-08 · P0** 结果应分开统计 `supported`、`insufficient`、`out_of_scope`，不能只统计容易回答的问题。
- [ ] **M5-09 · P1** 报告召回定义：多 gold 证据时采用宏平均 Recall@5 或 hit-rate，避免术语混用。
- [ ] **M5-10 · P1** 报告 Root Cause Top-1 准确率、拒答正确率、引用精确率和人工检查失败案例。
- [ ] **M5-11 · P1** 对代表性指标报告置信区间及固定的评测程序版本。

### M5-B · 工程质量与开源交付

- [ ] **M5-12 · P0** 提供真正可用的 Docker Compose 启动命令，包含服务健康检查、数据卷和关闭命令。
- [ ] **M5-13 · P0** README 更新真实的 `install → ingest → diagnose → evaluate` 命令；全部从全新环境验证。
- [ ] **M5-14 · P0** CI 包括 lint、pytest、数据隔离、集成测试（允许慢测试单独触发）和许可证扫描。
- [ ] **M5-15 · P0** 导出最小公开可重复实验：锁文件、模型 ID、corpus 版本、测试 ID、脚本、汇总和逐题结果。
- [ ] **M5-16 · P0** 出具消融矩阵：Dense / Hybrid / Hybrid+Rerank / GraphRAG / Agentic。
- [ ] **M5-17 · P0** 完成质量—成本 Pareto 对比；若节省 Token 却使准确率降低，应如实展示。
- [ ] **M5-18 · P1** 编写演示界面：输入设备故障码/现象、证据引用查看、补检时间线和候选根因。
- [ ] **M5-19 · P1** 补齐 OpenAPI 示例、Demo 视频 / GIF（需真实录屏）、带版权合规的截图。
- [ ] **M5-20 · P1** 完善异常处理、重试、P95 响应时延、错误监控和简单的容量测算。
- [ ] **M5-21 · P1** 加入贡献者文档、Issue 模板、变更记录、CITATION.cff（如果有正式论文/软件引用需求）。
- [ ] **M5-22 · P1** 公开发布前检查 `.env` / access token / 原始厂商 PDF / 个人信息 / 未授权数据泄漏。
- [ ] **M5-23 · P1** 在 Release Notes 中说明真实数据比例、模拟数据局限、尚未支持的型号/版本。
- [ ] **M5-24 · P2** 收集用户反馈和失败案例，准备扩展到第二设备品牌；建立回归套件。

**M5 DoD**：第三方可按 README 在清洁环境复现至少一项完整诊断、数据出处及一份实验报告；不再使用无法核验的简历性能数字。

---

## Backlog（不阻塞第一版）

- [ ] **B-01 · P2** 新增 Schneider ATV320 官方手册，单独建 source/model/firmware 适用性空间，禁止混入 ABB 图谱。
- [ ] **B-02 · P2** 加入 MetroPT-3 传感器时间窗分析（需要与故障事件数据做明确映射，不假装有逐行根因标签）。
- [ ] **B-03 · P2** 研究多跳图谱扩展自适应预算与不同 reranker 的成本效益。
- [ ] **B-04 · P2** 加入人工复核工作台：处理冲突关系、错页码、无证据诊断和补充检查结果。
- [ ] **B-05 · P2** 支持多语种维护文档、术语词典与中英文混合检索。
- [ ] **B-06 · P2** 支持设备资产实例层级、维护时间线和版本迁移历史。
- [ ] **B-07 · P2** 结合时序异常预警，但不将预测性维护指标当作 RAG 根因准确率。

## 第一轮建议创建的 8 个 GitHub Issues

1. `M0-06 | Review seed evidence and synthetic case quality`
2. `M0-13 | Verify ABB PDF fingerprints and page anchors`
3. `M1-07 | Parse ABB manuals with stable page/table locators`
4. `M1-17 | Design evidence database schema and migrations`
5. `M1-21 | Ship Dense-only retrieval baseline`
6. `M2-05 | Implement deterministic RRF fusion with tests`
7. `M3-01 | Freeze industrial fault ontology v1`
8. `M4-07 | Implement and test Agent termination policy`

> 每个 Issue 使用标识、目标、依赖、输入/输出、测试计划和安全风险。PR 需要更新相应的 TODO checkbox、文档与测试。
