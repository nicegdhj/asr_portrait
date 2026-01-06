#!/bin/bash
# ===========================================
# Portrait 离线部署 - 远端部署脚本
# ===========================================
# 功能: 导入镜像并启动服务
# 使用: ./deploy_remote.sh [镜像文件路径]
# ===========================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 打印信息
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# 获取 docker compose 命令
get_compose_cmd() {
    if docker compose version &> /dev/null; then
        echo "docker compose"
    else
        echo "docker-compose"
    fi
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}   Portrait 离线部署 - 远端部署${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
    error "Docker 未安装，请先安装 Docker"
fi

COMPOSE_CMD=$(get_compose_cmd)
if [ "$COMPOSE_CMD" = "docker-compose" ] && ! command -v docker-compose &> /dev/null; then
    error "Docker Compose 未安装"
fi

info "Docker 版本: $(docker --version)"

# 获取镜像文件路径
TAR_FILE="${1:-portrait-images.tar.gz}"

# 如果文件路径是相对路径且在当前目录不存在，尝试在脚本目录查找
if [ ! -f "$TAR_FILE" ] && [[ "$TAR_FILE" != /* ]]; then
    if [ -f "$SCRIPT_DIR/$TAR_FILE" ]; then
        TAR_FILE="$SCRIPT_DIR/$TAR_FILE"
    fi
fi

if [ ! -f "$TAR_FILE" ]; then
    error "打包文件不存在: $TAR_FILE"
fi

# 导入镜像和配置
info "开始解压并导入..."
info "文件: $TAR_FILE"
info "文件大小: $(du -h "$TAR_FILE" | cut -f1)"
echo ""

# 创建临时目录
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# 解压文件
info "解压打包文件..."
info "临时目录: $TEMP_DIR"
tar -xzf "$TAR_FILE" -C "$TEMP_DIR" || error "解压失败"

# 验证解压结果
info "验证解压后的文件..."
if [ ! -d "$TEMP_DIR" ]; then
    error "临时目录不存在: $TEMP_DIR"
fi

# 列出解压后的文件（用于调试）
info "解压后的文件列表:"
ls -lh "$TEMP_DIR" | grep -v "^total" || true
echo ""

# 导入 Docker 镜像
IMAGE_TAR="$TEMP_DIR/images.tar"
if [ -f "$IMAGE_TAR" ]; then
    info "导入 Docker 镜像..."
    info "镜像文件路径: $IMAGE_TAR"
    info "镜像文件大小: $(du -h "$IMAGE_TAR" | cut -f1)"
    # 使用管道方式导入，避免路径和权限问题
    cat "$IMAGE_TAR" | docker load || error "镜像导入失败"
    echo ""
    success "镜像导入完成"
else
    error "未找到镜像文件: $IMAGE_TAR"
fi

# 复制配置文件
if [ -f "$TEMP_DIR/.env" ]; then
    if [ -f ".env" ]; then
        success "环境变量配置已就绪"
    fi
else
    warn "打包文件中未包含 .env 文件"
fi

if [ -f "$TEMP_DIR/docker-compose.prod.yml" ]; then
    info "复制 docker-compose.prod.yml..."
    cp "$TEMP_DIR/docker-compose.prod.yml" .
fi

# 验证镜像
info "验证导入的镜像..."
echo ""

EXPECTED_IMAGES=("portrait-api:latest" "portrait-web:latest" "postgres:15-alpine")
MISSING_IMAGES=()

for img in "${EXPECTED_IMAGES[@]}"; do
    if docker image inspect "$img" &> /dev/null; then
        ARCH=$(docker image inspect "$img" --format '{{.Architecture}}')
        SIZE=$(docker image inspect "$img" --format '{{.Size}}' | awk '{print int($1/1024/1024)}')
        info "✓ $img - 架构: $ARCH, 大小: ${SIZE}MB"
    else
        MISSING_IMAGES+=("$img")
    fi
done

echo ""

if [ ${#MISSING_IMAGES[@]} -gt 0 ]; then
    error "以下镜像导入失败:\n  ${MISSING_IMAGES[*]}"
fi

success "所有镜像验证通过"

# 检查环境变量
if [ ! -f ".env" ]; then
    warn ".env 文件不存在,将使用 docker-compose.prod.yml 中的默认配置"
    warn "建议创建 .env 文件并配置正确的数据库连接信息"
else
    info ".env 文件已就绪"
fi

# 创建日志目录
info "准备日志目录..."
mkdir -p logs
chmod 777 logs
success "日志目录已就绪"

# 启动服务
info "启动服务..."
echo ""

$COMPOSE_CMD -f docker-compose.prod.yml up -d || error "服务启动失败"

echo ""
success "服务已启动"

# 等待服务就绪
info "等待服务启动..."
sleep 10

$COMPOSE_CMD -f docker-compose.prod.yml ps

# 初始化数据库表结构
echo ""
info "初始化数据库表结构..."
$COMPOSE_CMD -f docker-compose.prod.yml exec -T portrait-api alembic upgrade head || {
    warn "数据库迁移失败，可能需要手动执行:"
    warn "  $COMPOSE_CMD -f docker-compose.prod.yml exec portrait-api alembic upgrade head"
}
success "数据库表结构初始化完成"
echo ""

# 健康检查
info "健康检查..."
echo ""

if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    success "✓ 后端 API 服务正常"
else
    warn "✗ 后端 API 服务可能还在启动中"
fi

if curl -sf http://localhost:80 > /dev/null 2>&1; then
    success "✓ 前端服务正常"
else
    warn "✗ 前端服务可能还在启动中"
fi

if docker exec portrait-postgres pg_isready -U portrait > /dev/null 2>&1; then
    success "✓ PostgreSQL 数据库正常"
else
    warn "✗ PostgreSQL 数据库可能还在启动中"
fi

echo ""

# 获取服务器 IP
SERVER_IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "your-server-ip")

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}   服务访问信息${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  前端地址: http://${SERVER_IP}:80"
echo "  后端 API: http://${SERVER_IP}:8000"
echo "  API 文档: http://${SERVER_IP}:8000/docs"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
info "查看日志: $COMPOSE_CMD -f docker-compose.prod.yml logs -f"
info "停止服务: $COMPOSE_CMD -f docker-compose.prod.yml down"
info "重新初始化数据库: $COMPOSE_CMD -f docker-compose.prod.yml exec portrait-api alembic upgrade head"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
success "部署完成!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
