"""
场景(任务)画像 API

提供按任务聚合的满意度、风险占比统计及趋势
"""

import uuid
from typing import Literal

from fastapi import APIRouter, Path, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import Integer, distinct, func, select

from src.api.deps import PortraitDB
from src.models import CallRecordEnriched, TaskPortraitSummary
from src.schemas import ApiResponse

router = APIRouter()


# ===========================================
# Schemas
# ===========================================


class TaskSummaryResponse(BaseModel):
    """任务汇总响应"""

    task_id: str = Field(..., description="任务ID")
    task_name: str | None = Field(default=None, description="任务名称")
    period_type: str = Field(..., description="周期类型")
    period_key: str = Field(..., description="周期编号")
    total_customers: int = Field(default=0, description="总客户数")
    total_calls: int = Field(default=0, description="总通话数")
    connected_calls: int = Field(default=0, description="接通数")
    connect_rate: float = Field(default=0.0, description="接通率")
    avg_duration: float = Field(default=0.0, description="平均通话时长(秒)")
    satisfaction: dict = Field(default_factory=dict, description="满意度分布")
    risk: dict = Field(default_factory=dict, description="风险分布")


class TrendPoint(BaseModel):
    """趋势数据点"""

    period: str = Field(..., description="周期")
    value: float = Field(..., description="值")


class TaskTrendResponse(BaseModel):
    """任务趋势响应"""

    task_id: str = Field(..., description="任务ID")
    metric: str = Field(..., description="指标名称")
    series: list[TrendPoint] = Field(default_factory=list, description="趋势数据")


# ===========================================
# API Endpoints
# ===========================================


