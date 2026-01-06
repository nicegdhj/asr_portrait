#!/bin/bash
# ===========================================
# Portrait 部署问题诊断脚本
# ===========================================
# 功能: 诊断容器启动失败的原因
# 使用: ./diagnose_deployment.sh
# ===========================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }
title() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}   Portrait 部署问题诊断${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ===========================================
# 1. 检查容器状态
# ===========================================
title "容器状态"

docker compose -f docker-compose.prod.yml ps

# ===========================================
# 2. 查看 portrait-api 容器日志
# ===========================================
title "portrait-api 容器日志 (最近 50 行)"

docker compose -f docker-compose.prod.yml logs --tail=50 portrait-api

# ===========================================
# 3. 检查容器健康状态
# ===========================================
title "容器健康检查详情"

if docker ps -a | grep -q portrait-api; then
    HEALTH_STATUS=$(docker inspect portrait-api --format='{{.State.Health.Status}}' 2>/dev/null || echo "no healthcheck")
    info "portrait-api 健康状态: $HEALTH_STATUS"
    
    if [ "$HEALTH_STATUS" != "no healthcheck" ] && [ "$HEALTH_STATUS" != "healthy" ]; then
        warn "健康检查失败日志:"
        docker inspect portrait-api --format='{{range .State.Health.Log}}{{.Output}}{{end}}' 2>/dev/null || echo "无健康检查日志"
    fi
fi

# ===========================================
# 4. 检查环境变量配置
# ===========================================
title "环境变量检查"

if [ -f ".env" ]; then
    info ".env 文件存在"
    echo ""
    echo "关键配置项："
    grep -E "^(POSTGRES_|MYSQL_|APP_ENV)" .env | sed 's/PASSWORD=.*/PASSWORD=***/' || true
else
    error ".env 文件不存在"
fi

# ===========================================
# 5. 检查数据库连接
# ===========================================
title "数据库连接测试"

# 检查 PostgreSQL
if docker ps | grep -q portrait-postgres; then
    if docker exec portrait-postgres pg_isready -U portrait > /dev/null 2>&1; then
        info "PostgreSQL 数据库: 可连接"
    else
        error "PostgreSQL 数据库: 无法连接"
    fi
else
    error "portrait-postgres 容器未运行"
fi

# ===========================================
# 6. 尝试手动启动 API 容器
# ===========================================
title "尝试手动启动 API 容器"

echo "执行命令: docker compose -f docker-compose.prod.yml up portrait-api"
echo "按 Ctrl+C 可中断..."
echo ""

sleep 2

docker compose -f docker-compose.prod.yml up portrait-api

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}诊断完成${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
