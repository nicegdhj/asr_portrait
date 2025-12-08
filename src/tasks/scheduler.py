"""
定时任务调度器

使用 APScheduler 管理定时任务：
- 每日凌晨同步前一天的通话记录
- 触发 LLM 分析任务
- 周期快照计算
"""

from datetime import date, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from src.core.config import settings


class TaskScheduler:
    """
    任务调度器

    管理系统中的所有定时任务
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
        self._initialized = False

    def init(self) -> None:
        """初始化调度器"""
        if self._initialized:
            return

        if not settings.scheduler_enabled:
            logger.info("定时任务调度器已禁用")
            return

        # 注册定时任务
        self._register_jobs()
        self._initialized = True
        logger.info("定时任务调度器初始化完成")

    def start(self) -> None:
        """启动调度器"""
        if not settings.scheduler_enabled:
            return

        if not self._initialized:
            self.init()

        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("定时任务调度器已启动")

    def shutdown(self) -> None:
        """关闭调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("定时任务调度器已关闭")

    def _register_jobs(self) -> None:
        """注册所有定时任务"""

        # 1. 每日数据同步任务 (凌晨2点)
        self.scheduler.add_job(
            self._job_sync_yesterday_records,
            trigger=CronTrigger(
                hour=settings.sync_cron_hour,
                minute=settings.sync_cron_minute,
            ),
            id="sync_call_records",
            name="同步通话记录",
            replace_existing=True,
        )
        logger.info(f"注册任务: 同步通话记录 @ {settings.sync_cron_hour:02d}:{settings.sync_cron_minute:02d}")

        # 2. LLM 分析任务 (凌晨2:30)
        self.scheduler.add_job(
            self._job_llm_analyze,
            trigger=CronTrigger(hour=2, minute=30),
            id="llm_analyze",
            name="LLM 分析通话记录",
            replace_existing=True,
        )
        logger.info("注册任务: LLM 分析 @ 02:30")

        # 3. 周期快照检查 (凌晨6点)
        self.scheduler.add_job(
            self._job_check_period_snapshot,
            trigger=CronTrigger(hour=6, minute=0),
            id="check_period_snapshot",
            name="检查并计算周期快照",
            replace_existing=True,
        )
        logger.info("注册任务: 周期快照检查 @ 06:00")

        # 4. 场景汇总计算 (凌晨6:30，在快照计算之后)
        self.scheduler.add_job(
            self._job_compute_task_summary,
            trigger=CronTrigger(hour=6, minute=30),
            id="compute_task_summary",
            name="计算场景汇总统计",
            replace_existing=True,
        )
        logger.info("注册任务: 场景汇总计算 @ 06:30")

    async def _job_sync_yesterday_records(self) -> None:
        """
        同步昨日通话记录

        T+1 策略：同步前一天的完整数据
        """
        from src.services.etl_service import etl_service

        yesterday = date.today() - timedelta(days=1)
        logger.info(f"[定时任务] 开始同步 {yesterday} 的通话记录")

        try:
            result = await etl_service.sync_call_records(yesterday)
            logger.info(f"[定时任务] 同步完成: {result}")
        except Exception as e:
            logger.error(f"[定时任务] 同步失败: {e}")

    async def _job_llm_analyze(self) -> None:
        """
        LLM 分析任务

        分析未处理的通话记录
        """
        from src.services.llm_service import llm_service

        logger.info("[定时任务] 开始 LLM 分析")

        try:
            result = await llm_service.analyze_pending_batch()
            logger.info(f"[定时任务] LLM 分析完成: {result}")
        except Exception as e:
            logger.error(f"[定时任务] LLM 分析失败: {e}")

    async def _job_check_period_snapshot(self) -> None:
        """
        检查并计算周期快照

        在周一计算上周快照
        在月初计算上月快照
        在季度初计算上季度快照
        """
        from src.services.portrait_service import portrait_service

        today = date.today()
        logger.info(f"[定时任务] 检查周期快照 (今日: {today})")

        try:
            # 检查是否需要计算周快照 (周一)
            if today.weekday() == 0:  # Monday
                await portrait_service.compute_weekly_snapshot()

            # 检查是否需要计算月快照 (1号)
            if today.day == 1:
                await portrait_service.compute_monthly_snapshot()

            # 检查是否需要计算季度快照 (季度首日)
            if today.month in [1, 4, 7, 10] and today.day == 1:
                await portrait_service.compute_quarterly_snapshot()

            logger.info("[定时任务] 周期快照检查完成")
        except Exception as e:
            logger.error(f"[定时任务] 周期快照计算失败: {e}")

    async def _job_compute_task_summary(self) -> None:
        """
        计算场景汇总统计

        在周快照计算后，聚合生成 task_portrait_summary
        """
        from src.services.portrait_service import portrait_service
        from src.services.period_service import get_week_key

        today = date.today()
        logger.info(f"[定时任务] 开始计算场景汇总 (今日: {today})")

        try:
            # 计算上周的场景汇总
            last_week = today - timedelta(days=7)
            week_key = get_week_key(last_week)

            result = await portrait_service.compute_task_summary("week", week_key)
            logger.info(f"[定时任务] 场景汇总完成: {result}")

        except Exception as e:
            logger.error(f"[定时任务] 场景汇总计算失败: {e}")

    # ==========================================
    # 手动触发接口
    # ===========================================

    async def trigger_sync(self, target_date: date) -> dict:
        """手动触发数据同步"""
        from src.services.etl_service import etl_service

        logger.info(f"[手动触发] 同步 {target_date} 的通话记录")
        return await etl_service.sync_call_records(target_date)

    async def trigger_llm_analyze(self, limit: int = 100) -> dict:
        """手动触发 LLM 分析"""
        from src.services.llm_service import llm_service

        logger.info(f"[手动触发] LLM 分析 (limit={limit})")
        return await llm_service.analyze_pending_batch(limit=limit)

    async def trigger_compute_snapshot(
        self,
        period_type: str,
        period_key: str,
    ) -> dict:
        """手动触发快照计算"""
        from src.services.portrait_service import portrait_service

        logger.info(f"[手动触发] 计算快照: {period_type}/{period_key}")
        return await portrait_service.compute_snapshot(period_type, period_key)


# 全局调度器实例
task_scheduler = TaskScheduler()
