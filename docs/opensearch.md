# OpenSearch 业务字段（M1-19）

`dense-v2` 扩展 M1-06 的最小向量 mapping。M1-20 新建 `dense-v3`，字段不变，将向量模型身份改为阿里云 `text-embedding-v4`，保留独立的 v1/v2 历史文件。当前提供字段配置、写入前契约和临时索引集成测试；[Embedding API](embedding.md) 已单独实测，但没有索引真实语料或实现 Retriever。PostgreSQL 仍是来源和物理定位的权威存储。

## 版本与字段

`versions.lock.json.opensearch_mapping` 指向 `config/opensearch/dense-v3.json` 并记录完整字节 SHA-256。`load_mapping()` 核对摘要后返回配置。继续使用固定的 OpenSearch 2.17.1 镜像，以及 1024 维、Lucene HNSW、cosine 配置；`_meta` 记录 `aliyun_dashscope`、`text-embedding-v4`、L2 归一化和未知的服务端 revision（`null`）。v2 的 BGE 向量与 v3 不兼容，须重建索引；不升级服务、不新增依赖。

| 字段 | OpenSearch 类型 | 输入契约与用途 |
| --- | --- | --- |
| `evidence_id` | `keyword` | 稳定物理证据 ID 或项目记录 ID，不用检索排名代替。 |
| `document_key` / `source_id` / `document_revision` | `keyword` | 厂商块必须与父文档身份一致；项目注释只保留自己的修订与引用来源，不赋予厂商块主键；事件三者均为 `null`。合成注释无厂商来源 ID。 |
| `record_kind` | `keyword` | `manual_chunk` / `knowledge_note` / `work_order` / `alarm`，区分解析原文、项目注释和历史事件。 |
| `chunk_type` | `keyword` | 仅厂商块使用现有四类切块类型，其余为 `null`。 |
| `model` | `keyword` | 非空、无重复的字符串数组；单型号也使用一项数组。厂商块后续应转录来源清单的 `models`，不发明兼容型号。 |
| `firmware_scope` / `firmware_version` | `keyword` | 前者用于文档/注释，后者用于历史事件；不用文档修订代替固件。非空格式沿用 `ASCKX <数字>.<数字>`。 |
| `firmware_state` | `keyword` | `known` / `unrestricted` / `unknown`，由下面的规则确定，不表示已匹配某个诊断输入。 |
| `synthetic` | `boolean` | 显式布尔值；真实厂商块为 `false`，现有虚构事件与干扰注释为 `true`。测试用伪文档只测试类型形状，不构成真实来源。 |
| `available_at` | `date` | 写入契约要求含时区的时间；后续构建器须使用有来源依据的可用时间，不能用导入时间替代、从缺少时区的日期猜测现场时间。 |
| `alarm_code` | `keyword` | 原始码值字符串数组，允许无故障码时为 `[]`；保留前导零、大小写和原文字符，不做数值转换或隐式规范化。 |
| `text` | `text` | 非空正文；使用默认分析器，M2 再处理中文分词/BM25，不宣称已优化全文检索。 |
| `embedding` | `knn_vector` | 1024 个有限、float32 范围内的数值，排除布尔值与零向量；M1-20 客户端执行 L2 归一化，每批最多 10 条。 |

精确字段没有 normalizer。OpenSearch 的 [keyword](https://docs.opensearch.org/2.17/field-types/supported-field-types/keyword/) 不分词、区分大小写；`00a1`、`00A1`、`a1` 分别匹配，不把它们隐式合并。`model` 数组任一元素可以被精确 term 查询命中。

## 两类空固件与写入边界

- `manual_chunk` / `knowledge_note`：`firmware_version` 必须为 `null`；已知 `firmware_scope` 对应 `known`，显式 `firmware_scope=null` 对应 `unrestricted`。
- `work_order` / `alarm`：`firmware_scope` 必须为 `null`；已知 `firmware_version` 对应 `known`，`firmware_version=null` 对应 `unknown`。
- 未知历史固件不能改写为不限固件；`known` 也不等于适用于任意输入版本。查询侧的适用性判断仍须结合记录类型、型号、固件值、修订和时间。

OpenSearch 默认不为 `null` 建倒排项，但 `_source` 仍保留原值，因此只用 `exists` 无法区分上述两类空值。此 mapping 不使用 `null_value` 哨兵，而用独立 `firmware_state` 精确字段表达两类语义；参考 [keyword 空值行为](https://docs.opensearch.org/2.17/field-types/supported-field-types/keyword/)。

`validate_index_record(record, mapping)` 要求所有已声明字段显式存在，不适用值也要写 `null` / `[]`；拒绝未知字段、字符串布尔值、数字码值、缺型号、模糊时间、固件与父文档矛盾、错误向量维度/非有限值。该契约不读取语料或评测文件，也不生成向量。它不证明正文真实性、模型来源、引用语义或来源授权；后续构建器仍须使用既有白名单/已验证的数据库来源，不能直接扫描目录。

`dynamic: strict` 只拒绝未声明字段，并不替代应用的必填字段、枚举和跨字段校验。直接绕过应用向 OpenSearch 写入不享有上述契约保证。`expected_status`、`gold_evidence_ids` 等评测字段未声明；物理定位在检索后按父文档/证据 ID 回查，当前不保存可混入任意 JSON 的不透明载荷。

对通过校验的记录，`index_record_id()` 将 `[record_kind, document_key, evidence_id]` 的确定性 JSON 编码散列为 SHA-256，作为后续写入的 `_id`。不同修订可以拥有相同 `ev1:`，但父文档不同，因此不能只用 `evidence_id` 当 OpenSearch `_id`。正文、向量和排名不参与该身份；同一身份的更新/删除策略仍在 M1-24。

## 运行与验收

```bash
# 离线字段契约与指纹检查，集成项默认跳过
python -m unittest discover -s tests -p test_opensearch_schema.py -v
python -m unittest discover -s tests -p test_version_lock.py -v
```

启动已有 Compose 服务后，可对独立测试索引运行下面的 PowerShell 命令。测试仅访问 `127.0.0.1:9200`，创建随机名称 `forgerca-mapping-test-<UUID>`，结束时只删除本次创建的索引，不读取或改变已有业务索引。

```powershell
$env:FORGERCA_TEST_OPENSEARCH = '1'
try { python -m unittest discover -s tests -p test_opensearch_schema.py -v }
finally { Remove-Item Env:FORGERCA_TEST_OPENSEARCH }
```

Compose CI 自动执行同一测试：建索引后比对完整 mapping，写入三个自造记录与人工向量，回读正文和空值，验证多型号、大小写/前导零、修订、合成标识、固件状态和时间过滤；不同修订同证据 ID 共存；错误维度、未声明字段、对象型号及无效日期返回 HTTP 400。人工向量只证明字段和服务行为，不代表语义检索效果。

迁移到 `dense-v3` 必须新建索引，不能覆盖旧版映射或复用 BGE / 未知来源的旧向量。本项没有执行任何业务索引切换。

2026-11-06 的 [Linux CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/42242297998) 实测 9 项测试全部通过，包含真实 OpenSearch mapping、三个自造记录的回读、精确元数据与时间筛选、跨修订身份及 HTTP 400 拒绝行为；三服务重建和持久化回读也通过。本地 pytest 为 264 passed、8 skipped、523 subtests；系统 Python unittest 为 267 项、21 项跳过，Ruff、数据与敏感文件检查通过。Windows 本机 Docker Engine 仍不可用，未完成本机服务验收。
