#!/bin/bash
# ===========================================
# MySQL 测试环境启动脚本
# ===========================================
# 功能: 启动 MySQL 测试服务并加载模拟数据
# 使用: ./scripts/start_test_mysql.sh
# ===========================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
title() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}   启动 MySQL 测试环境${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 检查模拟数据
title "检查模拟数据"

if [ ! -d "data/mock_sql" ]; then
    error "模拟数据目录不存在: data/mock_sql"
fi

SQL_FILES=$(ls data/mock_sql/*.sql 2>/dev/null | wc -l)
if [ "$SQL_FILES" -eq 0 ]; then
    error "未找到 SQL 文件"
fi

info "找到 $SQL_FILES 个 SQL 文件"
ls -lh data/mock_sql/*.sql

# 启动 MySQL
title "启动 MySQL 容器"

info "使用配置: docker/docker-compose.test-mysql.yml"
docker compose -f docker/docker-compose.test-mysql.yml up -d

# 等待 MySQL 就绪
title "等待 MySQL 启动"

info "等待健康检查通过（数据文件较大，可能需要 2-3 分钟）..."
MAX_WAIT=180  # 增加到 3 分钟
WAIT_TIME=0

while [ $WAIT_TIME -lt $MAX_WAIT ]; do
    if docker compose -f docker/docker-compose.test-mysql.yml ps | grep -q "healthy"; then
        info "MySQL 已就绪"
        break
    fi
    echo -n "."
    sleep 5  # 每 5 秒检查一次
    WAIT_TIME=$((WAIT_TIME + 5))
done

if [ $WAIT_TIME -ge $MAX_WAIT ]; then
    warn "MySQL 启动超时，但可能仍在初始化中..."
    warn "数据文件较大（~240MB），请继续等待并手动检查："
    echo ""
    echo "  # 查看日志"
    echo "  docker compose -f docker/docker-compose.test-mysql.yml logs -f test-mysql"
    echo ""
    echo "  # 检查容器状态"
    echo "  docker compose -f docker/docker-compose.test-mysql.yml ps"
    echo ""
    echo "  # 测试连接"
    echo "  docker exec portrait-test-mysql mysqladmin ping -h localhost -u root -proot123"
    echo ""
fi

# 验证数据加载
title "验证数据加载"

info "检查数据库和表..."

# 等待额外时间让初始化脚本执行
sleep 5

# 检查表是否存在
TABLES=$(docker exec portrait-test-mysql mysql -uroot -proot123 -D outbound_saas -e "SHOW TABLES;" 2>/dev/null | grep -v "Tables_in" | wc -l)

if [ "$TABLES" -gt 0 ]; then
    info "成功加载 $TABLES 个表"
    docker exec portrait-test-mysql mysql -uroot -proot123 -D outbound_saas -e "SHOW TABLES;" 2>/dev/null
else
    warn "未检测到表，可能还在加载中..."
    warn "数据文件较大，请稍后使用以下命令检查："
    echo "  docker exec portrait-test-mysql mysql -uroot -proot123 -D outbound_saas -e \"SHOW TABLES;\""
fi

# 显示连接信息
title "连接信息"

echo ""
echo "MySQL 测试环境已启动！"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  连接信息"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  主机: localhost"
echo "  端口: 3306"
echo "  数据库: outbound_saas"
echo "  用户: root"
echo "  密码: root123"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "更新 .env 配置："
echo ""
echo "  MYSQL_HOST=localhost"
echo "  MYSQL_PORT=3306"
echo "  MYSQL_USER=root"
echo "  MYSQL_PASSWORD=root123"
echo "  MYSQL_DB=outbound_saas"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "常用命令："
echo ""
echo "  # 查看日志"
echo "  docker compose -f docker/docker-compose.test-mysql.yml logs -f"
echo ""
echo "  # 连接 MySQL"
echo "  docker exec -it portrait-test-mysql mysql -uroot -proot123 outbound_saas"
echo ""
echo "  # 停止服务"
echo "  docker compose -f docker/docker-compose.test-mysql.yml down"
echo ""
echo "  # 停止并删除数据"
echo "  docker compose -f docker/docker-compose.test-mysql.yml down -v"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

