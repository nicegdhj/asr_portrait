"""
数据库连接管理

- PostgreSQL: 画像数据存储 (读写)
- MySQL: 智能外呼源数据 (只读)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import settings

# ===========================================
# PostgreSQL 连接池 (画像存储)
# ===========================================

_portrait_engine: AsyncEngine | None = None
_portrait_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_portrait_db() -> None:
    """初始化 PostgreSQL 连接池"""
    global _portrait_engine, _portrait_session_factory
    
    logger.info(f"初始化 PostgreSQL 连接: {settings.postgres_host}:{settings.postgres_port}")
    
    _portrait_engine = create_async_engine(
        settings.postgres_dsn,
        echo=settings.debug,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    
    _portrait_session_factory = async_sessionmaker(
        bind=_portrait_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    
    # 测试连接
    async with _portrait_engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    
    logger.info("PostgreSQL 连接池初始化成功")


async def close_portrait_db() -> None:
    """关闭 PostgreSQL 连接池"""
    global _portrait_engine, _portrait_session_factory
    
    if _portrait_engine:
        await _portrait_engine.dispose()
        _portrait_engine = None
        _portrait_session_factory = None
        logger.info("PostgreSQL 连接池已关闭")


async def get_portrait_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取 PostgreSQL 会话 (画像存储)
    
    用法:
        async with get_portrait_db() as session:
            result = await session.execute(...)
    """
    if _portrait_session_factory is None:
        raise RuntimeError("PostgreSQL 连接池未初始化，请先调用 init_portrait_db()")
    
    async with _portrait_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ===========================================
# MySQL 连接池 (源数据 - 只读)
# ===========================================

_source_engine: AsyncEngine | None = None
_source_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_source_db() -> bool:
    """
    初始化 MySQL 连接池 (只读)
    
    Returns:
        bool: 连接是否成功
    """
    global _source_engine, _source_session_factory
    
    logger.info(f"初始化 MySQL 连接: {settings.mysql_host}:{settings.mysql_port}")
    
    try:
        _source_engine = create_async_engine(
            settings.mysql_dsn,
            echo=settings.debug,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        
        _source_session_factory = async_sessionmaker(
            bind=_source_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        # 测试连接
        async with _source_engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        
        logger.info("MySQL 连接池初始化成功")
        return True
    except Exception as e:
        logger.warning(f"MySQL 连接失败 (源数据库不可用): {e}")
        logger.warning("注意: 源数据库连接失败不影响 API 启动，但数据同步功能将不可用")
        _source_engine = None
        _source_session_factory = None
        return False


async def close_source_db() -> None:
    """关闭 MySQL 连接池"""
    global _source_engine, _source_session_factory
    
    if _source_engine:
        await _source_engine.dispose()
        _source_engine = None
        _source_session_factory = None
        logger.info("MySQL 连接池已关闭")


async def get_source_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取 MySQL 会话 (源数据只读)
    
    用法:
        async with get_source_db() as session:
            result = await session.execute(...)
    """
    if _source_session_factory is None:
        raise RuntimeError("MySQL 源数据库不可用。请检查网络连接或配置。")
    
    async with _source_session_factory() as session:
        try:
            yield session
            # 只读，不需要 commit
        except Exception:
            await session.rollback()
            raise


def is_source_db_available() -> bool:
    """检查 MySQL 源数据库是否可用"""
    return _source_session_factory is not None


# ===========================================
# 数据库生命周期管理
# ===========================================

@asynccontextmanager
async def lifespan_db():
    """
    数据库生命周期管理器
    
    用于 FastAPI lifespan:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with lifespan_db():
                yield
    """
    try:
        await init_portrait_db()
        await init_source_db()
        yield
    finally:
        await close_portrait_db()
        await close_source_db()


def get_portrait_engine() -> AsyncEngine:
    """获取 PostgreSQL 引擎 (用于 Alembic 等场景)"""
    if _portrait_engine is None:
        raise RuntimeError("PostgreSQL 连接池未初始化")
    return _portrait_engine


def get_source_engine() -> AsyncEngine:
    """获取 MySQL 引擎"""
    if _source_engine is None:
        raise RuntimeError("MySQL 连接池未初始化")
    return _source_engine

