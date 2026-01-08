#!/bin/bash
#
# Portrait 部署验证脚本
#
# 模拟完整的数据清洗流程，用于验证部署是否成功：
# 1. 同步通话记录
# 2. 计算用户画像快照
# 3. 计算场景汇总
# 4. 同步任务名称
#
# 使用方式:
#     bash verify_deployment.sh [--date 2025-11-05] [--api-url http://localhost:8000] [--skip-sync]
#

set -e

# 默认参数
API_URL="http://localhost:8000"
TARGET_DATE=$(date -d "yesterday" +%Y-%m-%d 2>/dev/null || date -v-1d +%Y-%m-%d 2>/dev/null || date +%Y-%m-%d)
SKIP_SYNC=false

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --date)
            TARGET_DATE="$2"
            shift 2
            ;;
        --api-url)
            API_URL="$2"
            shift 2
            ;;
        --skip-sync)
            SKIP_SYNC=true
            shift
            ;;
        --help)
            echo "使用方式: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --date DATE         同步日期 (默认: 昨天)"
            echo "  --api-url URL       API 地址 (默认: http://localhost:8000)"
            echo "  --skip-sync         跳过数据同步步骤"
            echo "  --help              显示帮助信息"
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 移除 API_URL 末尾的斜杠
API_URL="${API_URL%/}"

# 计算周期编号
get_week_key() {
    local date_str=$1
    # 使用 date 命令获取 ISO 周编号
    local year=$(date -d "$date_str" +%G 2>/dev/null || date -j -f "%Y-%m-%d" "$date_str" +%G 2>/dev/null)
    local week=$(date -d "$date_str" +%V 2>/dev/null || date -j -f "%Y-%m-%d" "$date_str" +%V 2>/dev/null)
    echo "${year}-W${week}"
}

PERIOD_KEY=$(get_week_key "$TARGET_DATE")

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 打印步骤标题
print_step() {
    local step=$1
    local title=$2
    echo ""
    echo "============================================================"
    echo "  步骤 $step: $title"
    echo "============================================================"
}

# 打印结果
print_result() {
    local success=$1
    local message=$2
    if [ "$success" = "true" ]; then
        echo -e "\n  ${GREEN}✅ 成功${NC}: $message"
    else
        echo -e "\n  ${RED}❌ 失败${NC}: $message"
    fi
}

# HTTP 请求函数
make_request() {
    local url=$1
    local method=${2:-GET}
    local data=${3:-}
    
    local response
    local http_code
    
    if [ -n "$data" ]; then
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            --max-time 120 \
            "$url" 2>&1)
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" \
            -H "Content-Type: application/json" \
            --max-time 120 \
            "$url" 2>&1)
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo "$body"
        return 0
    else
        echo "{\"error\": \"HTTP $http_code: 请求失败\"}"
        return 1
    fi
}

# 检查 jq 是否安装
check_dependencies() {
    if ! command -v jq &> /dev/null; then
        echo -e "${RED}错误: 需要安装 jq 工具来解析 JSON${NC}"
        echo "请运行: sudo apt-get install jq  (Ubuntu/Debian)"
        echo "或运行: brew install jq  (macOS)"
        exit 1
    fi
    
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}错误: 需要安装 curl 工具${NC}"
        exit 1
    fi
}

# 步骤 0: 检查 API 健康状态
check_health() {
    print_step 0 "检查 API 服务"
    
    local result
    result=$(make_request "$API_URL/health") || {
        print_result false "无法连接到 API 服务"
        return 1
    }
    
    local status
    status=$(echo "$result" | jq -r '.status // "ok"' 2>/dev/null)
    
    if [ -z "$status" ]; then
        print_result false "API 响应格式错误"
        return 1
    fi
    
    print_result true "API 服务正常 - $status"
    return 0
}

