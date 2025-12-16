#!/usr/bin/env python3
"""
重建数据脚本

1. 清空画像数据
2. 添加新字段到数据库表
3. 重新同步通话记录
4. 分析通话记录（满意度/情绪/风险）
5. 同步任务名称
6. 重新计算画像快照
"""

import asyncio
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import text

from src.core.database import get_portrait_db, init_portrait_db, close_portrait_db, init_source_db, close_source_db


async def clear_data():
    """清空画像数据"""
    logger.info("清空画像数据...")

    async for session in get_portrait_db():
        try:
            # 按依赖顺序清空
            await session.execute(text("TRUNCATE TABLE task_portrait_summary CASCADE"))
            await session.execute(text("TRUNCATE TABLE user_portrait_snapshot CASCADE"))
            await session.execute(text("TRUNCATE TABLE call_record_enriched CASCADE"))
            await session.execute(text("TRUNCATE TABLE period_registry CASCADE"))
            await session.commit()
            logger.info("数据清空完成")
        except Exception as e:
            logger.error(f"清空数据失败: {e}")
            await session.rollback()
            raise


async def add_new_columns():
    """添加新字段到数据库表"""
    logger.info("添加新字段...")

    async for session in get_portrait_db():
        try:
            # call_record_enriched 表
            await session.execute(text("""
                ALTER TABLE call_record_enriched
                ADD COLUMN IF NOT EXISTS phone VARCHAR(20),
                ADD COLUMN IF NOT EXISTS satisfaction VARCHAR(16),
                ADD COLUMN IF NOT EXISTS satisfaction_source VARCHAR(16),
                ADD COLUMN IF NOT EXISTS willingness VARCHAR(16),
                ADD COLUMN IF NOT EXISTS risk_level VARCHAR(16)
            """))

            # user_portrait_snapshot 表
            await session.execute(text("""
                ALTER TABLE user_portrait_snapshot
                ADD COLUMN IF NOT EXISTS phone VARCHAR(20),
                ADD COLUMN IF NOT EXISTS satisfied_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS neutral_satisfaction_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS unsatisfied_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS final_satisfaction VARCHAR(16),
                ADD COLUMN IF NOT EXISTS final_emotion VARCHAR(16),
                ADD COLUMN IF NOT EXISTS willingness VARCHAR(16),
                ADD COLUMN IF NOT EXISTS willingness_deep_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS willingness_normal_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS willingness_low_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS risk_level VARCHAR(16),
                ADD COLUMN IF NOT EXISTS risk_churn_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS risk_complaint_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS risk_medium_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS risk_none_count INTEGER DEFAULT 0
            """))

            # task_portrait_summary 表
            await session.execute(text("""
                ALTER TABLE task_portrait_summary
                ADD COLUMN IF NOT EXISTS medium_risk_customers INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS no_risk_customers INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS high_risk_rate FLOAT DEFAULT 0.0,
                ADD COLUMN IF NOT EXISTS neutral_emotion_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS positive_rate FLOAT DEFAULT 0.0,
                ADD COLUMN IF NOT EXISTS deep_willingness_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS normal_willingness_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS low_willingness_count INTEGER DEFAULT 0,
                ADD COLUMN IF NOT EXISTS deep_willingness_rate FLOAT DEFAULT 0.0
            """))

            await session.commit()
            logger.info("字段添加完成")
        except Exception as e:
            # 某些字段可能已存在，忽略错误
            logger.warning(f"添加字段时出现警告（可忽略）: {e}")
            await session.rollback()


async def sync_call_records():
    """重新同步通话记录（含分析）"""
    from src.services.etl_service import etl_service

    logger.info("开始重新同步通话记录（包含 ASR 分析）...")

    # 同步整个 11 月的数据（2025-11-01 到 2025-12-04）
    start_date = date(2025, 11, 1)
    end_date = date(2025, 12, 4)
    
    current_date = start_date
    total_synced = 0
    total_analyzed = 0
    
    while current_date <= end_date:
        try:
            result = await etl_service.sync_call_records(current_date)
            synced = result.get("synced", 0)
            if synced > 0:
                total_synced += synced
                logger.info(f"{current_date}: 同步 {synced} 条记录")
        except Exception as e:
            logger.warning(f"{current_date}: 同步失败 - {e}")
        current_date += timedelta(days=1)
    
    logger.info(f"通话记录同步完成，共 {total_synced} 条")


