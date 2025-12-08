#!/bin/bash
# Phase 1 完整验证脚本

echo "===== Phase 1 验证开始 ====="

# 1. 环境准备
echo "[1/5] 检查依赖..."
uv sync

# 2. 数据库迁移
echo "[2/5] 执行数据库迁移..."
uv run alembic upgrade head

# 3. 启动服务 (后台)
echo "[3/5] 启动 API 服务..."
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
sleep 3

# 4. API 测试
echo "[4/5] 测试 API..."
curl -sf http://localhost:8000/health && echo "健康检查: ✓" || echo "健康检查: ✗"
curl -sf http://localhost:8000/api/v1/periods?type=week && echo "周期接口: ✓" || echo "周期接口: ✗"

# 5. 自动化测试
echo "[5/5] 运行测试..."
kill $API_PID 2>/dev/null
uv run pytest tests/ -v

echo "===== Phase 1 验证完成 ====="
