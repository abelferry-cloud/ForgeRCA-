set default-list

[windows]
set shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

# 静态检查
lint:
    uv run --frozen ruff check .

# 全量测试
test:
    uv run --frozen pytest

# 离线数据校验与敏感文件扫描；任一步失败即停止
data-check:
    python scripts/validate_data.py
    python scripts/check_sensitive_files.py

# 启动本地服务，并等待健康检查通过
up:
    docker compose up -d --wait --wait-timeout 300

# 停止本地服务，保留数据卷
down:
    docker compose down

# 导入尚未实现；此入口明确失败，不写入任何数据
ingest:
    @python -c "import sys; sys.exit('ingest is not implemented; see M1-07 to M1-18')"
