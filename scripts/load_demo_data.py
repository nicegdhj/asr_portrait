"""
加载演示数据

为新用户提供示例数据,便于体验系统功能
"""

import asyncio
import uuid
from datetime import date, datetime, timedelta

from loguru import logger

from src.core.database import get_portrait_db, init_portrait_db, close_portrait_db
from src.models.portrait.call_enriched import CallRecordEnriched
from src.models.portrait.snapshot import UserPortraitSnapshot
from src.models.portrait.task_summary import TaskPortraitSummary
from src.services.period_service import period_service


async def load_demo_data():
    """加载演示数据"""
    logger.info("开始加载演示数据...")

    await init_portrait_db()

    # 创建示例任务
    demo_task_id = uuid.uuid4()
    demo_task_name = "演示场景 - 客户满意度调查"

    # 创建示例通话记录
    demo_calls = []
    base_date = date.today() - timedelta(days=7)

    for i in range(50):
        call_date = base_date + timedelta(days=i % 7)
        demo_calls.append(
            CallRecordEnriched(
                callid=f"demo_call_{i:03d}",
                task_id=demo_task_id,
                user_id=f"customer_{i % 20:03d}",  # 20个客户
                phone=f"138{i:08d}",
                call_date=call_date,
                duration=60 + (i % 120) * 10,  # 60-1260秒
                bill=50 + (i % 100) * 10,  # 50-1050秒
                rounds=3 + (i % 8),  # 3-10轮
                call_status="connected",
                satisfaction=["satisfied", "neutral", "unsatisfied"][i % 3],
                emotion=["positive", "neutral", "negative"][i % 3],
                risk_level=["none", "medium", "high"][i % 3],
                willingness=["深度", "一般", "较低"][i % 3],
            )
        )

    # 批量插入
    async for session in get_portrait_db():
        session.add_all(demo_calls)
        await session.commit()
        logger.info(f"已插入 {len(demo_calls)} 条演示通话记录")

    # 注册周期
    current_week = period_service.get_current_week()
    await period_service.register_period("week", current_week)
    logger.info(f"已注册周期: {current_week}")

    # 创建画像快照 (简化版,实际应该通过 portrait_service 计算)
    snapshots = []
    for customer_id in [f"customer_{i:03d}" for i in range(20)]:
        snapshots.append(
            UserPortraitSnapshot(
                customer_id=customer_id,
                task_id=demo_task_id,
                period_type="week",
                period_key=current_week,
                phone=f"138{customer_id[-3:]}00000",
                total_calls=2 + (int(customer_id[-3:]) % 3),
                connected_calls=2,
                avg_duration=300 + (int(customer_id[-3:]) % 10) * 30,
                avg_rounds=5,
                final_satisfaction=["satisfied", "neutral", "unsatisfied"][int(customer_id[-3:]) % 3],
                final_emotion=["positive", "neutral", "negative"][int(customer_id[-3:]) % 3],
                risk_level=["none", "medium", "high"][int(customer_id[-3:]) % 3],
                willingness=["深度", "一般", "较低"][int(customer_id[-3:]) % 3],
            )
        )

    async for session in get_portrait_db():
        session.add_all(snapshots)
        await session.commit()
        logger.info(f"已插入 {len(snapshots)} 条画像快照")

    # 创建场景汇总
    summary = TaskPortraitSummary(
        task_id=demo_task_id,
        task_name=demo_task_name,
        period_type="week",
        period_key=current_week,
        total_customers=20,
        total_calls=50,
        avg_duration=450,
        satisfied_count=7,
        neutral_satisfaction_count=7,
        unsatisfied_count=6,
        positive_count=7,
        neutral_emotion_count=7,
        negative_count=6,
        high_risk_count=7,
        medium_risk_count=6,
        no_risk_count=7,
        deep_willingness_count=7,
        normal_willingness_count=7,
        low_willingness_count=6,
    )

    async for session in get_portrait_db():
        session.add(summary)
        await session.commit()
        logger.info("已插入场景汇总")

    await close_portrait_db()

    logger.info("✅ 演示数据加载完成!")
    logger.info(f"演示任务ID: {demo_task_id}")
    logger.info(f"演示任务名称: {demo_task_name}")
    logger.info(f"统计周期: {current_week}")
    logger.info("")
    logger.info("现在可以访问前端查看演示数据:")
    logger.info("  http://localhost:3001")


if __name__ == "__main__":
    asyncio.run(load_demo_data())
