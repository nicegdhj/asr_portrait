# Portrait 用户数据画像服务 Dockerfile
# 多阶段构建,减小镜像体积,支持跨平台构建

# ===========================================
# 构建阶段
# ===========================================
FROM --platform=linux/amd64 python:3.11-slim as builder

WORKDIR /app

# 安装构建依赖(合并 RUN 减少层数)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && pip install --no-cache-dir uv \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 复制依赖文件
COPY pyproject.toml README.md ./

# 创建虚拟环境并安装依赖
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache .

# ===========================================
# 运行阶段
# ===========================================
FROM --platform=linux/amd64 python:3.11-slim as runtime

WORKDIR /app

# 安装运行时依赖(合并 RUN 减少层数)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# 从构建阶段复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制源代码(只复制必要的文件)
COPY src/ ./src/
COPY migrations/ ./migrations/
COPY alembic.ini ./

# 环境变量
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production

# 创建非 root 用户和日志目录
RUN groupadd -r portrait && \
    useradd -r -g portrait portrait && \
    mkdir -p /app/logs && \
    chown -R portrait:portrait /app

USER portrait

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

