# Dense-only 检索（M1-21）

本阶段提供明确的语料投影、新索引构建和查询命令，使用 M1-20 的阿里云北京 `text-embedding-v4`。依赖现有本地 OpenSearch 和 PostgreSQL，不新增 SDK、不下载 embedding 模型。M1-22 已接入[引用回查](citations.md)，生成和逐题评测仍未实现。

## 索引输入

`index` 命令组合以下两种显式入口：

1. `scripts/corpus_allowlist.py` 的三个文件：项目知识注释、合成工单、合成告警。使用 `indexable_files()` / `assert_indexable()`，与离线校验器共用纯函数 `validate_corpus()`；不调用会读取评测和参考图的 `load_data()`。
2. PostgreSQL 的 `chunk`，只连接父 `document` 和同父文档的成功 `ingest_run`。数据库表白名单单独声明为 `INDEXABLE_DATABASE_TABLES=("chunk",)`。它不把 `data/processed/` 加入文件白名单，也不直接读取解析快照。

手册块保留 `document_key`、来源、修订、型号、原始故障码与正文，类型为 `manual_chunk`。知识注释仍为 `knowledge_note`，不伪装成厂商块；工单和告警保留 `synthetic=true`。只生成 mapping 声明的字段，不把参考图、诊断记录、审核资料或 gold labels 投影进索引。

日期投影约定：厂商 manifest 的 `effective_date` 只有日期精度，项目将其解释为**当日北京时间（UTC+08:00）零点**的可用时间。这是本项目的日粒度约定，不是已知的厂商发布时间；缺少生效日期直接失败，不能用 `accessed_at` 或导入时间替代。文件语料原有的带时区 `available_at` 保持原样。

## 构建新索引

先按[数据库说明](database.md)完成迁移和显式手册导入，按[本地服务说明](local-services.md)启动 Compose，并在被忽略的 `.env` 配置数据库凭据和 `DASHSCOPE_API_KEY`：

```bash
uv run --frozen --env-file .env python -m scripts.dense index \
  --output artifacts/dense/build.json
```

命令先验证全部元数据和证据身份，再调用 embedding。所有向量通过校验后，才创建 `<OPENSEARCH_INDEX_PREFIX>-dense-v3-<UUID>` 独立索引；使用固定 `dense-v3` mapping 和稳定 `_id` 批量 `create`，刷新后核对 mapping 与记录数。输出报告记录具体索引名、条数、向量配置和批次 Token 用量。

不会覆盖已有业务索引、切换别名或默认删除旧索引。重复构建创建新的完整索引，不是增量更新；同一输入批次内重复身份会在模型调用前失败。创建收到成功确认后，批量错误或记录数不符会尝试删除本次新索引；清理失败明确报错，不宣称回滚成功。若创建响应丢失，可能留下未发布的新索引，此时不会删除未确认归属的索引。网络故障恢复和完整的增量替换/删除策略属于 M1-24。

单条文本超过 4096 UTF-8 字节时，embedding 客户端在发送任何批次前拒绝整次调用；不拆掉警告条件、不截断正文、不伪造新证据 ID。当前构建将语料和向量放在内存中，适用于初始化规模，不是流式大规模索引器。

## 查询

将构建报告中的具体索引名用于查询；禁止通配符、别名和旧模型索引：

```bash
uv run --frozen --env-file .env python -m scripts.dense query \
  --index "forgerca-dense-v3-替换为构建报告中的32位UUID" \
  --query "这里填写设备现象" --model ACS580-01 \
  --firmware-version "ASCKX 2.16" --as-of "2026-11-07T00:00:00+08:00" \
  --top-k 5 --output artifacts/dense/query.json
```

查询先核对服务端 mapping 和模型身份，然后只向量化一次查询。`top_k` 接受 1–100 的整数；型号按完整 keyword 精确匹配，不做别名、大小写或前导零转换；`as_of` 必须带时区。过滤位于 Lucene k-NN 内部，避免先取近邻再过滤导致漏掉满足条件的候选，接口依据 [OpenSearch 2.17 过滤文档](https://docs.opensearch.org/2.17/search-plugins/knn/filter-search-knn/)。

本基线只返回当前明确适用的证据：

| 条件 | 处理 |
| --- | --- |
| 型号不匹配或 `available_at > as_of` | 排除 |
| 文档明确不限固件（`unrestricted`） | 在型号/时间匹配后允许 |
| 固件已知且与查询完全一致 | 允许 |
| 固件不匹配、历史固件未知 | 排除 |
| 查询省略固件 | 仅返回明确不限固件的文档/注释 |

未知固件上下文如何用于提示缺口，留给后续适用性策略；这里不把 `null` 当作不限固件。服务返回的记录还会再次检查字段、完整身份、分数和适用性；超时、失败分片、模型错配或非法结果都报错，不能伪装成“无证据”。正常无命中返回空列表。

去重使用 `[record_kind, document_key, evidence_id]` 的稳定索引 ID。同一证据身份只保留最高分；跨文档修订的同名物理证据保留，不能因裸 `evidence_id` 相同丢失父文档。结果按分数降序、稳定 ID 次序输出，含 `rank/score/evidence_id/document_key` 及适用性字段，不返回向量。分数是 OpenSearch 检索分，不是根因概率；最多返回 `top_k` 条，不承诺 ANN 跨运行的候选完全一致。

两种命令只把报告写入 `artifacts/` 内的新 JSON，不覆盖已有文件。查询报告可含厂商正文，必须保持本地忽略。命令不会输出原文、凭据或原始服务错误。当前客户端只连接回环地址的无认证开发服务，不支持远程集群部署。

## 验证范围

2026-11-07 本机已将三个白名单文件的 33 条记录，以及通过现有 M1-18 验证入口检查的硬件手册第 152 页 1 块，提交到真实阿里云 API：34 条均返回 1024 维单位向量，批次 10/10/10/4，共 1784 Token。最长输入 877 UTF-8 字节；未调用评测集、参考图或审核资料。该次只验证向量化与字段准备，**没有在本机写入 OpenSearch**。

离线测试覆盖来源隔离、原始码值、日期投影、跨修订身份、模型错配、批量失败清理、HTTP/JSON 错误、未知固件、返回值复核和命令输出边界。Linux CI 使用真实 PostgreSQL 验证成功导入投影，使用真实 OpenSearch 验证新索引构建、Top-k 排序、型号/时间/固件过滤和空结果；向量由显式合成测试编码器生成，无需 API 密钥，不能当作真实语义检索效果。

```bash
python -m unittest discover -s tests -p test_retrieval_corpus.py -v
python -m unittest discover -s tests -p test_dense.py -v
# 仅对本地临时测试服务显式开启：FORGERCA_TEST_OPENSEARCH=1
```

PR #43 的 [PostgreSQL CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/42362689829) 与 [Compose / OpenSearch CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/42362689853) 已于 2026-11-07 通过，2026-11-09 复核状态通过。数据库套件 14 项通过，Dense 套件 15 项（含真实服务）及文件投影套件 5 项通过。

Windows Docker Engine 当前不可用。本机真实服务链路和诊断质量尚未验收；M1-22 的来源核对和定位器输出见[引用回查](citations.md)。M0-06 / M1-15 人工复核仍待人工完成。
