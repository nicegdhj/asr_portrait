"""
Portrait 用户数据画像服务

FastAPI 应用入口
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from src.api import api_router
from src.core.config import settings
from src.core.database import lifespan_db
from src.core.logging import setup_logging
from src.schemas import ApiResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 初始化日志系统
    setup_logging()

    logger.info(f"启动 {settings.app_name} 服务...")

    # 初始化数据库连接
    async with lifespan_db():
        logger.info("数据库连接已建立")

        # 启动定时任务调度器
        from src.tasks.scheduler import task_scheduler

        task_scheduler.start()

        yield

        # 关闭调度器
        task_scheduler.shutdown()

    logger.info("服务已停止")


# 创建 FastAPI 应用
app = FastAPI(
    title="Portrait - 用户数据画像服务",
    description="""
## 简介

基于智能外呼系统数据构建用户行为画像的 API 服务。

## 功能

- **周期管理**: 查询可用的统计周期 (周/月/季度)
- **用户画像**: 获取单用户或全量用户的画像数据
- **趋势分析**: 获取多周期趋势数据，支持柱状图展示
- **管理接口**: 系统状态查询、手动触发计算

## 数据来源

- 智能外呼系统通话记录
- 通话详情 (ASR 识别文本)
- 任务和号码数据
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理"""
    logger.exception(f"未处理异常: {exc}")
    return JSONResponse(
        status_code=500,
        content=ApiResponse.error(
            message=f"服务器内部错误: {str(exc)}",
            code=500,
        ).model_dump(),
    )


# 健康检查
@app.get(
    "/health",
    tags=["系统"],
    summary="健康检查",
    response_model=ApiResponse[dict],
)
async def health_check():
    """
    健康检查接口

    用于 Docker 健康检查和负载均衡探针
    """
    return ApiResponse.success(
        data={
            "status": "healthy",
            "service": settings.app_name,
            "version": "1.0.0",
        }
    )


# 根路径
@app.get(
    "/",
    tags=["系统"],
    include_in_schema=False,
)
async def root():
    """根路径重定向到文档"""
    return {
        "service": "Portrait - 用户数据画像服务",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


# 注册 API 路由
app.include_router(api_router, prefix=settings.api_prefix)


# 开发环境直接运行
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
