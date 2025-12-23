# 云部署指南

本文档详细说明如何将 Portrait 用户画像系统从本机部署到云服务器。

---

## 目录

- [准备工作](#准备工作)
- [方式一：一键部署（推荐）](#方式一一键部署推荐)
- [方式二：手动部署](#方式二手动部署)
- [数据库初始化](#数据库初始化)
- [数据同步配置](#数据同步配置)
- [常见问题](#常见问题)
- [运维命令](#运维命令)

---

## 准备工作

### 1. 云服务器要求

| 项目 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2核 | 4核 |
| 内存 | 4GB | 8GB |
| 磁盘 | 40GB SSD | 100GB SSD |
| 系统 | Ubuntu 20.04+ / CentOS 7+ | Ubuntu 22.04 |

### 2. 安装 Docker

**Ubuntu/Debian:**
```bash
# 安装 Docker
curl -fsSL https://get.docker.com | sh

# 启动 Docker
sudo systemctl start docker
sudo systemctl enable docker

# 将当前用户加入 docker 组（免 sudo）
sudo usermod -aG docker $USER
newgrp docker

# 验证安装
docker --version
docker compose version
```

**CentOS:**
```bash
# 安装 Docker
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 启动 Docker
sudo systemctl start docker
sudo systemctl enable docker

# 将当前用户加入 docker 组
sudo usermod -aG docker $USER
newgrp docker
```

### 3. 开放端口

在云服务器安全组/防火墙中开放以下端口：

| 端口 | 用途 | 是否必须 |
|------|------|---------|
| 80 | 前端 Web 服务 | ✅ 必须 |
| 8000 | 后端 API 服务 | 可选（内部访问） |
| 22 | SSH | ✅ 必须 |

### 4. 网络连通性检查

确保云服务器能访问 MySQL 源数据库：

```bash
# 测试 MySQL 连接
telnet your_mysql_host 3306

# 或使用 nc
nc -zv your_mysql_host 3306
```

> ⚠️ 如果源数据库在内网，需要配置 VPN 或专线连接

---

## 方式一：一键部署（推荐）

### 步骤 1: 上传代码到服务器

**方式 A: Git 克隆**
```bash
# 在云服务器上
cd /opt
git clone <your-repo-url> portrait
cd portrait
```

**方式 B: 本地打包上传**
```bash
# 本地执行：打包代码
tar -czvf portrait.tar.gz \
    --exclude='.venv' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.git' \
    --exclude='data' \
    .

# 上传到服务器
scp portrait.tar.gz user@your-server:/opt/

# 服务器上解压
ssh user@your-server
cd /opt
mkdir -p portrait && cd portrait
tar -xzvf ../portrait.tar.gz
```

### 步骤 2: 配置环境变量

```bash
# 复制环境变量模板
cp env.production.example .env

# 编辑配置
vim .env
```

**必须修改的配置：**

```env
# PostgreSQL 密码（务必修改为强密码）
POSTGRES_PASSWORD=YourSecurePassword123!

# MySQL 源数据库连接信息
MYSQL_HOST=10.0.0.100          # MySQL 服务器地址
MYSQL_PORT=3306
MYSQL_USER=readonly_user        # 只读用户
MYSQL_PASSWORD=your_mysql_pass  # MySQL 密码
MYSQL_DB=outbound_saas          # 数据库名
```

### 步骤 3: 执行部署

```bash
# 添加执行权限
chmod +x scripts/deploy.sh

# 一键部署
./scripts/deploy.sh deploy
```

### 步骤 4: 验证部署

```bash
# 查看服务状态
./scripts/deploy.sh status

# 查看日志
./scripts/deploy.sh logs

# 访问测试
curl http://localhost:8000/health
curl http://localhost:80
```

浏览器访问：
- 前端界面：`http://<服务器IP>/`
- API 文档：`http://<服务器IP>:8000/docs`

---

## 方式二：手动部署

### 步骤 1: 配置环境变量

```bash
cd /opt/portrait
cp env.production.example .env
vim .env  # 按上述说明修改
```

### 步骤 2: 构建镜像

```bash
# 构建后端镜像
docker build -t portrait-api -f docker/Dockerfile .

# 构建前端镜像
docker build -t portrait-web -f web/Dockerfile ./web
```

### 步骤 3: 启动服务

```bash
# 使用 docker compose 启动
docker compose -f docker-compose.prod.yml up -d

# 查看日志
docker compose -f docker-compose.prod.yml logs -f
```

---

## 数据库初始化

首次部署后，需要初始化数据库表结构：

```bash
# 方式1: 使用部署脚本
./scripts/deploy.sh init-db

# 方式2: 手动执行迁移
docker compose -f docker-compose.prod.yml exec portrait-api alembic upgrade head
```

### 同步数据

初始化数据库后，可以触发首次数据同步：

```bash
# 通过 API 触发
curl -X POST http://localhost:8000/api/v1/admin/sync

# 或进入容器执行
docker compose -f docker-compose.prod.yml exec portrait-api \
    python -c "
import asyncio
from src.services.etl_service import etl_service
from datetime import date, timedelta

async def sync():
    # 同步最近7天数据
    for i in range(7):
        d = date.today() - timedelta(days=i)
        await etl_service.sync_call_records(d)
        print(f'Synced {d}')

asyncio.run(sync())
"
```

---

## 数据同步配置

### 自动同步（推荐）

在 `.env` 中启用定时任务：

```env
# 启用调度器
SCHEDULER_ENABLED=true

# 每天凌晨 2 点同步
SYNC_CRON_HOUR=2
SYNC_CRON_MINUTE=0
```

重启服务生效：
```bash
./scripts/deploy.sh restart
```

### 手动同步

```bash
# 同步指定日期
curl -X POST "http://localhost:8000/api/v1/admin/sync?date=2025-12-01"

# 计算画像快照
curl -X POST "http://localhost:8000/api/v1/admin/compute?period_type=week&period_key=2025-W48"
```

---

## 常见问题

### Q1: 无法连接 MySQL 源数据库

**症状**: API 启动成功但数据为空

**检查步骤**:
```bash
# 1. 检查网络连通性
docker compose -f docker-compose.prod.yml exec portrait-api \
    python -c "import socket; socket.create_connection(('$MYSQL_HOST', 3306), timeout=5); print('OK')"

# 2. 检查环境变量
docker compose -f docker-compose.prod.yml exec portrait-api env | grep MYSQL

# 3. 查看详细日志
./scripts/deploy.sh logs portrait-api
```

**解决方案**:
- 确认云服务器安全组开放了到 MySQL 的出站规则
- 确认 MySQL 允许远程连接
- 检查 MySQL 用户权限

### Q2: 前端无法访问后端 API

**症状**: 前端页面显示但数据加载失败

**检查步骤**:
```bash
# 检查 Nginx 配置
docker compose -f docker-compose.prod.yml exec portrait-web cat /etc/nginx/conf.d/default.conf

# 检查容器网络
docker network inspect portrait_portrait-network
```

**解决方案**:
确保 `nginx.conf` 中的代理地址正确：
```nginx
location /api/ {
    proxy_pass http://portrait-api:8000;  # 使用容器名
}
```

### Q3: 磁盘空间不足

```bash
# 清理 Docker 缓存
docker system prune -a

# 清理旧镜像
docker image prune -a

# 查看磁盘使用
docker system df
```

### Q4: 服务启动慢或失败

```bash
# 查看详细启动日志
docker compose -f docker-compose.prod.yml logs --tail=200 portrait-api

# 检查健康状态
docker compose -f docker-compose.prod.yml ps

# 重新构建
./scripts/deploy.sh rebuild
```

---

## 运维命令

### 日常运维

```bash
# 查看服务状态
./scripts/deploy.sh status

# 查看所有日志
./scripts/deploy.sh logs

# 查看特定服务日志
./scripts/deploy.sh logs portrait-api

# 重启服务
./scripts/deploy.sh restart

# 停止服务
./scripts/deploy.sh stop
```

### 更新部署

```bash
# 拉取最新代码（如果使用 Git）
git pull

# 重新部署
./scripts/deploy.sh deploy

# 或强制重建
./scripts/deploy.sh rebuild
```

### 数据库操作

```bash
# 进入 PostgreSQL
docker compose -f docker-compose.prod.yml exec portrait-postgres \
    psql -U portrait -d portrait

# 备份数据库
docker compose -f docker-compose.prod.yml exec portrait-postgres \
    pg_dump -U portrait portrait > backup_$(date +%Y%m%d).sql

# 恢复数据库
cat backup_20251216.sql | docker compose -f docker-compose.prod.yml exec -T portrait-postgres \
    psql -U portrait -d portrait
```

### 日志管理

```bash
# 实时查看日志
docker compose -f docker-compose.prod.yml logs -f

# 导出日志
docker compose -f docker-compose.prod.yml logs --no-color > logs_$(date +%Y%m%d).txt

# 清理日志（谨慎操作）
docker compose -f docker-compose.prod.yml down
docker volume prune
```

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        云服务器                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐      ┌─────────────┐      ┌─────────────┐    │
│   │   Nginx     │      │  FastAPI    │      │ PostgreSQL  │    │
│   │   (前端)    │─────►│  (后端API)  │─────►│  (画像库)   │    │
│   │   :80       │      │   :8000     │      │   :5432     │    │
│   └─────────────┘      └──────┬──────┘      └─────────────┘    │
│                               │                                 │
│   Docker Network: portrait-network                              │
│                               │                                 │
└───────────────────────────────┼─────────────────────────────────┘
                                │
                                │ (内网/VPN)
                                ▼
                        ┌─────────────┐
                        │   MySQL     │
                        │  (源数据库) │
                        │  (外呼系统) │
                        └─────────────┘
```

---

## 更新日志

- 2025-12-16: 初始版本