@router.get(
    "/{task_id}/summary",
    response_model=ApiResponse[TaskSummaryResponse],
    summary="获取任务汇总统计",
    description="获取指定任务在某周期的满意度、风险占比等汇总统计",
)
async def get_task_summary(
    db: PortraitDB,
    task_id: str = Path(..., description="任务ID"),
    period_type: Literal["week", "month", "quarter"] = Query(default="week", description="周期类型"),
    period_key: str = Query(..., description="周期编号，如 2025-W48"),
):
    """
    获取任务汇总统计

    - **task_id**: 任务UUID
    - **period_type**: 周期类型 (week/month/quarter)
    - **period_key**: 周期编号
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return ApiResponse.error(code=400, message=f"无效的任务ID: {task_id}")

    # 查找已计算的汇总
    stmt = select(TaskPortraitSummary).where(
        TaskPortraitSummary.task_id == task_uuid,
        TaskPortraitSummary.period_type == period_type,
        TaskPortraitSummary.period_key == period_key,
    )
    result = await db.execute(stmt)
    summary = result.scalar_one_or_none()

    if summary:
        return ApiResponse.success(
            data=TaskSummaryResponse(
                task_id=str(summary.task_id),
                task_name=summary.task_name,
                period_type=summary.period_type,
                period_key=summary.period_key,
                total_customers=summary.total_customers,
                total_calls=summary.total_calls,
                connected_calls=summary.connected_calls,
                connect_rate=summary.connect_rate,
                avg_duration=summary.avg_duration,
                satisfaction={
                    "satisfied": summary.satisfied_count,
                    "satisfied_rate": summary.satisfied_rate,
                    "neutral": summary.neutral_count,
                    "unsatisfied": summary.unsatisfied_count,
                },
                risk={
                    "high_complaint": summary.high_complaint_customers,
                    "high_complaint_rate": summary.high_complaint_rate,
                    "high_churn": summary.high_churn_customers,
                    "high_churn_rate": summary.high_churn_rate,
                },
            )
        )

    # 如果没有预计算数据，实时聚合
    logger.info(f"实时聚合任务统计: {task_id}/{period_type}/{period_key}")

    from src.services.period_service import get_period_range

    try:
        start_date, end_date = get_period_range(period_type, period_key)
    except (ValueError, Exception) as e:
        return ApiResponse.error(code=400, message=f"无效的周期: {period_key} - {e}")

    # 实时统计
    stmt = select(
        func.count(distinct(CallRecordEnriched.user_id)).label("customers"),
        func.count().label("calls"),
        func.sum(func.cast(CallRecordEnriched.call_status == "connected", Integer)).label("connected"),
        func.avg(CallRecordEnriched.bill / 1000.0).label("avg_duration"),
    ).where(
        CallRecordEnriched.task_id == task_uuid,
        CallRecordEnriched.call_date >= start_date,
        CallRecordEnriched.call_date <= end_date,
    )
    result = await db.execute(stmt)
    row = result.one()

    total_customers = row.customers or 0
    total_calls = row.calls or 0
    connected_calls = row.connected or 0
    avg_duration = float(row.avg_duration or 0)

    return ApiResponse.success(
        data=TaskSummaryResponse(
            task_id=task_id,
            task_name=None,
            period_type=period_type,
            period_key=period_key,
            total_customers=total_customers,
            total_calls=total_calls,
            connected_calls=connected_calls,
            connect_rate=connected_calls / total_calls if total_calls > 0 else 0,
            avg_duration=avg_duration,
            satisfaction={
                "satisfied": 0,
                "satisfied_rate": 0,
                "neutral": 0,
                "unsatisfied": 0,
            },
            risk={
                "high_complaint": 0,
                "high_complaint_rate": 0,
                "high_churn": 0,
                "high_churn_rate": 0,
            },
        )
    )


@router.get(
    "/{task_id}/trend",
    response_model=ApiResponse[TaskTrendResponse],
    summary="获取任务指标趋势",
    description="获取指定任务某指标的历史趋势数据",
)
async def get_task_trend(
    db: PortraitDB,
    task_id: str = Path(..., description="任务ID"),
    period_type: Literal["week", "month", "quarter"] = Query(default="week", description="周期类型"),
    metric: Literal[
        "connect_rate",
        "satisfied_rate",
        "high_complaint_rate",
        "high_churn_rate",
        "avg_duration",
    ] = Query(default="connect_rate", description="指标名称"),
    limit: int = Query(default=12, description="返回周期数", ge=1, le=52),
):
    """
    获取任务指标趋势

    - **task_id**: 任务UUID
    - **period_type**: 周期类型
    - **metric**: 指标名称
    - **limit**: 返回最近多少个周期
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return ApiResponse.error(code=400, message=f"无效的任务ID: {task_id}")

    # 查询历史数据
    stmt = (
        select(
            TaskPortraitSummary.period_key,
            getattr(TaskPortraitSummary, metric),
        )
        .where(
            TaskPortraitSummary.task_id == task_uuid,
            TaskPortraitSummary.period_type == period_type,
        )
        .order_by(TaskPortraitSummary.period_key.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 倒序排列（时间升序）
    series = [TrendPoint(period=row[0], value=float(row[1] or 0)) for row in reversed(rows)]

    return ApiResponse.success(
        data=TaskTrendResponse(
            task_id=task_id,
            metric=metric,
            series=series,
        )
    )


@router.get(
    "",
    response_model=ApiResponse[list[dict]],
    summary="获取任务列表",
    description="获取所有有通话记录的任务列表",
)
async def list_tasks(
    db: PortraitDB,
    limit: int = Query(default=50, description="返回数量", ge=1, le=200),
):
    """获取任务列表"""
    stmt = (
        select(
            CallRecordEnriched.task_id,
            func.count().label("call_count"),
            func.count(distinct(CallRecordEnriched.user_id)).label("customer_count"),
            func.min(CallRecordEnriched.call_date).label("first_call"),
            func.max(CallRecordEnriched.call_date).label("last_call"),
        )
        .group_by(CallRecordEnriched.task_id)
        .order_by(func.count().desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    tasks = [
        {
            "task_id": str(row.task_id),
            "call_count": row.call_count,
            "customer_count": row.customer_count,
            "first_call": str(row.first_call),
            "last_call": str(row.last_call),
        }
        for row in rows
    ]

    return ApiResponse.success(data=tasks)
