"""
场景(任务)画像 API

提供按任务聚合的满意度、风险占比统计及趋势
"""

from __future__ import annotations

import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Path, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import Integer, distinct, func, select

from src.api.deps import PortraitDB
from src.models import CallRecordEnriched, TaskPortraitSummary, PeriodRegistry
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
    # 4个维度的统计
    satisfaction: dict = Field(default_factory=dict, description="满意度分布: satisfied/neutral/unsatisfied")
    risk: dict = Field(default_factory=dict, description="风险分布: high_churn/high_complaint/medium/none")
    emotion: dict = Field(default_factory=dict, description="情感分布: positive/neutral/negative")
    willingness: dict = Field(default_factory=dict, description="沟通意愿分布: deep/normal/low")


class TrendPoint(BaseModel):
    """趋势数据点"""

    period: str = Field(..., description="周期")
    value: float = Field(..., description="值")


class TaskTrendResponse(BaseModel):
    """任务趋势响应"""

    task_id: str = Field(..., description="任务ID")
    metric: str = Field(..., description="指标名称")
    series: list[TrendPoint] = Field(default_factory=list, description="趋势数据")


class AvailablePeriod(BaseModel):
    """可用周期"""

    period_type: str = Field(..., description="周期类型")
    period_key: str = Field(..., description="周期编号")
    total_users: int = Field(default=0, description="用户数")
    total_records: int = Field(default=0, description="记录数")


# ===========================================
# API Endpoints
# ===========================================


