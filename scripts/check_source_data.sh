#!/bin/bash
# ===========================================
# 检查源数据库指定日期的数据
# ===========================================
# 使用方式:
#   ./scripts/check_source_data.sh 2026-01-06       # 查看指定日期
#   ./scripts/check_source_data.sh 2026-01          # 查看指定月份所有天
#   ./scripts/check_source_data.sh                  # 查看最近30天
# ===========================================

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# 从 .env 文件读取数据库配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_DIR/.env" ]; then
    source "$PROJECT_DIR/.env"
fi

# 默认配置（可被 .env 覆盖）
MYSQL_HOST="${MYSQL_HOST:-188.107.245.36}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-rootpass}"
MYSQL_DB="${MYSQL_DB:-saas_bdb07bac-d573-4289-b8ff-39029f057bfb}"

# 参数解析
TARGET_DATE="$1"

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}   源数据库数据检查工具${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  MySQL: ${MYSQL_HOST}:${MYSQL_PORT}"
echo -e "  数据库: ${MYSQL_DB}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 构建 Python 脚本
if [ -z "$TARGET_DATE" ]; then
    # 没有参数，显示最近30天
    PYTHON_SCRIPT="
import pymysql
from datetime import datetime, timedelta

conn = pymysql.connect(
    host='${MYSQL_HOST}',
    port=${MYSQL_PORT},
    user='${MYSQL_USER}',
    password='${MYSQL_PASSWORD}',
    database='${MYSQL_DB}'
)
cursor = conn.cursor()

# 获取最近30天涉及的月份
today = datetime.now()
months = set()
for i in range(30):
    d = today - timedelta(days=i)
    months.add(d.strftime('%Y_%m'))

print('=== 最近30天数据概览 ===')
print()

for month in sorted(months, reverse=True):
    table = f'autodialer_call_record_{month}'
    try:
        cursor.execute(f'''
            SELECT DATE(calldate) as dt, COUNT(*) as cnt 
            FROM {table} 
            WHERE calldate >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY DATE(calldate) 
            ORDER BY dt DESC
        ''')
        rows = cursor.fetchall()
        if rows:
            print(f'📅 {month.replace(\"_\", \"-\")}月:')
            for row in rows:
                print(f'   {row[0]}: {row[1]:,} 条')
            print()
    except Exception as e:
        pass

conn.close()
"
elif [[ "$TARGET_DATE" =~ ^[0-9]{4}-[0-9]{2}$ ]]; then
    # 月份格式 (YYYY-MM)
    YEAR_MONTH=$(echo "$TARGET_DATE" | sed 's/-/_/')
    PYTHON_SCRIPT="
import pymysql

conn = pymysql.connect(
    host='${MYSQL_HOST}',
    port=${MYSQL_PORT},
    user='${MYSQL_USER}',
    password='${MYSQL_PASSWORD}',
    database='${MYSQL_DB}'
)
cursor = conn.cursor()

table = 'autodialer_call_record_${YEAR_MONTH}'

print(f'=== {\"${TARGET_DATE}\"} 月数据统计 ===')
print()

try:
    # 按天统计
    cursor.execute(f'''
        SELECT DATE(calldate) as dt, COUNT(*) as cnt 
        FROM {table} 
        GROUP BY DATE(calldate) 
        ORDER BY dt
    ''')
    rows = cursor.fetchall()
    
    if rows:
        total = 0
        for row in rows:
            print(f'  {row[0]}: {row[1]:,} 条')
            total += row[1]
        print()
        print(f'  📊 月总计: {total:,} 条')
    else:
        print('  ⚠️  该月没有数据')
        
except Exception as e:
    print(f'  ❌ 表不存在或查询失败: {e}')

conn.close()
"
else
    # 具体日期格式 (YYYY-MM-DD)
    YEAR_MONTH=$(echo "$TARGET_DATE" | cut -d'-' -f1,2 | sed 's/-/_/')
    PYTHON_SCRIPT="
import pymysql

conn = pymysql.connect(
    host='${MYSQL_HOST}',
    port=${MYSQL_PORT},
    user='${MYSQL_USER}',
    password='${MYSQL_PASSWORD}',
    database='${MYSQL_DB}'
)
cursor = conn.cursor()

table = 'autodialer_call_record_${YEAR_MONTH}'
target_date = '${TARGET_DATE}'

print(f'=== {target_date} 数据统计 ===')
print()

try:
    # 查询该日期的数据量
    cursor.execute(f'''
        SELECT COUNT(*) FROM {table} WHERE DATE(calldate) = %s
    ''', (target_date,))
    count = cursor.fetchone()[0]
    
    if count > 0:
        print(f'  ✅ 通话记录: {count:,} 条')
        
        # 查询时间分布
        cursor.execute(f'''
            SELECT 
                MIN(calldate) as first_call,
                MAX(calldate) as last_call
            FROM {table} 
            WHERE DATE(calldate) = %s
        ''', (target_date,))
        row = cursor.fetchone()
        print(f'  📅 最早通话: {row[0]}')
        print(f'  📅 最晚通话: {row[1]}')
        
        # 查询任务分布
        cursor.execute(f'''
            SELECT task_id, COUNT(*) as cnt 
            FROM {table} 
            WHERE DATE(calldate) = %s
            GROUP BY task_id
            ORDER BY cnt DESC
            LIMIT 5
        ''', (target_date,))
        rows = cursor.fetchall()
        if rows:
            print()
            print('  📋 任务分布 (Top 5):')
            for row in rows:
                print(f'     {row[0][:8]}...: {row[1]:,} 条')
    else:
        print(f'  ⚠️  {target_date} 没有通话记录')
        
        # 查询该月有数据的日期
        cursor.execute(f'''
            SELECT DATE(calldate) as dt, COUNT(*) as cnt 
            FROM {table} 
            GROUP BY DATE(calldate) 
            ORDER BY dt DESC
            LIMIT 5
        ''')
        rows = cursor.fetchall()
        if rows:
            print()
            print('  💡 该月有数据的最近日期:')
            for row in rows:
                print(f'     {row[0]}: {row[1]:,} 条')
        
except Exception as e:
    print(f'  ❌ 查询失败: {e}')

conn.close()
"
fi

# 执行查询
docker exec portrait-api python3 -c "$PYTHON_SCRIPT"

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
