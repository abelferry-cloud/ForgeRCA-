# ForgeRCA · Engineering TODO / Roadmap

> **版本**：v0.3（2026-10-13） · **当前**：M0 工程基线基本就绪（仓库名锁定 `ForgeRCA-`、Apache-2.0 已添加、`main` 主线与分支规范已建立），种子资料仍待人工复核；M1–M5 为计划。  
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
| **M0** | 数据/文档/安全基线 | 无 | 工程基线就绪；人工复核未完成 |
| **M1** | 基础 Dense RAG 与可信引用 | M0 | 未开始 |
| **M2** | 混合检索 + 版本过滤 + Reranker | M1 | 未开始 |
| **M3** | 证据约束的 Neo4j GraphRAG | M1/M2 | 未开始 |
| **M4** | LangGraph 动态补检与 Langfuse | M2/M3 | 未开始 |
| **M5** | 盲测、消融、部署与展示 | M1–M4 | 未开始 |

---

## M0｜仓库与数据基线（**优先先做完**）

### M0-A · GitHub 工程准备

- [x] **M0-01 · P0** 仓库名称维持 `ForgeRCA-`（末尾连字符保留），不改名；clone、CI、Issue 与徽章 URL 保持现状。*(2026-10-13 决定)*
- [x] **M0-02 · P0** 已选定 **Apache-2.0**，添加根目录 `LICENSE`（版权行 `Copyright 2026 abelferry-cloud`）；README 与 CONTRIBUTING 均声明**第三方数据不受项目许可证覆盖**。*(2026-10-13)*
- [ ] **M0-03 · P0** 审核当前 `data/sources/manifest.json` 的 ABB 文档编号、修订、SHA-256、页码与可访问链接。
- [ ] **M0-04 · P0** 在本地运行 `python scripts/validate_data.py`，保存失败信息、修复数据关联问题。
- [ ] **M0-05 · P0** 在本地运行 `python -m unittest discover -s tests -v`，记录 Python 版本和测试摘要。
- [ ] **M0-06 · P0** 对 9 条知识注释、8 条合成工单及 5 条 demo 场景进行至少一次人工领域核对；记录审核人、日期、变更。
- [ ] **M0-07 · P1** GitHub 仓库 About、topics、description、homepage 与 Issue / PR 模板完善。
- [ ] **M0-08 · P1** 确认 CI 在 PR 与默认分支运行：离线数据校验、unittest、敏感文件扫描。
- [x] **M0-09 · P1** 已确立分支管理：`main` 为唯一稳定主线并设为默认分支；**禁止直接向 `main` 提交**，改动一律从 `main` 切出功能分支走 PR，仅错别字、失效链接等极小改动或经维护者明确允许可直接提交。命名前缀 `feat/` `fix/` `docs/` `chore/` `data/`，建议携带任务 ID。详见 `CONTRIBUTING.md`《分支与合并规范》。*(2026-10-13)*
- [ ] **M0-10 · P1** 建立 `.env.example`（只提供非机密参数名），核实 `.gitignore` 忽略 `.env`、密钥、数据库卷和原始 PDF。
- [ ] **M0-11 · P1** 新增 `SECURITY.md`（漏洞报告路径与安全边界），定义数据泄漏排查流程。
- [ ] **M0-12 · P2** 选择 Python 包管理方案（uv / pip），首次添加依赖时生成可复现的锁文件，不提前虚构已装依赖。

### M0-B · 公开数据与来源管理

- [ ] **M0-13 · P0** 将 ABB 官方固件和硬件 PDF 下载到 `data/raw/abb/`，运行 `--check-raw` 校验 SHA-256 和页数。
- [ ] **M0-14 · P0** 对设备型号、固件版本、文档修订定义三套独立字段；补全 `firmware_scope` 适用性逻辑和“未知”分支。
- [ ] **M0-15 · P0** 为每个注释确认 `source_id + pdf_page + locator` 可指向指定 PDF 的实际信息，修复不可追溯项。
- [ ] **M0-16 · P0** 在 `data/raw/` 与 `data/processed/` 保持原始数据不入 Git；记录来源许可证与归属。
- [ ] **M0-17 · P1** 验证可选下载脚本：`python scripts/download_public_data.py --list` / `--dataset maintie-gold`；下载失败须输出清楚的错误。
- [ ] **M0-18 · P1** 下载 MaintIE gold 后验证 JSON 的 tokens/entities/relations，作为**独立**信息抽取数据集。
- [ ] **M0-19 · P1** 下载 AI4I 后确认是合成的预测性维护表格数据，仅用于扩展情境，不赋予 ABB 工单 ID。
- [ ] **M0-20 · P1** 编写第三方数据署名、版本、URL、下载时间、SHA-256、用途和禁止混用说明。
- [ ] **M0-21 · P1** 确保 `data/evaluation/` 永不被数据构建器递归扫描；设置显式 allowlist 测试。
- [ ] **M0-22 · P2** 制定数据卡模板：来源、字段、规模、合成标记、授权、已知偏差、标注状态、预处理版本。
- [ ] **M0-23 · P1** 在 GitHub Settings → Branches 为 `main` 启用分支保护规则：禁止直接推送、要求经 PR 合并、要求 CI 检查通过。*(文字规范已落地，仓库侧开关待开启)*

**M0 DoD**：新贡献者按 README 的现有命令可完成校验；每条种子事实都能追到真实页码或明确的合成记录；未来的第三方数据和盲测答案没有混入主语料；所有改动均经功能分支与 PR 进入 `main`，`main` 历史保持可校验。

---

## M1｜PDF → Evidence Store → Dense-only RAG

### M1-A · 系统底座

- [ ] **M1-01 · P0** 建立 `pyproject.toml`、开发/生产依赖分组、Python 最低版本和 Ruff / pytest 配置。
- [ ] **M1-02 · P0** 建立 `app/` 分层：`ingestion/`, `retrieval/`, `db/`, `api/`, `schemas/`；保持路由不直接处理业务。
- [ ] **M1-03 · P0** 建立配置模块：环境变量、类型检查、缺少必填项时失败、日志中的密钥脱敏。
- [ ] **M1-04 · P0** 本地 Docker Compose 提供 PostgreSQL / OpenSearch / Neo4j；健康检查和端口可配置。
- [ ] **M1-05 · P1** 增加 `Makefile` / `justfile`：`lint`, `test`, `data-check`, `up`, `down`, `ingest`；只有实测能运行后再在 README 展示。
- [ ] **M1-06 · P1** 版本锁定：Docling、向量模型、OpenSearch mapping、DB migration 工具；提交可重现版本清单。

### M1-B · 文档解析与证据锚点

- [ ] **M1-07 · P0** 选择 PDF 解析器（优先 Docling），保留标题、段落、表格、页码和页内顺序。
- [ ] **M1-08 · P0** 建立文档主键：`source_id`、文档编号、修订、固件适用性、文件 SHA-256 与下载来源。
- [ ] **M1-09 · P0** 识别故障码模式并保留原始码值 / 规范化码值，避免将前导零、字母或大小写损坏。
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
