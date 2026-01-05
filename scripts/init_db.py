"""
Author: HeJia nicehejia@gmail.com
Date: 2025-12-04 14:48:18
LastEditors: HeJia nicehejia@gmail.com
LastEditTime: 2026-01-05 18:34:10
FilePath: /potrait/scripts/init_db.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
"""

"""
Author: HeJia nicehejia@gmail.com
Date: 2025-12-04 14:48:18
LastEditors: HeJia nicehejia@gmail.com
LastEditTime: 2025-12-23 14:55:30
FilePath: /potrait/scripts/init_db.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
"""

"""
Author: HeJia nicehejia@gmail.com
Date: 2025-12-04 14:48:18
LastEditors: HeJia nicehejia@gmail.com
LastEditTime: 2025-12-16 17:39:17
FilePath: /potrait/scripts/init_db.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
"""

#!/usr/bin/env python
"""
初始化数据库脚本

用法:
    python scripts/init_db.py
    
功能:
    1. 创建数据库表
    2. 初始化基础数据
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from sqlalchemy import text

from src.core.config import settings
from src.core.database import init_portrait_db, close_portrait_db, get_portrait_engine
from src.models.portrait.base import PortraitBase


async def create_tables():
    """创建所有表"""
    logger.info("开始创建数据库表...")

    await init_portrait_db()
    engine = get_portrait_engine()

    async with engine.begin() as conn:
        # 创建所有表
        await conn.run_sync(PortraitBase.metadata.create_all)

    logger.info("数据库表创建完成")


async def check_connection():
    """检查数据库连接"""
    logger.info(f"检查 PostgreSQL 连接: {settings.postgres_host}:{settings.postgres_port}")

    await init_portrait_db()
    engine = get_portrait_engine()

    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT version()"))
        version = result.scalar()
        logger.info(f"PostgreSQL 版本: {version}")

    return True


async def main():
    """主函数"""
    try:
        # 检查连接
        await check_connection()

        # 创建表
        await create_tables()

        logger.info("✅ 数据库初始化完成")

    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        raise
    finally:
        await close_portrait_db()


if __name__ == "__main__":
    asyncio.run(main())
