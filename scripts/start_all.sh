#!/bin/bash
# ============================================
# 一键启动所有服务脚本
# 启动数据库、后端和前端服务
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WEB_DIR="$PROJECT_DIR/web"

echo "🚀 启动所有服务..."
echo ""

cd "$PROJECT_DIR"

# 启动 PostgreSQL
echo "🐘 启动 PostgreSQL (Docker)..."
if docker ps | grep -q "portrait-postgres"; then
    echo "   ⏭️  PostgreSQL 已在运行"
else
    docker compose -f docker/docker-compose.yml up -d postgres
    echo "   ✅ PostgreSQL 已启动"
    sleep 3  # 等待数据库就绪
fi

# 启动后端 API
echo "🐍 启动后端服务 (Uvicorn)..."
if pgrep -f "uvicorn src.main:app" > /dev/null 2>&1; then
    echo "   ⏭️  后端服务已在运行"
else
    nohup uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &
    echo "   ✅ 后端服务已启动 (http://localhost:8000)"
    sleep 2
fi

# 启动前端
echo "📦 启动前端服务 (Vite)..."
if pgrep -f "vite" > /dev/null 2>&1; then
    echo "   ⏭️  前端服务已在运行"
else
    cd "$WEB_DIR"
    nohup npm run dev > /tmp/vite-dev.log 2>&1 &
    echo "   ✅ 前端服务已启动"
    sleep 2
fi

echo ""
echo "============================================"
echo "✅ 所有服务已启动!"
echo ""
echo "📊 前端地址: http://localhost:3001"
echo "🔌 后端地址: http://localhost:8000"
echo "🐘 数据库:   localhost:5432"
echo "============================================"
echo ""
echo "查看日志:"
echo "  后端: tail -f logs/portrait.log"
echo "  错误: tail -f logs/error.log"
echo "  前端: tail -f /tmp/vite-dev.log"
echo ""
echo "停止服务: ./scripts/stop_all.sh"