# 步骤 1: 获取系统状态
check_system_status() {
    print_step 1 "获取系统状态"
    
    local result
    result=$(make_request "$API_URL/api/v1/admin/status") || {
        print_result false "无法获取系统状态"
        return 1
    }
    
    local data
    data=$(echo "$result" | jq -r '.data // {}' 2>/dev/null)
    
    local status=$(echo "$data" | jq -r '.status // "unknown"')
    local database=$(echo "$data" | jq -r '.database // "unknown"')
    local source_db=$(echo "$data" | jq -r '.source_db // "unknown"')
    local total_periods=$(echo "$data" | jq -r '.total_periods // 0')
    local total_snapshots=$(echo "$data" | jq -r '.total_snapshots // 0')
    local total_enriched=$(echo "$data" | jq -r '.total_enriched_records // 0')
    
    echo ""
    echo "  系统状态: $status"
    echo "  数据库:   $database"
    echo "  源数据库: $source_db"
    echo "  已计算周期数: $total_periods"
    echo "  画像快照总数: $total_snapshots"
    echo "  增强记录总数: $total_enriched"
    
    print_result true "系统状态获取成功"
    return 0
}

# 步骤 2: 同步通话记录
sync_call_records() {
    print_step 2 "同步通话记录 ($TARGET_DATE)"
    
    local result
    result=$(make_request "$API_URL/api/v1/admin/sync" "POST" "{\"date\": \"$TARGET_DATE\"}") || {
        print_result false "同步请求失败"
        return 1
    }
    
    local data
    data=$(echo "$result" | jq -r '.data // {}' 2>/dev/null)
    
    local status=$(echo "$data" | jq -r '.status // "unknown"')
    local synced=$(echo "$data" | jq -r '.synced // 0')
    local message=$(echo "$data" | jq -r '.message // ""')
    
    if [ "$status" = "skipped" ] && [ "$message" = "source_db_unavailable" ]; then
        print_result false "源数据库不可用 - 请检查 MYSQL_HOST 配置"
        return 1
    fi
    
    print_result true "同步 $synced 条记录"
    return 0
}

# 步骤 3: 计算用户画像快照
compute_snapshot() {
    local period_type=$1
    local period_key=$2
    
    print_step 3 "计算用户画像快照 ($period_type/$period_key)"
    
    local result
    result=$(make_request "$API_URL/api/v1/admin/compute" "POST" \
        "{\"period_type\": \"$period_type\", \"period_key\": \"$period_key\", \"force\": true}") || {
        print_result false "计算请求失败"
        return 1
    }
    
    local data
    data=$(echo "$result" | jq -r '.data // {}' 2>/dev/null)
    
    local status=$(echo "$data" | jq -r '.status // "unknown"')
    local users=$(echo "$data" | jq -r '.users // 0')
    local records=$(echo "$data" | jq -r '.records // 0')
    local msg=$(echo "$data" | jq -r '.message // ""')
    
    if [ "$status" != "success" ]; then
        print_result false "${msg:-计算失败}"
        return 1
    fi
    
    print_result true "计算 $users 个用户, $records 条记录"
    return 0
}

# 步骤 4: 计算场景汇总
compute_task_summary() {
    local period_type=$1
    local period_key=$2
    
    print_step 4 "计算场景汇总 ($period_type/$period_key)"
    
    local result
    result=$(make_request "$API_URL/api/v1/admin/compute-task-summary" "POST" \
        "{\"period_type\": \"$period_type\", \"period_key\": \"$period_key\", \"force\": true}") || {
        print_result false "计算请求失败"
        return 1
    }
    
    local data
    data=$(echo "$result" | jq -r '.data // {}' 2>/dev/null)
    
    local status=$(echo "$data" | jq -r '.status // "unknown"')
    local tasks=$(echo "$data" | jq -r '.tasks // 0')
    local msg=$(echo "$data" | jq -r '.message // ""')
    
    if [ "$status" != "success" ]; then
        print_result false "${msg:-计算失败}"
        return 1
    fi
    
    print_result true "计算 $tasks 个场景/任务"
    return 0
}

