#!/bin/bash
# ===========================================
# Portrait 部署后访问检测脚本
# ===========================================
# 功能: 检测服务状态、防火墙、获取访问地址
# 使用: ./check_access.sh
# ===========================================

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 打印函数
info() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; }
title() { echo -e "\n${BLUE}━━━ $1 ━━━${NC}"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${CYAN}   Portrait 部署检测工具${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ===========================================
# 1. 获取服务器 IP 地址
# ===========================================
title "服务器 IP 地址检测"

# 内网 IP
INTERNAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$INTERNAL_IP" ]; then
    INTERNAL_IP=$(ip route get 1 2>/dev/null | awk '{print $7; exit}')
fi
if [ -z "$INTERNAL_IP" ]; then
    INTERNAL_IP="无法获取"
fi
info "内网 IP: ${INTERNAL_IP}"

# 公网 IP (尝试多个服务)
PUBLIC_IP=""
for service in "ifconfig.me" "ipinfo.io/ip" "icanhazip.com" "api.ipify.org"; do
    PUBLIC_IP=$(curl -s --connect-timeout 3 --max-time 5 "$service" 2>/dev/null)
    if [[ "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        break
    fi
    PUBLIC_IP=""
done

if [ -n "$PUBLIC_IP" ]; then
    info "公网 IP: ${PUBLIC_IP}"
else
    warn "公网 IP: 无法获取 (可能无公网访问)"
fi

# ===========================================
# 2. Docker 服务状态检测
# ===========================================
title "Docker 容器状态"

if ! command -v docker &> /dev/null; then
    error "Docker 未安装"
    exit 1
fi

# 检查各个容器
CONTAINERS=("portrait-web" "portrait-api" "portrait-postgres")
ALL_RUNNING=true

for container in "${CONTAINERS[@]}"; do
    STATUS=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "not_found")
    if [ "$STATUS" = "running" ]; then
        info "$container: 运行中"
    elif [ "$STATUS" = "not_found" ]; then
        error "$container: 未找到"
        ALL_RUNNING=false
    else
        error "$container: $STATUS"
        ALL_RUNNING=false
    fi
done

# ===========================================
# 3. 端口监听检测
# ===========================================
title "端口监听状态"

# 从 .env 文件读取端口配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"

API_PORT=8000
WEB_PORT=80
POSTGRES_PORT=5432

if [ -f "$ENV_FILE" ]; then
    API_PORT_FROM_ENV=$(grep "^API_PORT=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'" | xargs)
    WEB_PORT_FROM_ENV=$(grep "^WEB_PORT=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'" | xargs)
    POSTGRES_PORT_FROM_ENV=$(grep "^POSTGRES_PORT=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'" | xargs)
    
    [ -n "$API_PORT_FROM_ENV" ] && API_PORT="$API_PORT_FROM_ENV"
    [ -n "$WEB_PORT_FROM_ENV" ] && WEB_PORT="$WEB_PORT_FROM_ENV"
    [ -n "$POSTGRES_PORT_FROM_ENV" ] && POSTGRES_PORT="$POSTGRES_PORT_FROM_ENV"
fi

check_port() {
    local port=$1
    local name=$2
    if ss -tlnp 2>/dev/null | grep -q ":${port} " || netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        info "端口 ${port} (${name}): 已监听"
        return 0
    else
        error "端口 ${port} (${name}): 未监听"
        return 1
    fi
}

check_port $WEB_PORT "前端"
check_port $API_PORT "后端API"
check_port $POSTGRES_PORT "PostgreSQL"

# ===========================================
# 4. 服务健康检测
# ===========================================
title "服务健康检查"

# 前端检测
if curl -sf --connect-timeout 5 http://localhost:${WEB_PORT} > /dev/null 2>&1; then
    info "前端服务: 正常响应"
else
    error "前端服务: 无响应"
fi

# 后端 API 检测
API_HEALTH=$(curl -sf --connect-timeout 5 http://localhost:${API_PORT}/health 2>/dev/null)
if [ $? -eq 0 ]; then
    info "后端 API: 正常响应"
else
    error "后端 API: 无响应"
fi

# 数据库检测
if docker exec portrait-postgres pg_isready -U portrait > /dev/null 2>&1; then
    info "PostgreSQL: 正常运行"
else
    error "PostgreSQL: 无响应"
fi

# ===========================================
# 5. 防火墙状态检测
# ===========================================
title "防火墙状态"

FIREWALL_ISSUES=""

# 检测 UFW (Ubuntu/Debian)
if command -v ufw &> /dev/null; then
    UFW_STATUS=$(sudo ufw status 2>/dev/null | head -1)
    if echo "$UFW_STATUS" | grep -q "active"; then
        info "UFW 防火墙: 已启用"
        # 检查端口是否开放
        for port in $WEB_PORT $API_PORT; do
            if sudo ufw status 2>/dev/null | grep -qE "^${port}.*ALLOW"; then
                info "  端口 ${port}: 已开放"
            else
                warn "  端口 ${port}: 未开放"
                FIREWALL_ISSUES="$FIREWALL_ISSUES\n  sudo ufw allow ${port}/tcp"
            fi
        done
    else
        info "UFW 防火墙: 未启用"
    fi
fi

# 检测 firewalld (CentOS/RHEL)
if command -v firewall-cmd &> /dev/null; then
    if systemctl is-active firewalld &> /dev/null; then
        info "firewalld 防火墙: 已启用"
        for port in $WEB_PORT $API_PORT; do
            if sudo firewall-cmd --list-ports 2>/dev/null | grep -q "${port}/tcp"; then
                info "  端口 ${port}: 已开放"
            else
                warn "  端口 ${port}: 未开放"
                FIREWALL_ISSUES="$FIREWALL_ISSUES\n  sudo firewall-cmd --permanent --add-port=${port}/tcp"
            fi
        done
    else
        info "firewalld 防火墙: 未启用"
    fi
fi

# 检测 iptables
if command -v iptables &> /dev/null && [ -z "$FIREWALL_ISSUES" ]; then
    info "可通过 iptables 管理防火墙规则"
fi

# ===========================================
# 6. 生成访问地址
# ===========================================
title "访问地址"

echo ""
echo -e "${CYAN}┌──────────────────────────────────────────────────────────┐${NC}"
echo -e "${CYAN}│${NC}  ${GREEN}前端访问地址${NC}                                          ${CYAN}│${NC}"
echo -e "${CYAN}├──────────────────────────────────────────────────────────┤${NC}"

if [ "$INTERNAL_IP" != "无法获取" ]; then
    echo -e "${CYAN}│${NC}  局域网: ${YELLOW}http://${INTERNAL_IP}${NC}                        ${CYAN}│${NC}"
fi

if [ -n "$PUBLIC_IP" ]; then
    echo -e "${CYAN}│${NC}  公网:   ${YELLOW}http://${PUBLIC_IP}${NC}                        ${CYAN}│${NC}"
fi

echo -e "${CYAN}│${NC}  本机:   ${YELLOW}http://localhost${NC}                             ${CYAN}│${NC}"
echo -e "${CYAN}├──────────────────────────────────────────────────────────┤${NC}"
echo -e "${CYAN}│${NC}  ${GREEN}API 文档${NC}                                              ${CYAN}│${NC}"
echo -e "${CYAN}├──────────────────────────────────────────────────────────┤${NC}"

if [ "$INTERNAL_IP" != "无法获取" ]; then
    echo -e "${CYAN}│${NC}  局域网: ${YELLOW}http://${INTERNAL_IP}:${API_PORT}/docs${NC}               ${CYAN}│${NC}"
fi

if [ -n "$PUBLIC_IP" ]; then
    echo -e "${CYAN}│${NC}  公网:   ${YELLOW}http://${PUBLIC_IP}:${API_PORT}/docs${NC}               ${CYAN}│${NC}"
fi

echo -e "${CYAN}│${NC}  本机:   ${YELLOW}http://localhost:${API_PORT}/docs${NC}                    ${CYAN}│${NC}"
echo -e "${CYAN}└──────────────────────────────────────────────────────────┘${NC}"
echo ""

# ===========================================
# 7. 问题诊断建议
# ===========================================
if [ "$ALL_RUNNING" = false ] || [ -n "$FIREWALL_ISSUES" ]; then
    title "问题修复建议"
    
    if [ "$ALL_RUNNING" = false ]; then
        echo -e "${YELLOW}容器未正常运行，请执行:${NC}"
        echo "  docker compose -f docker-compose.prod.yml up -d"
        echo "  docker compose -f docker-compose.prod.yml logs -f"
        echo ""
    fi
    
    if [ -n "$FIREWALL_ISSUES" ]; then
        echo -e "${YELLOW}防火墙端口未开放，请执行:${NC}"
        echo -e "$FIREWALL_ISSUES"
        echo ""
    fi
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}检测完成!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
