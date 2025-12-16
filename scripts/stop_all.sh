#!/bin/bash
# ============================================
# 一键关闭所有服务脚本
# 停止前端、后端和数据库服务
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🛑 停止所有服务..."
echo ""

# 停止前端 Vite 开发服务器
echo "📦 停止前端服务 (Vite)..."
if pgrep -f "vite" > /dev/null 2>&1; then
    pkill -f "vite" && echo "   ✅ 前端服务已停止"
else
    echo "   ⏭️  前端服务未运行"
fi

# 停止后端 API 服务
echo "🐍 停止后端服务 (Uvicorn)..."
if pgrep -f "uvicorn src.main:app" > /dev/null 2>&1; then
    pkill -f "uvicorn src.main:app" && echo "   ✅ 后端服务已停止"
else
    echo "   ⏭️  后端服务未运行"
fi

# 停止 Docker PostgreSQL (可选，默认不停止)
if [[ "$1" == "--all" ]] || [[ "$1" == "-a" ]]; then
    echo "🐘 停止 PostgreSQL (Docker)..."
    cd "$PROJECT_DIR"
    if docker ps | grep -q "portrait-postgres"; then
        docker compose -f docker/docker-compose.yml down && echo "   ✅ PostgreSQL 已停止"
    else
        echo "   ⏭️  PostgreSQL 未运行"
    fi
fi

echo ""
echo "✅ 所有服务已停止!"
echo ""
echo "提示: 使用 --all 或 -a 参数同时停止 Docker 数据库"
echo "例如: ./scripts/stop_all.sh --all"
