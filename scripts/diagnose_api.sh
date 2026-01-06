#!/bin/bash
# 快速诊断 Portrait API 启动失败问题

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Portrait API 启动失败诊断"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "━━━ 1. 容器状态 ━━━"
docker compose -f docker-compose.prod.yml ps

echo ""
echo "━━━ 2. API 日志（最近 50 行）━━━"
docker compose -f docker-compose.prod.yml logs --tail=50 portrait-api

echo ""
echo "━━━ 3. 环境变量检查 ━━━"
if [ -f ".env" ]; then
    echo "PostgreSQL 配置:"
    grep "^POSTGRES_" .env || echo "  未找到 POSTGRES_ 配置"
    echo ""
    echo "MySQL 配置:"
    grep "^MYSQL_" .env || echo "  未找到 MYSQL_ 配置"
else
    echo "错误: .env 文件不存在"
fi

echo ""
echo "━━━ 4. 日志目录权限 ━━━"
if [ -d "logs" ]; then
    ls -la logs/
else
    echo "logs 目录不存在，创建中..."
    mkdir -p logs
    chmod 777 logs
    echo "已创建 logs 目录"
fi

echo ""
echo "━━━ 5. PostgreSQL 连接测试 ━━━"
docker exec portrait-postgres pg_isready -U portrait 2>/dev/null && echo "✓ PostgreSQL 可连接" || echo "✗ PostgreSQL 连接失败"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  建议操作"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "根据上面的日志，常见问题："
echo ""
echo "1. 日志权限错误:"
echo "   mkdir -p logs && chmod 777 logs"
echo "   docker compose -f docker-compose.prod.yml restart portrait-api"
echo ""
echo "2. PostgreSQL 连接错误:"
echo "   确保 .env 中 POSTGRES_HOST=portrait-postgres"
echo "   docker compose -f docker-compose.prod.yml restart portrait-api"
echo ""
echo "3. 数据库未初始化:"
echo "   docker compose -f docker-compose.prod.yml exec portrait-api alembic upgrade head"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
