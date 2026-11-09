# 引用回查（M1-22）

`python -m scripts.dense query` 在检索之后、写出报告之前默认回查每一条命中的来源。只有整批验证通过，才发布含 `evidence_id + locator` 的报告；缺失来源、旧正文、版本错配或错误定位器都会使命令失败，不能把部分结果当作已核验引用。

沿用 [Dense 检索命令](dense-retrieval.md#查询)。已有索引无需修改 mapping；索引中的记录必须仍与权威来源一致，否则需重新构建。仅出现手册命中时才需要 PostgreSQL；纯文件命中和空结果不连接数据库。回查本身不调用模型、不下载 PDF，也不读取评测集、参考图或审核资料。

## 来源与版本

| 命中类型 | 回查入口 | 核对内容 |
| --- | --- | --- |
| `manual_chunk` | PostgreSQL `chunk + document + ingest_run`，只接受成功导入 | 按 `(document_key, evidence_id)` 查找；正文及全部索引元数据与数据库投影相同；父文档所有身份字段与导入时的 `source_metadata` 相同；重算物理定位器的 `ev1` 指纹；物理页、已知印刷页与来源一致 |
| 非合成 `knowledge_note` | 三个白名单 JSONL 与当前 manifest | 保持项目注释身份；核对正文、修订、型号、固件、可用时间及来源；物理页须已核验，印刷页须匹配绑定 PDF 指纹的显式页码表 |
| 合成注释、工单、告警 | 三个白名单 JSONL | 保持 `synthetic=true`；只返回原文件与记录 ID，不附厂商来源 |

检索身份使用 `(record_kind, document_key, evidence_id)`，并重算 `index_id`。同一个物理证据 ID 可以属于不同修订，回查不会合并或自动换成最新版本。历史手册使用其入库来源快照；当前 manifest 不必仍包含该旧版本。

项目注释的索引字段没有保存建索引时的 PDF SHA，因此它核验的是当前 manifest 中同来源、同修订的引用，不声称能识别“同修订下替换 PDF 并同时更新所有来源元数据”的情况。手册索引的 `document_key` 包含完整 SHA。这里检查已入库/登记的指纹关系，不重新下载或逐次校验磁盘 PDF；实际原 PDF 字节检查已在 M1-18 导入入口执行。

## 输出

每个 `hits` 项保留原检索元数据、排序与分数，新增：

- `source`：厂商来源的 `document_key/source_id/document_code/revision/sha256/source_url/accessed_at/firmware_scope`；合成记录为 `null`。注释本身的顶层 `document_key` 仍为 `null`，引用文档身份在 `source` 内。
- `locator`：注释保留 `source_id/pdf_page/printed_page/section`；合成记录保留 `file/record_id`；手册包含 `evidence_locator/locations/section/table_row`。
- PDF 定位器的 `url` 使用原来源地址加 `#page=<物理页>`。手册跨页块保留全部物理页，未知印刷页保持 `null`，不推算页码偏移。

`table_row` 仅保留入库时的表格上下文，它的解析器引用不是永久 ID；物理定位器用于定位原 PDF。页链接是否自动跳页取决于 PDF 查看器是否支持片段参数。回查验证来源一致性，不代表项目注释已完成领域复核，也不证明检索内容足以确诊。

报告仍只写到本地忽略的 `artifacts/` 新 JSON。服务异常不会输出数据库参数、凭据、原文或原始服务错误；失败不会发布部分引用。

## 验收

```bash
python -m unittest discover -s tests -p test_citations.py -v
python -m unittest discover -s tests -p test_dense.py -v
# 临时 PostgreSQL 的显式开关为 FORGERCA_TEST_POSTGRES=1
# 临时 OpenSearch 的显式开关为 FORGERCA_TEST_OPENSEARCH=1
```

离线覆盖 33 条白名单记录、跨修订同名证据、正文/来源/页码/指纹篡改、缺失来源、文件读取边界、跨页及未知印刷页、命令发布边界。PostgreSQL CI 验证精确复合键、跨修订回查与失败导入排除；OpenSearch CI 验证实际检索命中再回查白名单来源。服务测试使用合成向量/数据库夹具，不是语义召回效果评测。

2026-11-09 本机已回查当前 33 条白名单记录；另通过 M1-18 原 PDF/解析快照验证入口，核对硬件手册 1 块的定位器，得到物理页 152、显式印刷页 `152` 及原来源页链接。该次只验证文件回查与手册入库准备数据，没有实际数据库读写、OpenSearch 检索或模型调用。本地 pytest 303 passed、12 skipped、675 subtests；引用回查的 9 项离线测试通过。

Windows Docker Engine 当前不可用，本机完整数据库/检索链路尚未验收。M0-06 与 M1-15 的人工复核仍待人工签署。
