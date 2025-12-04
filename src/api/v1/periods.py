"""
周期管理接口

提供可查询的周期列表
"""

from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select

from src.api.deps import PortraitDB
from src.models import PeriodRegistry
from src.schemas import ApiResponse, PeriodInfo, PeriodListResponse
from src.utils import get_recent_periods, get_period_range

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[PeriodListResponse],
    summary="获取可选周期列表",
    description="返回可查询的周/月/季度列表，按时间倒序排列",
)
async def list_periods(
    db: PortraitDB,
    type: Literal["week", "month", "quarter"] = Query(
        default="week",
        description="周期类型",
    ),
    limit: int = Query(
        default=12,
        ge=1,
        le=52,
        description="返回数量",
    ),
):
    """
    获取可选周期列表
    
    - **type**: 周期类型 (week/month/quarter)
    - **limit**: 返回数量，默认12
    
    返回已计算完成的周期列表，用于前端下拉选择
    """
    # 查询已计算完成的周期
    stmt = (
        select(PeriodRegistry)
        .where(PeriodRegistry.period_type == type)
        .where(PeriodRegistry.status == "completed")
        .order_by(PeriodRegistry.period_start.desc())
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    records = result.scalars().all()
    
    if records:
        # 从数据库返回
        periods = [
            PeriodInfo(
                key=r.period_key,
                label=r.label,
                start=r.period_start,
                end=r.period_end,
                status=r.status,
            )
            for r in records
        ]
    else:
        # 数据库为空时，返回理论周期列表 (状态为 pending)
        recent = get_recent_periods(type, limit, include_current=False)
        periods = [
            PeriodInfo(
                key=key,
                label=_get_label(type, key),
                start=start,
                end=end,
                status="pending",
            )
            for key, start, end in recent
        ]
    
    return ApiResponse.success(
        data=PeriodListResponse(type=type, periods=periods)
    )


@router.get(
    "/current",
    response_model=ApiResponse[PeriodInfo],
    summary="获取当前周期",
    description="返回当前正在进行的周期信息",
)
async def get_current_period(
    type: Literal["week", "month", "quarter"] = Query(
        default="week",
        description="周期类型",
    ),
):
    """获取当前周期信息（注意：当前周期通常未完成计算）"""
    from src.utils import get_current_week, get_current_month, get_current_quarter
    
    if type == "week":
        key, start, end = get_current_week()
    elif type == "month":
        key, start, end = get_current_month()
    else:
        key, start, end = get_current_quarter()
    
    return ApiResponse.success(
        data=PeriodInfo(
            key=key,
            label=_get_label(type, key),
            start=start,
            end=end,
            status="in_progress",
        )
    )


def _get_label(period_type: str, period_key: str) -> str:
    """获取周期标签"""
    if period_type == "week":
        year, week = period_key.split("-W")
        return f"{year}年第{int(week)}周"
    elif period_type == "month":
        year, month = period_key.split("-")
        return f"{year}年{int(month)}月"
    elif period_type == "quarter":
        year, q = period_key.split("-Q")
        return f"{year}年第{q}季度"
    return period_key

