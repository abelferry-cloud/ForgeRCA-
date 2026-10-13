# 初始化补丁如何合并到现有仓库

本交付物针对公开仓库 [`abelferry-cloud/ForgeRCA-`](https://github.com/abelferry-cloud/ForgeRCA-/tree/codex/initialize-project) 的现有 `codex/initialize-project` 版本制作，**是增量补丁，不是覆盖整个仓库的独立应用**。

### 新增文件

- `TODO.md`：完整的可验收 M0–M5 任务清单。
- `docs/public-datasets.md`：公开数据来源、许可和下载方式。
- `scripts/download_public_data.py`：安全限制的轻量公开数据下载器（无需第三方依赖）。
- `tests/test_download_public_data.py`：无需联网的下载器测试。
- `CONTRIBUTING.md`：Issue / PR / 数据安全规范。
- `.github/ISSUE_TEMPLATE/{feature_request,bug_report}.yml`：GitHub 结构化 Issue 模板。
- `docs/merge-notes.md`：本文。

### 替换文件

- `README.md`：新版 GitHub 展示型首页；保留了现有 **ABB ACS580-01** 首期目标、离线脚本命令、数据路径及“尚未实现”的客观状态。

### 不覆盖的文件

- `data/sources/manifest.json`、`data/corpus/*`、`data/evaluation/*`、`data/graph/reference.json`
- `scripts/download_sources.py`、`scripts/validate_data.py`、原有测试和 CI
- `docs/project-scope.md`、`docs/data-spec.md`、`docs/architecture.md`、`docs/evaluation.md`、`docs/knowledge-graph.md`
- `.gitignore`（已有 `data/raw/` 忽略规则适用于新下载的数据）

### 合并步骤

```bash
# 在本地已 clone 的原仓库执行
# 1. 先确认当前分支及工作区干净
git status --short
git branch --show-current

# 2. 解压本补丁包，将其中 ForgeRCA-/ 目录下的内容拷贝到仓库根目录。
#    若你的仓库已有私有改动，先运行 git diff 核查 README 是否需要手动合并。

# 3. 验收
python scripts/download_public_data.py --list
python -m unittest discover -s tests -p 'test_download_public_data.py' -v
python scripts/validate_data.py
python -m unittest discover -s tests -v

# 4. 检查变更再提交
git status --short
git diff -- README.md
```

### 已知限制

当前执行环境不能直接获取 UCI / GitHub 外部二进制文件，因而未将第三方真实数据捆绑进 ZIP，**也未声称已完成外部网络下载测试**。可通过脚本在用户自己的网络环境获取；MetroPT-3 因体积大默认不下载。另：仓库在 GitHub 上真实名称目前是 `ForgeRCA-`，不是最初描述的 `ForgeRCA`。如果之后重命名，请全局修改 clone URL 和 badges。
