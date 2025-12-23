#!/bin/bash
# ===========================================
# Portrait 用户画像系统 - 云部署脚本
# ===========================================
# 使用方式:
#   ./scripts/deploy.sh          # 首次部署或更新
#   ./scripts/deploy.sh rebuild  # 重新构建镜像
#   ./scripts/deploy.sh logs     # 查看日志
#   ./scripts/deploy.sh stop     # 停止服务
#   ./scripts/deploy.sh restart  # 重启服务
# ===========================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 切换到项目目录
cd "$PROJECT_DIR"

# 打印信息
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# 检查 .env 文件
check_env() {
    if [ ! -f ".env" ]; then
        warn ".env 文件不存在"
        if [ -f "env.production.example" ]; then
            info "从模板创建 .env 文件..."
            cp env.production.example .env
            warn "请编辑 .env 文件配置数据库连接信息后重新运行"
            exit 1
        else
            error "缺少环境变量配置文件"
        fi
    fi
    info ".env 文件已就绪"
}

# 检查 Docker
check_docker() {
    if ! command -v docker &> /dev/null; then
        error "Docker 未安装，请先安装 Docker"
    fi
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        error "Docker Compose 未安装"
    fi
    info "Docker 环境检查通过"
}

# 获取 docker compose 命令
get_compose_cmd() {
    if docker compose version &> /dev/null; then
        echo "docker compose"
    else
        echo "docker-compose"
    fi
}

# 部署/更新
deploy() {
    info "开始部署..."
    
    check_docker
    check_env
    
    COMPOSE_CMD=$(get_compose_cmd)
    
    # 拉取最新代码 (如果是 git 仓库)
    if [ -d ".git" ]; then
        info "拉取最新代码..."
        git pull || warn "Git pull 失败，使用本地代码继续"
    fi
    
    # 构建并启动
    info "构建 Docker 镜像..."
    $COMPOSE_CMD -f docker-compose.prod.yml build
    
    info "启动服务..."
    $COMPOSE_CMD -f docker-compose.prod.yml up -d
    
    # 等待服务启动
    info "等待服务启动..."
    sleep 10
    
    # 检查服务状态
    info "检查服务状态..."
    $COMPOSE_CMD -f docker-compose.prod.yml ps
    
    # 健康检查
    info "健康检查..."
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        info "后端 API 服务正常 ✓"
    else
        warn "后端 API 服务可能还在启动中，请稍后检查"
    fi
    
    if curl -sf http://localhost:80 > /dev/null 2>&1; then
        info "前端服务正常 ✓"
    else
        warn "前端服务可能还在启动中，请稍后检查"
    fi
    
    echo ""
    info "部署完成！"
    info "前端访问: http://<your-server-ip>:80"
    info "后端 API: http://<your-server-ip>:8000"
    info "API 文档: http://<your-server-ip>:8000/docs"
}

# 重新构建
rebuild() {
    info "重新构建镜像..."
    
    check_docker
    check_env
    
    COMPOSE_CMD=$(get_compose_cmd)
    
    info "停止现有服务..."
    $COMPOSE_CMD -f docker-compose.prod.yml down
    
    info "清理旧镜像..."
    docker image prune -f
    
    info "重新构建..."
    $COMPOSE_CMD -f docker-compose.prod.yml build --no-cache
    
    info "启动服务..."
    $COMPOSE_CMD -f docker-compose.prod.yml up -d
    
    info "重建完成！"
}

# 查看日志
logs() {
    COMPOSE_CMD=$(get_compose_cmd)
    SERVICE=${2:-}
    
    if [ -z "$SERVICE" ]; then
        $COMPOSE_CMD -f docker-compose.prod.yml logs -f --tail=100
    else
        $COMPOSE_CMD -f docker-compose.prod.yml logs -f --tail=100 "$SERVICE"
    fi
}

# 停止服务
stop() {
    info "停止服务..."
    COMPOSE_CMD=$(get_compose_cmd)
    $COMPOSE_CMD -f docker-compose.prod.yml down
    info "服务已停止"
}

# 重启服务
restart() {
    info "重启服务..."
    COMPOSE_CMD=$(get_compose_cmd)
    $COMPOSE_CMD -f docker-compose.prod.yml restart
    info "服务已重启"
}

# 查看状态
status() {
    COMPOSE_CMD=$(get_compose_cmd)
    $COMPOSE_CMD -f docker-compose.prod.yml ps
}

# 初始化数据库
init_db() {
    info "初始化数据库..."
    COMPOSE_CMD=$(get_compose_cmd)
    
    # 等待数据库就绪
    info "等待 PostgreSQL 就绪..."
    sleep 5
    
    # 运行数据库迁移
    info "运行数据库迁移..."
    $COMPOSE_CMD -f docker-compose.prod.yml exec portrait-api alembic upgrade head
    
    info "数据库初始化完成"
}

# 同步数据
sync_data() {
    info "触发数据同步..."
    COMPOSE_CMD=$(get_compose_cmd)
    
    # 调用 admin API 同步数据
    curl -X POST http://localhost:8000/api/v1/admin/sync
    
    info "数据同步已触发"
}

# 主函数
main() {
    case "${1:-deploy}" in
        deploy)
            deploy
            ;;
        rebuild)
            rebuild
            ;;
        logs)
            logs "$@"
            ;;
        stop)
            stop
            ;;
        restart)
            restart
            ;;
        status)
            status
            ;;
        init-db)
            init_db
            ;;
        sync)
            sync_data
            ;;
        *)
            echo "使用方式: $0 {deploy|rebuild|logs|stop|restart|status|init-db|sync}"
            echo ""
            echo "命令说明:"
            echo "  deploy   - 首次部署或更新 (默认)"
            echo "  rebuild  - 重新构建镜像"
            echo "  logs     - 查看日志 (可指定服务名)"
            echo "  stop     - 停止所有服务"
            echo "  restart  - 重启所有服务"
            echo "  status   - 查看服务状态"
            echo "  init-db  - 初始化数据库"
            echo "  sync     - 触发数据同步"
            exit 1
            ;;
    esac
}

main "$@"
