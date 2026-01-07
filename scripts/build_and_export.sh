#!/bin/bash
# ===========================================
# Portrait 离线部署 - 本地构建打包脚本
# ===========================================
# 功能: 构建 linux/amd64 镜像并导出为 tar 文件
# 输出: files/portrait-images.tar
# ===========================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${PROJECT_DIR}/files"
OUTPUT_FILE="${OUTPUT_DIR}/portrait-images.tar"

cd "$PROJECT_DIR"

# 打印信息
info() { echo -e "${GREEN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLUE}   Portrait 离线部署 - 本地构建打包${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查 Docker
if ! command -v docker &> /dev/null; then
    error "Docker 未安装，请先安装 Docker Desktop"
fi
info "Docker 版本: $(docker --version)"

# 检查并创建 buildx 构建器
info "检查 Docker Buildx 环境..."
if ! docker buildx version &> /dev/null; then
    error "Docker Buildx 不可用，请升级 Docker Desktop"
fi

if docker buildx ls | grep -q "multiarch"; then
    info "使用现有的 multiarch 构建器"
    docker buildx use multiarch
else
    info "创建新的 multiarch 构建器..."
    docker buildx create --name multiarch --driver docker-container --use
    docker buildx inspect --bootstrap
fi
success "Buildx 环境准备完成"

# 构建镜像并直接导出为 tar
info "开始构建 linux/amd64 平台镜像..."
echo ""

# 创建临时目录存放单个镜像 tar
TEMP_DIR="${OUTPUT_DIR}/temp"
mkdir -p "$TEMP_DIR"

info "1/3 构建后端 API 镜像..."
docker buildx build \
    --platform linux/amd64 \
    -t portrait-api:latest \
    --output type=docker,dest="${TEMP_DIR}/portrait-api.tar" \
    -f docker/Dockerfile \
    . || error "后端镜像构建失败"
success "后端镜像构建完成"
echo ""

info "2/3 构建前端 Web 镜像..."
docker buildx build \
    --platform linux/amd64 \
    -t portrait-web:latest \
    --output type=docker,dest="${TEMP_DIR}/portrait-web.tar" \
    -f web/Dockerfile \
    ./web || error "前端镜像构建失败"
success "前端镜像构建完成"
echo ""

# 拉取 PostgreSQL 镜像并导出
info "3/3 拉取并导出 PostgreSQL 镜像..."
docker pull --platform linux/amd64 postgres:15-alpine
docker save -o "${TEMP_DIR}/postgres.tar" postgres:15-alpine || error "PostgreSQL 镜像导出失败"
success "PostgreSQL 镜像导出完成"
echo ""

# 加载镜像到本地 Docker 以便验证
info "加载镜像到本地 Docker..."
docker load -i "${TEMP_DIR}/portrait-api.tar" > /dev/null
docker load -i "${TEMP_DIR}/portrait-web.tar" > /dev/null
docker load -i "${TEMP_DIR}/postgres.tar" > /dev/null

# 验证镜像
info "验证镜像平台架构..."
API_ARCH=$(docker image inspect portrait-api:latest --format '{{.Architecture}}')
WEB_ARCH=$(docker image inspect portrait-web:latest --format '{{.Architecture}}')
PG_ARCH=$(docker image inspect postgres:15-alpine --format '{{.Architecture}}')
[ "$API_ARCH" != "amd64" ] && error "后端镜像架构错误: $API_ARCH"
[ "$WEB_ARCH" != "amd64" ] && error "前端镜像架构错误: $WEB_ARCH"
info "✓ portrait-api:latest - 架构: $API_ARCH"
info "✓ portrait-web:latest - 架构: $WEB_ARCH"
info "✓ postgres:15-alpine - 架构: $PG_ARCH"
echo ""
success "所有镜像验证通过"

# 重新导出所有镜像为一个 tar 文件
info "合并所有镜像到单个 tar 文件..."
IMAGES_TAR="${OUTPUT_DIR}/images.tar"
docker save -o "$IMAGES_TAR" \
    portrait-api:latest \
    portrait-web:latest \
    postgres:15-alpine || error "镜像导出失败"
success "镜像合并完成"

# 检查 .env.remote 文件（远端环境配置）
if [ ! -f ".env.remote" ]; then
    error ".env.remote 文件不存在，请先创建远端环境配置文件"
else
    info "复制 .env.remote 文件到打包目录..."
    cp .env.remote "$OUTPUT_DIR/.env.remote"
fi

# 复制 docker-compose.prod.yml
info "复制 docker-compose.prod.yml..."
cp docker-compose.prod.yml "$OUTPUT_DIR/"

# 复制部署脚本
info "复制部署脚本..."
mkdir -p "$OUTPUT_DIR/scripts"
cp scripts/deploy_remote.sh "$OUTPUT_DIR/scripts/"
cp scripts/check_access.sh "$OUTPUT_DIR/scripts/"
chmod +x "$OUTPUT_DIR/scripts/"*.sh

# 打包所有文件
info "打包镜像和配置文件..."
cd "$OUTPUT_DIR"

# 生成带时间戳的文件名
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_FILENAME="portrait-images_${TIMESTAMP}.tar.gz"

# 打包时包含脚本目录和环境配置
tar -czf "$OUTPUT_FILENAME" images.tar docker-compose.prod.yml scripts/ .env.remote
cd "$PROJECT_DIR"

# 清理临时文件
rm -rf "$TEMP_DIR"
rm -f "$IMAGES_TAR"

# 最终输出文件
OUTPUT_FILE="${OUTPUT_DIR}/${OUTPUT_FILENAME}"

success "打包完成"
echo ""

# 显示文件信息
FILE_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
FILE_SIZE_MB=$(du -m "$OUTPUT_FILE" | cut -f1)

info "导出文件信息:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  文件路径: $OUTPUT_FILE"
echo "  文件大小: $FILE_SIZE (${FILE_SIZE_MB}MB)"
echo "  包含内容:"
echo "    - portrait-api:latest (Docker 镜像)"
echo "    - portrait-web:latest (Docker 镜像)"
echo "    - postgres:15-alpine (Docker 镜像)"
echo "    - docker-compose.prod.yml (编排配置)"
echo "    - .env.remote (远端环境变量配置)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

info "传输到云端服务器的方法:"
echo ""
echo "  方法1: 使用 scp 命令"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  scp $OUTPUT_FILE user@your-server:/path/to/destination/"
echo ""
echo "  方法2: 使用 rsync 命令(支持断点续传)"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  rsync -avP $OUTPUT_FILE user@your-server:/path/to/destination/"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
success "构建打包完成!"
echo ""
info "下一步: 将 $OUTPUT_FILE 传输到云端服务器"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
