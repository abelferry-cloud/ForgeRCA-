# 阿里云稠密向量 API（M1-20）

本阶段调用阿里云百炼北京地域的文本向量服务，提供独立的 `DenseEmbedder.encode(texts)` 和显式文本命令。没有本地 embedding 权重、下载器或 tokenizer；没有自动读取语料、创建向量索引或实现 Retriever。PDF 解析原有的 Docling 依赖不变。

## 模型与请求契约

当前配置在 `versions.lock.json.embedding`：

| 项目 | 设置 |
| --- | --- |
| 服务 / 地域 | `aliyun_dashscope` / `cn-beijing` |
| Base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 请求 | `POST /embeddings`；标准库 HTTPS，无新增 SDK |
| 模型 / 维度 | `text-embedding-v4` / `1024` |
| 返回格式 / 本地处理 | `float` / 每条向量 L2 归一化 |
| 每批 / 超时 | 最多 10 条 / 每次网络操作 30 秒；不自动重试 |
| 本地长度上限 | 单条 4096 个 UTF-8 字节；发送第一批前检查全部输入，超限拒绝 |
| 文本处理 | 无查询/正文前缀，不裁剪、不截断；空白输入拒绝 |

接口和模型能力依据[阿里云兼容接口](https://help.aliyun.com/zh/model-studio/embedding-interfaces-compatible-with-openai)及[同步 API](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api/)。官方文档列出 v4 每批 10 条、每条 8192 Token；本项目的字节上限是独立的客户端策略，不是 Token 估算。真实探测中，重复 9000 次英文单词的请求仍被服务端接受，因此不能凭文档假设超长内容一定收到 HTTP 400；这也不能证明服务端保留或截断了哪些 Token。本项目显式限制输入，后续长块拆分仍需单独设计。

北京旧域名仍受支持，详见[API Key 配置](https://help.aliyun.com/zh/model-studio/get-api-key)。凭据只发往固定 HTTPS 地址，客户端拒绝重定向。错误仅保留 HTTP 状态或固定错误说明，不回显密钥、输入或原始响应；缺少凭据或环境变量中的模型名与清单不同，会在请求前失败。

API 不提供本地可校验的权重 revision；`revision: null` 表示未知，不能伪造 BGE 的 commit 或承诺跨时间逐位复现。`embedding_reference` 仅保留 M1-06 的 BGE 身份作为历史记录，不参与运行。`dense-v3` 更新模型身份和归一化元数据，`dense-v1` / `dense-v2` 保持原样。即使同为 1024 维，不同模型的向量也不能混用；换模型必须新建配置版本并重建索引。

## 使用

在本地已被忽略的 `.env` 配置 `DASHSCOPE_API_KEY`，`EMBEDDING_MODEL` 保持 `text-embedding-v4`。密钥不通过命令行参数传递，也不写入版本清单、配置快照或 CI。命令仅使用标准库，可直接运行 Python；若凭据放在 `.env`，使用 uv 的显式加载入口：

```bash
uv run --frozen --env-file .env python -m scripts.embed_text \
  --text "这是自造的接口连通性测试句子。" \
  --output artifacts/embedding/example.json
```

此命令会将显式输入发送到阿里云，并可能产生 API 用量。不会读取 `data/evaluation/`、`data/graph/`、审核材料或厂商 PDF。原文不复制到输出；输出包含向量、输入摘要、批次大小、服务端返回的 Token 用量、UTC 时间、配置及配置 SHA-256。缺失的用量记为 `null`，不记 0；不把 embedding 用量算成诊断生成 Token。

输出只允许写入 `artifacts/` 下的新 JSON，拒绝覆盖已有文件。全部请求成功后才发布结果；后续批次失败不会生成部分结果文件，但此前成功请求仍可能计费。该命令不是批量语料索引入口。

## 验收

2026-11-07，北京真实 API 使用自造中英文文本完成命令行调用：输出 2 个 1024 维向量。另测两条输入的顺序反转，向量最大差为 0；11 条输入分成 10 + 1，客户端归一化后的单位范数通过。后四次成功请求的服务端用量合计 94 Token；此数字不含首个命令行请求及长度探测，不是性能或成本基准。运行结果仅保存在本地忽略目录。

11 项离线测试覆盖批次、原文保留、响应索引乱序、重复/缺失索引、维度/非有限值/零向量、模型错配、UTF-8 长度边界、401/403/429/500、传输和 JSON 错误、禁止重定向、密钥脱敏和部分失败不发布结果。测试随既有标准库 CI 执行，不要求密钥，也不联网。

```bash
python -m unittest discover -s tests -p test_embedding.py -v
```

尚未验证实际语料召回率、索引写入、查询过滤或诊断质量；这些属于 M1-21 及后续任务。M0-06 与 M1-15 的人工复核仍待人工填写。