@router.get(
    "/periods",
    response_model=ApiResponse[list[AvailablePeriod]],
    summary="获取可用周期列表",
    description="获取已完成计算的周期列表，用于前端周期选择",
)
async def list_available_periods(
    db: PortraitDB,
    period_type: Literal["week", "month", "quarter"] = Query(default="week", description="周期类型"),
):
    """
    获取可用周期列表

    返回已完成计算且有数据的周期列表
    """
    stmt = (
        select(
            PeriodRegistry.period_type,
            PeriodRegistry.period_key,
            PeriodRegistry.total_users,
            PeriodRegistry.total_records,
        )
        .where(
            PeriodRegistry.period_type == period_type,
            PeriodRegistry.status == "completed",
            PeriodRegistry.total_users > 0,  # 只返回有数据的周期
        )
        .order_by(PeriodRegistry.period_key.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    periods = [
        AvailablePeriod(
            period_type=row.period_type,
            period_key=row.period_key,
            total_users=row.total_users or 0,
            total_records=row.total_records or 0,
        )
        for row in rows
    ]

    return ApiResponse.success(data=periods)


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
                    "medium": summary.medium_risk_customers,
                    "none": summary.no_risk_customers,
                },
                emotion={
                    "positive": summary.positive_count,
                    "positive_rate": summary.positive_rate,
                    "neutral": summary.neutral_emotion_count,
                    "negative": summary.negative_count,
                },
                willingness={
                    "deep": summary.deep_willingness_count,
                    "deep_rate": summary.deep_willingness_rate,
                    "normal": summary.normal_willingness_count,
                    "low": summary.low_willingness_count,
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
        "high_risk_rate",  # 综合风险率（投诉+流失）
        "positive_rate",  # 正向情感率
        "deep_willingness_rate",  # 深度沟通率
        "avg_duration",
    ] = Query(default="satisfied_rate", description="指标名称"),
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

    # 生成最近 limit 个周期的列表
    from datetime import date, timedelta

    def get_week_key(d: date) -> str:
        """获取日期对应的 ISO 周编号"""
        iso_year, iso_week, _ = d.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    # 从当前日期倒推生成周期列表
    today = date.today()
    all_periods = []
    current_date = today
    for _ in range(limit):
        week_key = get_week_key(current_date)
        if week_key not in all_periods:
            all_periods.append(week_key)
        if len(all_periods) >= limit:
            break
        current_date -= timedelta(days=7)

    # 按时间升序排列（旧→新）
    all_periods = list(reversed(all_periods))

    # 查询历史数据
    stmt = (
        select(
            TaskPortraitSummary.period_key,
            getattr(TaskPortraitSummary, metric),
        )
        .where(
            TaskPortraitSummary.task_id == task_uuid,
            TaskPortraitSummary.period_type == period_type,
            TaskPortraitSummary.period_key.in_(all_periods),
        )
        .order_by(TaskPortraitSummary.period_key)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 构建数据字典
    data_map = {row[0]: float(row[1] or 0) for row in rows}

    # 填充所有周期（没有数据的填 0）
    series = [TrendPoint(period=period, value=data_map.get(period, 0.0)) for period in all_periods]

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
    summary="获取场景列表",
    description="获取所有场景（任务）列表，用于前端场景选择",
)
async def list_tasks(
    db: PortraitDB,
    period_type: Literal["week", "month", "quarter"] = Query(default="week", description="周期类型"),
    period_key: Optional[str] = Query(default=None, description="周期编号，如 2025-W48，不传则返回所有场景"),
    limit: int = Query(default=50, description="返回数量", ge=1, le=200),
):
    """
    获取场景列表

    - 如果传入 period_key，返回该周期内有数据的场景及其客户数
    - 如果不传 period_key，返回所有有数据的场景
    """
    # 从 task_portrait_summary 获取场景数据（已按场景+周期聚合）
    if period_key:
        # 指定周期：从汇总表获取该周期的场景数据
        stmt = (
            select(
                TaskPortraitSummary.task_id,
                TaskPortraitSummary.task_name,
                TaskPortraitSummary.total_customers,
                TaskPortraitSummary.total_calls,
            )
            .where(
                TaskPortraitSummary.period_type == period_type,
                TaskPortraitSummary.period_key == period_key,
            )
            .order_by(TaskPortraitSummary.total_customers.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        rows = result.all()

        tasks = [
            {
                "task_id": str(row.task_id),
                "task_name": row.task_name,
                "customer_count": row.total_customers,
                "call_count": row.total_calls,
            }
            for row in rows
        ]
    else:
        # 不指定周期：从原始表统计所有场景
        # 先获取任务名称映射
        task_name_map = {}
        name_stmt = (
            select(TaskPortraitSummary.task_id, TaskPortraitSummary.task_name)
            .where(TaskPortraitSummary.task_name.isnot(None))
            .distinct(TaskPortraitSummary.task_id)
        )
        name_result = await db.execute(name_stmt)
        for row in name_result.all():
            task_name_map[str(row.task_id)] = row.task_name

        stmt = (
            select(
                CallRecordEnriched.task_id,
                func.count().label("call_count"),
                func.count(distinct(CallRecordEnriched.user_id)).label("customer_count"),
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
                "task_name": task_name_map.get(str(row.task_id)),
                "customer_count": row.customer_count,
                "call_count": row.call_count,
            }
            for row in rows
        ]

    return ApiResponse.success(data=tasks)


# ===========================================
# 客户列表相关
# ===========================================


class CustomerListItem(BaseModel):
    """客户列表项"""

    customer_id: str = Field(..., description="客户ID")
    phone: Optional[str] = Field(default=None, description="手机号")
    task_id: str = Field(..., description="任务ID")
    task_name: Optional[str] = Field(default=None, description="任务名称")
    total_calls: int = Field(default=0, description="总通话数")
    avg_duration: float = Field(default=0.0, description="平均通话时长(秒)")
    satisfaction: Optional[str] = Field(default=None, description="满意度: satisfied/neutral/unsatisfied")
    emotion: Optional[str] = Field(default=None, description="情感: positive/neutral/negative")
    risk_level: Optional[str] = Field(
        default=None, description="风险: churn(流失)/complaint(投诉)/medium(一般)/none(无)"
    )
    willingness: Optional[str] = Field(default=None, description="沟通意愿: 深度/一般/较低")


class CustomerListResponse(BaseModel):
    """客户列表响应"""

    list: List[CustomerListItem] = Field(default_factory=list, description="客户列表")
    total: int = Field(default=0, description="总数")
    page: int = Field(default=1, description="当前页")
    page_size: int = Field(default=15, description="每页数量")


@router.get(
    "/{task_id}/customers",
    response_model=ApiResponse[CustomerListResponse],
    summary="获取任务客户列表",
    description="获取指定任务的客户画像列表，支持分页和筛选",
)
async def get_task_customers(
    db: PortraitDB,
    task_id: str = Path(..., description="任务ID"),
    period_type: Literal["week", "month", "quarter"] = Query(default="week", description="周期类型"),
    period_key: str = Query(..., description="周期编号，如 2025-W48"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=15, ge=1, le=100, description="每页数量"),
    # 筛选参数
    phone: Optional[str] = Query(default=None, description="手机号搜索"),
    satisfaction: Optional[str] = Query(default=None, description="满意度筛选"),
    emotion: Optional[str] = Query(default=None, description="情感筛选"),
    risk_level: Optional[str] = Query(default=None, description="风险筛选"),
    willingness: Optional[str] = Query(default=None, description="沟通意愿筛选"),
):
    """
    获取任务客户列表

    返回指定任务在某周期内的客户画像数据，支持筛选
    """
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        return ApiResponse.error(code=400, message=f"无效的任务ID: {task_id}")

    from src.models import UserPortraitSnapshot

    # 获取任务名称
    task_name = None
    name_stmt = (
        select(TaskPortraitSummary.task_name)
        .where(TaskPortraitSummary.task_id == task_uuid, TaskPortraitSummary.task_name.isnot(None))
        .limit(1)
    )
    name_result = await db.execute(name_stmt)
    name_row = name_result.scalar_one_or_none()
    if name_row:
        task_name = name_row

    # 构建基础筛选条件
    base_conditions = [
        UserPortraitSnapshot.task_id == task_uuid,
        UserPortraitSnapshot.period_type == period_type,
        UserPortraitSnapshot.period_key == period_key,
    ]

    # 添加筛选条件
    if phone:
        base_conditions.append(UserPortraitSnapshot.phone.ilike(f"%{phone}%"))
    if satisfaction:
        base_conditions.append(UserPortraitSnapshot.final_satisfaction == satisfaction)
    if emotion:
        base_conditions.append(UserPortraitSnapshot.final_emotion == emotion)
    if risk_level:
        base_conditions.append(UserPortraitSnapshot.risk_level == risk_level)
    if willingness:
        base_conditions.append(UserPortraitSnapshot.willingness == willingness)

    # 计算去重后的客户总数（带筛选条件）
    count_stmt = (
        select(func.count(func.distinct(UserPortraitSnapshot.customer_id)))
        .select_from(UserPortraitSnapshot)
        .where(*base_conditions)
    )
    count_result = await db.execute(count_stmt)
    total = count_result.scalar() or 0

    # 分页查询客户画像快照（按 customer_id 去重，保留最新/最多通话的记录）
    offset = (page - 1) * page_size

    # 使用子查询按 customer_id 去重，聚合数据
    stmt = (
        select(
            UserPortraitSnapshot.customer_id,
            func.max(UserPortraitSnapshot.phone).label("phone"),
            func.sum(UserPortraitSnapshot.total_calls).label("total_calls"),
            func.avg(UserPortraitSnapshot.avg_duration).label("avg_duration"),
            # 综合字段（取最新）
            func.max(UserPortraitSnapshot.final_satisfaction).label("final_satisfaction"),
            func.max(UserPortraitSnapshot.final_emotion).label("final_emotion"),
            func.max(UserPortraitSnapshot.risk_level).label("risk_level"),
            func.max(UserPortraitSnapshot.willingness).label("willingness"),
        )
        .where(*base_conditions)
        .group_by(UserPortraitSnapshot.customer_id)
        .order_by(func.sum(UserPortraitSnapshot.total_calls).desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    snapshots = result.all()

    # 构建响应
    customers = []
    for s in snapshots:
        total_calls = s.total_calls or 0
        avg_duration = float(s.avg_duration or 0)

        customers.append(
            CustomerListItem(
                customer_id=s.customer_id,
                phone=s.phone,
                task_id=task_id,
                task_name=task_name,
                total_calls=total_calls,
                avg_duration=round(avg_duration, 2),
                satisfaction=s.final_satisfaction,
                emotion=s.final_emotion,
                risk_level=s.risk_level,
                willingness=s.willingness,
            )
        )

    return ApiResponse.success(
        data=CustomerListResponse(
            list=customers,
            total=total,
            page=page,
            page_size=page_size,
        )
    )
