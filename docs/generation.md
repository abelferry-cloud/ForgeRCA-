# 受约束生成（M1-23）

`python -m scripts.dense answer` 复用 Dense 检索、适用性过滤和 M1-22 引用回查，再进行一次生成调用。空证据在本地返回 `insufficient`，不初始化生成客户端、不需要生成密钥；查询向量化仍属于前面的检索步骤。

## 模型与请求

固定使用阿里云北京 `qwen-plus-2025-12-01` 快照，Base URL 为 `https://dashscope.aliyuncs.com/compatible-mode/v1`，通过标准库 HTTP 调用 `/chat/completions`。生成与 Embedding 共用进程环境变量 `DASHSCOPE_API_KEY`，不读取预留的 `LLM_API_KEY`。`LLM_PROVIDER=aliyun_dashscope` 和 `LLM_MODEL=qwen-plus-2025-12-01` 必须匹配 `versions.lock.json`。

2026-11-09 已核对[官方快照说明](https://help.aliyun.com/zh/model-studio/qwen-plus)与[结构化输出说明](https://help.aliyun.com/zh/model-studio/qwen-structured-output)：该快照在北京支持文本与结构化输出，Qwen-Plus 的 JSON Object 模式用于非思考生成。本项目设置 `enable_thinking=false`、`response_format=json_object`、`temperature=0`、最多 2048 个输出 Token、60 秒超时；关闭联网搜索，不提供工具，拒绝重定向和自动重试。完整请求超过 65536 UTF-8 字节时拒绝发送，不截断证据；字节限制不是 Token 估算。

无需新增 SDK 或下载模型。API 权重摘要不可取得，`revision` 保留 `null`；固定快照名与温度也不代表服务逐字输出必然一致。代码内提示版本为 `evidence-candidates-v1`。

## 命令

先按 [Dense 检索说明](dense-retrieval.md)完成入库和索引，并设置进程环境变量。将命令中的索引名替换为构建报告返回的具体名称：

```bash
uv run --frozen python -m scripts.dense answer \
  --index '<index 返回的完整索引名>' \
  --query 'ACS580-01 出现 2310，根据可用证据解释候选原因或资料缺口。' \
  --model ACS580-01 --firmware-version 'ASCKX 2.16' \
  --as-of '2026-11-09T00:00:00+08:00' --top-k 5 \
  --output artifacts/dense-answer.json
```

输出必须是 `artifacts/` 内不存在的新文件。检索、回查、API 或生成校验任一步失败，都不发布成功报告或部分答复；错误不回显凭据、提示词、原始响应体或服务详情。

## 结果与校验

报告保留原检索字段与已核验 `hits`，新增 `answer`：

- `status`：`supported` 表示至少有一项候选解释附带可验证引用；`insufficient` 表示证据不足。两者都不是当前设备的确诊结果。
- `candidate_causes`：最多三项，包含候选名称、解释、逐条 `support`。每个支持项用完整 `index_id` 绑定证据，并包含与证据正文完全一致的连续 `quote`；模型不能控制引用 URL、页码或文档身份。服务端固定 `assessment=candidate_only`。
- `citations`：只从本次已核验命中回填，保留 `index_id/evidence_id/document_key/record_kind/synthetic/source/locator`。跨修订同名证据不会因裸 ID 相同而串引。
- `missing_evidence`：证据缺口；`insufficient` 必须非空。只有合成证据被引用时，程序强制降为 `insufficient` 并注明缺口。
- `generation`：是否调用、固定配置和返回的 `prompt_tokens/completion_tokens/total_tokens`；未调用或服务未返回用量时为 `null`，不虚构 Token 数。原检索的 Embedding 用量另行保留。

拒绝未知字段、虚构 ID、非逐字摘录、重复支持项、无支持的候选、错误类型、截断/拒答/工具调用响应和重复 JSON 键。资料中出现的指令作为数据处理，不能覆盖系统提示；合成历史只提供类比，不能确认当前根因。

**这些是结构、引用和摘录一致性检查，不是语义蕴含验证。** 合法引用仍可能支持不足或被解释错误，提示词也不能保证阻止所有提示注入。程序不把模型概率作为置信度，不执行设备操作，固定提示需由专业人员结合现场检查验证；断言支持率仍须后续独立评测与人工复核。

## 验收范围

2026-11-09 真实北京 API 小样本通过：项目注释 `K001` 的候选解释返回 `supported`（三项候选，引用仍为项目注释）；无关问题和合成注释均返回 `insufficient`，空证据本地返回 `insufficient` 且未调用生成模型。三次 API 合计 2248 Token。输入来自显式白名单命中，并由 M1-22 回查；未执行本机 OpenSearch 检索。这不是根因正确率或召回率评测，也不是整条真实服务链路验收。

本地 pytest 314 passed、12 skipped、702 subtests；系统 unittest 321 项、25 skipped；11 项生成专项测试覆盖 HTTP/JSON、模型与密钥配置、引用篡改、空证据、合成降级和命令发布边界。Linux CI 的真实 OpenSearch 测试使用合成向量与生成响应，核对检索→回查→生成引用绑定；API 密钥不进入 CI。

[PR #47](https://github.com/abelferry-cloud/ForgeRCA-/pull/47) 的 [Compose / OpenSearch CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/42631482877) 已通过 16 项 Dense 测试（含真实检索后生成引用绑定）和 11 项生成专项测试；[PostgreSQL CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/42631482960) 与 [解析器 CI](https://github.com/abelferry-cloud/ForgeRCA-/actions/runs/42631482595) 同时通过。

Windows Docker Engine 当前不可用。M0-06/M1-15 人工复核仍待签署；FastAPI、LangGraph 补检、完整诊断持久化与追踪仍待后续里程碑。