# 步骤 5: 同步任务名称
sync_task_names() {
    print_step 5 "同步任务名称"
    
    local result
    result=$(make_request "$API_URL/api/v1/admin/sync-task-names" "POST") || {
        print_result false "同步请求失败"
        return 1
    }
    
    local data
    data=$(echo "$result" | jq -r '.data // {}' 2>/dev/null)
    
    local status=$(echo "$data" | jq -r '.status // "unknown"')
    local tasks=$(echo "$data" | jq -r '.tasks // 0')
    local updated=$(echo "$data" | jq -r '.updated // 0')
    
    if [ "$status" = "skipped" ]; then
        print_result false "源数据库不可用，无法同步任务名称"
        return 1
    fi
    
    print_result true "同步 $tasks 个任务, 更新 $updated 条记录"
    return 0
}

# 步骤 6: 验证数据
verify_data() {
    local period_type=$1
    local period_key=$2
    
    print_step 6 "验证数据"
    
    # 检查周期列表
    local result
    result=$(make_request "$API_URL/api/v1/task/periods?period_type=$period_type") || {
        print_result false "无法获取周期列表"
        return 1
    }
    
    local periods
    periods=$(echo "$result" | jq -r '.data // []' 2>/dev/null)
    local period_count=$(echo "$periods" | jq 'length')
    
    if [ "$period_count" -eq 0 ]; then
        print_result false "没有找到任何周期数据"
        return 1
    fi
    
    echo "  找到 $period_count 个周期"
    
    # 检查任务列表
    result=$(make_request "$API_URL/api/v1/task?limit=5&period_type=$period_type&period_key=$period_key") || {
        print_result false "无法获取任务列表"
        return 1
    }
    
    local tasks
    tasks=$(echo "$result" | jq -r '.data // []' 2>/dev/null)
    local task_count=$(echo "$tasks" | jq 'length')
    
    if [ "$task_count" -eq 0 ]; then
        print_result false "没有找到任何任务数据"
        return 1
    fi
    
    echo "  找到 $task_count 个任务/场景"
    echo ""
    echo "  任务列表 (前5个):"
    
    echo "$tasks" | jq -r '.[] | "    - \(.task_name // "(未命名)"): \(.customer_count // 0) 客户"' | head -5
    
    print_result true "数据验证通过"
    return 0
}

# 主函数
main() {
    # 检查依赖
    check_dependencies
    
    echo ""
    echo "============================================================"
    echo "  Portrait 部署验证"
    echo "============================================================"
    echo "  API 地址: $API_URL"
    echo "  同步日期: $TARGET_DATE"
    echo "  周期编号: $PERIOD_KEY"
    echo "============================================================"
    
    # 执行验证流程
    local success=true
    
    # 步骤 0: 检查健康状态
    if ! check_health; then
        echo ""
        echo -e "${RED}❌ 验证失败: API 服务不可用${NC}"
        exit 1
    fi
    
    # 步骤 1: 获取系统状态
    check_system_status || true
    
    # 步骤 2-5: 数据同步和计算
    if [ "$SKIP_SYNC" = false ]; then
        if ! sync_call_records; then
            success=false
        else
            if ! compute_snapshot "week" "$PERIOD_KEY"; then
                success=false
            else
                if ! compute_task_summary "week" "$PERIOD_KEY"; then
                    success=false
                else
                    sync_task_names || true
                fi
            fi
        fi
    fi
    
    # 步骤 6: 验证数据
    if ! verify_data "week" "$PERIOD_KEY"; then
        success=false
    fi
    
    # 最终结果
    echo ""
    echo "============================================================"
    if [ "$success" = true ]; then
        echo -e "  ${GREEN}✅ 部署验证通过!${NC}"
        echo "============================================================"
        echo ""
        exit 0
    else
        echo -e "  ${YELLOW}⚠️  部署验证完成，但有错误${NC}"
        echo "============================================================"
        echo ""
        exit 1
    fi
}

# 运行主函数
main
