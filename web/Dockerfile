# ===========================================
# 构建阶段 - 使用 Node.js 构建 Vue 应用
# ===========================================
FROM --platform=linux/amd64 node:20-alpine AS builder

WORKDIR /app

# 复制依赖文件
COPY package*.json ./

# 安装依赖(包括 devDependencies 用于构建)
RUN npm ci && \
    npm cache clean --force

# 复制源码
COPY . .

# 构建生产版本
RUN npm run build

# ===========================================
# 生产阶段 - 使用 Nginx 提供静态文件
# ===========================================
FROM --platform=linux/amd64 nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 暴露端口
EXPOSE 80

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80 || exit 1

# 启动 Nginx
CMD ["nginx", "-g", "daemon off;"]
