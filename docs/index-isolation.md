# 索引与生成输入隔离（M1-25）

当前可检索文件仅为 `data/corpus/knowledge.jsonl`、`work_orders.jsonl`、`alarms.jsonl`；手册由 PostgreSQL 成功导入且未退役的 `chunk` 投影。`data/sources/manifest.json` 只用于核验来源，不能作为检索正文。`data/evaluation/`、`data/graph/reference.json`、审核记录、解析快照及 `artifacts/` 中的实验答案不进入文件索引入口。

`tests/test_index_isolation.py` 对当前生产路径执行以下检查：

- 在禁止目录和未列入白名单的 corpus 文件放置独特标记，包含带 gold/graph 字段的记录和形状合法的知识注释诱饵；运行时拒绝读取这些文件。
- 使用真实文件加载器、`build_index` / `sync_index` 和 CLI 命令。捕获 Embedding 文本及 bulk NDJSON 请求，逐条核对字段、完整身份和正文均等于权威输入；检查新增、修改、删除及重复同步后的请求。
- 完整回读索引 `_source`，比较全部记录与权威集合；同一用例同时运行于内存传输夹具和真实 OpenSearch。数据库侧由已通过的 M1-24 跨服务测试验证成功导入/退役过滤，本项 CLI 测试注入显式手册投影夹具。
- 用真实生成客户端的 HTTP 序列化代码和模拟响应核对最终请求，只允许已核验证据的八个上下文字段。向索引记录或检索命中注入 `gold_evidence_ids`、`acceptable_cause_ids`、`expected_status`、`rationale`、`review_status`、`nodes`、`edges`，必须在 Embedding、索引写入或生成请求前失败。

允许合法证据 ID（例如 `K001`）同时被评测标签引用；不能因为一个 ID 出现在 gold 或参考图中就从权威语料删掉它。合成历史正文仍可描述该历史事件，必须保留 `synthetic` 标识，不能伪装成当前设备的确诊结论。

```bash
uv run --frozen python -m unittest discover -s tests -p test_index_isolation.py -v
# 仅在临时本地 OpenSearch 上显式开启 FORGERCA_TEST_OPENSEARCH=1，启用真实服务用例。
```

测试无需模型下载或 API 密钥，生成响应和向量均为合成夹具。该检查证明当前管线的来源、字段和请求隔离；它不自动识别人工复制进合法正文的答案，也不代替 M5 的事件组划分、独立标注和盲测审核。
