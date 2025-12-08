"""
周期管理服务

管理画像统计周期：
- 自然周 (week): 周一到周日
- 自然月 (month): 每月1日到月末
- 自然季度 (quarter): 每季度首日到季末
"""

from datetime import date, timedelta
from typing import Literal

from dateutil.relativedelta import relativedelta
from loguru import logger
from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert

from src.core.database import get_portrait_db
from src.models.portrait.period import PeriodRegistry


PeriodType = Literal["week", "month", "quarter"]


def get_week_key(dt: date) -> str:
    """获取周编号，如 2024-W49"""
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def get_month_key(dt: date) -> str:
    """获取月编号，如 2024-11"""
    return dt.strftime("%Y-%m")


def get_quarter_key(dt: date) -> str:
    """获取季度编号，如 2024-Q4"""
    quarter = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{quarter}"


def get_week_range(dt: date) -> tuple[date, date]:
    """获取日期所在周的起止日期 (周一到周日)"""
    weekday = dt.weekday()
    start = dt - timedelta(days=weekday)
    end = start + timedelta(days=6)
    return start, end


def get_month_range(dt: date) -> tuple[date, date]:
    """获取日期所在月的起止日期"""
    start = dt.replace(day=1)
    end = (start + relativedelta(months=1)) - timedelta(days=1)
    return start, end


def get_quarter_range(dt: date) -> tuple[date, date]:
    """获取日期所在季度的起止日期"""
    quarter = (dt.month - 1) // 3
    start_month = quarter * 3 + 1
    start = date(dt.year, start_month, 1)
    end = (start + relativedelta(months=3)) - timedelta(days=1)
    return start, end


def get_period_range(period_type: PeriodType, period_key: str) -> tuple[date, date]:
    """
    根据周期类型和周期编号获取日期范围

    Args:
        period_type: 周期类型
        period_key: 周期编号

    Returns:
        (开始日期, 结束日期)
    """
    if period_type == "week":
        # 解析 2024-W49
        year, week = period_key.split("-W")
        year, week = int(year), int(week)
        first_day = date(year, 1, 4)  # ISO 周定义
        start = first_day + timedelta(weeks=week - 1)
        start = start - timedelta(days=start.weekday())
        end = start + timedelta(days=6)
        return start, end

    elif period_type == "month":
        # 解析 2024-11
        year, month = period_key.split("-")
        year, month = int(year), int(month)
        start = date(year, month, 1)
        end = (start + relativedelta(months=1)) - timedelta(days=1)
        return start, end

    elif period_type == "quarter":
        # 解析 2024-Q4
        year, q = period_key.split("-Q")
        year, q = int(year), int(q)
        start_month = (q - 1) * 3 + 1
        start = date(year, start_month, 1)
        end = (start + relativedelta(months=3)) - timedelta(days=1)
        return start, end

    raise ValueError(f"Unknown period type: {period_type}")


def get_period_label(period_type: PeriodType, period_key: str) -> str:
    """获取周期的中文标签"""
    if period_type == "week":
        year, week = period_key.split("-W")
        return f"{year}年第{week}周"
    elif period_type == "month":
        year, month = period_key.split("-")
        return f"{year}年{month}月"
    elif period_type == "quarter":
        year, q = period_key.split("-Q")
        return f"{year}年第{q}季度"
    return period_key


class PeriodService:
    """
    周期管理服务

    管理画像统计周期的注册和状态
    """

    async def get_available_periods(
        self,
        period_type: PeriodType,
        limit: int = 12,
    ) -> list[dict]:
        """
        获取可用的周期列表

        Args:
            period_type: 周期类型
            limit: 返回数量

        Returns:
            周期信息列表
        """
        # 生成最近的周期
        today = date.today()
        periods = []

        if period_type == "week":
            # 从上周开始向前
            current = today - timedelta(days=today.weekday() + 1)
            for _ in range(limit):
                start, end = get_week_range(current)
                key = get_week_key(current)
                periods.append(
                    {
                        "key": key,
                        "label": get_period_label("week", key),
                        "start": start,
                        "end": end,
                    }
                )
                current -= timedelta(weeks=1)

        elif period_type == "month":
            # 从上月开始向前
            current = today.replace(day=1) - timedelta(days=1)
            for _ in range(limit):
                start, end = get_month_range(current)
                key = get_month_key(current)
                periods.append(
                    {
                        "key": key,
                        "label": get_period_label("month", key),
                        "start": start,
                        "end": end,
                    }
                )
                current = start - timedelta(days=1)

        elif period_type == "quarter":
            # 从上季度开始向前
            quarter = (today.month - 1) // 3
            start_month = quarter * 3 + 1 if quarter > 0 else 10
            year = today.year if quarter > 0 else today.year - 1
            current = date(year, start_month, 1) - timedelta(days=1)

            for _ in range(limit):
                start, end = get_quarter_range(current)
                key = get_quarter_key(current)
                periods.append(
                    {
                        "key": key,
                        "label": get_period_label("quarter", key),
                        "start": start,
                        "end": end,
                    }
                )
                current = start - timedelta(days=1)

        # 查询已计算状态
        async for session in get_portrait_db():
            keys = [p["key"] for p in periods]
            result = await session.execute(
                select(PeriodRegistry.period_key, PeriodRegistry.status).where(
                    and_(
                        PeriodRegistry.period_type == period_type,
                        PeriodRegistry.period_key.in_(keys),
                    )
                )
            )
            status_map = {row.period_key: row.status for row in result}

            for p in periods:
                p["status"] = status_map.get(p["key"], "pending")

        return periods

    async def register_period(
        self,
        period_type: PeriodType,
        period_key: str,
    ) -> PeriodRegistry:
        """
        注册周期（如不存在）

        Args:
            period_type: 周期类型
            period_key: 周期编号

        Returns:
            周期记录
        """
        start, end = get_period_range(period_type, period_key)

        async for session in get_portrait_db():
            stmt = (
                insert(PeriodRegistry)
                .values(
                    period_type=period_type,
                    period_key=period_key,
                    period_start=start,
                    period_end=end,
                    status="pending",
                )
                .on_conflict_do_nothing(index_elements=["period_type", "period_key"])
            )
            await session.execute(stmt)
            await session.commit()

            # 返回记录
            result = await session.execute(
                select(PeriodRegistry).where(
                    and_(
                        PeriodRegistry.period_type == period_type,
                        PeriodRegistry.period_key == period_key,
                    )
                )
            )
            return result.scalar_one()

    async def update_period_status(
        self,
        period_type: PeriodType,
        period_key: str,
        status: str,
        **kwargs,
    ) -> None:
        """
        更新周期状态

        Args:
            period_type: 周期类型
            period_key: 周期编号
            status: 新状态
            **kwargs: 其他更新字段
        """
        from sqlalchemy import update

        async for session in get_portrait_db():
            stmt = (
                update(PeriodRegistry)
                .where(
                    and_(
                        PeriodRegistry.period_type == period_type,
                        PeriodRegistry.period_key == period_key,
                    )
                )
                .values(status=status, **kwargs)
            )
            await session.execute(stmt)
            await session.commit()

        logger.info(f"周期状态更新: {period_type}/{period_key} -> {status}")


# 全局服务实例
period_service = PeriodService()
