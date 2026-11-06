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

# 显式导入一个解析快照；连接信息由进程环境提供
ingest snapshot:
    uv run --frozen python -m scripts.ingest --snapshot {{quote(snapshot)}}
