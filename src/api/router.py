"""
API 路由汇总
"""

from fastapi import APIRouter

from .v1 import periods, portrait, admin

api_router = APIRouter()

# 注册 v1 路由
api_router.include_router(periods.router, prefix="/periods", tags=["周期管理"])
api_router.include_router(portrait.router, prefix="/portrait", tags=["用户画像"])
api_router.include_router(admin.router, prefix="/admin", tags=["管理接口"])