async def sync_task_names():
    """同步任务名称"""
    from src.services.etl_service import etl_service

    logger.info("开始同步任务名称...")

    try:
        result = await etl_service.sync_task_names()
        logger.info(f"任务名称同步完成: {result}")
    except Exception as e:
        logger.error(f"任务名称同步失败: {e}")


async def recompute_portraits():
    """重新计算画像"""
    from src.services.portrait_service import portrait_service

    logger.info("开始重新计算画像（含满意度和沟通意愿综合）...")

    # 计算 11 月相关的所有周期（W44 到 W49）
    periods = ["2025-W44", "2025-W45", "2025-W46", "2025-W47", "2025-W48", "2025-W49"]

    for period_key in periods:
        try:
            logger.info(f"计算周期: {period_key}")
            result = await portrait_service.compute_snapshot("week", period_key)
            customers = result.get('customers', 0)
            records = result.get('records', 0)
            logger.info(f"  -> 用户: {customers}, 记录: {records}")

            # 计算场景汇总
            await portrait_service.compute_task_summary("week", period_key)
        except Exception as e:
            logger.warning(f"计算失败 {period_key}: {e}")


async def print_stats():
    """打印统计信息"""
    logger.info("统计信息:")
    
    async for session in get_portrait_db():
        # 通话记录统计
        result = await session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(satisfaction) as with_satisfaction,
                COUNT(CASE WHEN satisfaction = 'satisfied' THEN 1 END) as satisfied,
                COUNT(CASE WHEN satisfaction = 'unsatisfied' THEN 1 END) as unsatisfied,
                COUNT(CASE WHEN risk_level = 'churn' THEN 1 END) as churn_risk,
                COUNT(CASE WHEN risk_level = 'complaint' THEN 1 END) as complaint_risk,
                COUNT(CASE WHEN sentiment = 'positive' THEN 1 END) as positive,
                COUNT(CASE WHEN sentiment = 'negative' THEN 1 END) as negative,
                COUNT(CASE WHEN willingness = '深度' THEN 1 END) as deep_willingness
            FROM call_record_enriched
        """))
        row = result.fetchone()
        logger.info(f"  通话记录: {row.total} 条")
        logger.info(f"  - 有满意度数据: {row.with_satisfaction} 条")
        logger.info(f"  - 满意: {row.satisfied}, 不满意: {row.unsatisfied}")
        logger.info(f"  - 流失风险: {row.churn_risk}, 投诉风险: {row.complaint_risk}")
        logger.info(f"  - 正向情感: {row.positive}, 负向情感: {row.negative}")
        logger.info(f"  - 深度沟通: {row.deep_willingness}")
        
        # 画像快照统计
        result = await session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(final_satisfaction) as with_satisfaction,
                COUNT(final_emotion) as with_emotion,
                COUNT(risk_level) as with_risk,
                COUNT(willingness) as with_willingness
            FROM user_portrait_snapshot
        """))
        row = result.fetchone()
        logger.info(f"  画像快照: {row.total} 条")
        logger.info(f"  - 有最终满意度: {row.with_satisfaction} 条")
        logger.info(f"  - 有最终情感: {row.with_emotion} 条")
        logger.info(f"  - 有风险等级: {row.with_risk} 条")
        logger.info(f"  - 有沟通意愿: {row.with_willingness} 条")


async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始重建数据（含规则引擎分析）...")
    logger.info("=" * 60)

    # 初始化数据库连接
    await init_portrait_db()
    await init_source_db()

    try:
        # 1. 清空数据
        await clear_data()
        
        # 2. 添加新字段
        await add_new_columns()

        # 3. 重新同步通话记录（含 ASR 分析）
        await sync_call_records()

        # 4. 重新计算画像
        await recompute_portraits()
        
        # 5. 同步任务名称
        await sync_task_names()
        
        # 6. 打印统计
        await print_stats()

        logger.info("=" * 60)
        logger.info("数据重建完成!")
        logger.info("=" * 60)

    finally:
        await close_portrait_db()
        await close_source_db()


if __name__ == "__main__":
    asyncio.run(main())
