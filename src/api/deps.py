"""
API 依赖注入

提供数据库会话、认证等公共依赖
"""

from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_portrait_db, get_source_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取画像数据库会话"""
    async for session in get_portrait_db():
        yield session


async def get_source() -> AsyncGenerator[AsyncSession, None]:
    """获取源数据库会话 (只读)"""
    async for session in get_source_db():
        yield session


# 类型别名，用于路由函数参数注入
PortraitDB = Annotated[AsyncSession, Depends(get_db)]
SourceDB = Annotated[AsyncSession, Depends(get_source)]

