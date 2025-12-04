"""
管理接口

提供手动触发计算、系统状态等管理功能
"""

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.api.deps import PortraitDB
from src.models import PeriodRegistry, UserPortraitSnapshot, CallRecordEnriched
from src.schemas import ApiResponse

router = APIRouter()


class SystemStatus(BaseModel):
    """系统状态"""

    status: str = Field(default="healthy", description="系统状态")
    database: str = Field(default="connected", description="数据库状态")
    total_periods: int = Field(default=0, description="已计算周期数")
    total_snapshots: int = Field(default=0, description="画像快照总数")
    total_enriched_records: int = Field(default=0, description="增强记录总数")
    last_compute_time: Optional[datetime] = Field(default=None, description="最后计算时间")


class ComputeRequest(BaseModel):
    """计算请求"""

    period_type: Literal["week", "month", "quarter"] = Field(..., description="周期类型")
    period_key: str = Field(..., description="周期编号")
    force: bool = Field(default=False, description="是否强制重新计算")


class ComputeResponse(BaseModel):
    """计算响应"""

    task_id: str = Field(..., description="任务ID")
    status: str = Field(default="submitted", description="状态")
    message: str = Field(default="", description="消息")


@router.get(
    "/status",
    response_model=ApiResponse[SystemStatus],
    summary="获取系统状态",
    description="返回系统运行状态和统计信息",
)
async def get_system_status(db: PortraitDB):
    """获取系统状态"""
    try:
        # 统计已计算周期数
        stmt = select(func.count()).select_from(PeriodRegistry).where(PeriodRegistry.status == "completed")
        result = await db.execute(stmt)
        total_periods = result.scalar() or 0

        # 统计画像快照数
        stmt = select(func.count()).select_from(UserPortraitSnapshot)
        result = await db.execute(stmt)
        total_snapshots = result.scalar() or 0

        # 统计增强记录数
        stmt = select(func.count()).select_from(CallRecordEnriched)
        result = await db.execute(stmt)
        total_enriched = result.scalar() or 0

        # 获取最后计算时间
        stmt = (
            select(PeriodRegistry.computed_at)
            .where(PeriodRegistry.status == "completed")
            .order_by(PeriodRegistry.computed_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        last_compute = result.scalar()

        return ApiResponse.success(
            data=SystemStatus(
                status="healthy",
                database="connected",
                total_periods=total_periods,
                total_snapshots=total_snapshots,
                total_enriched_records=total_enriched,
                last_compute_time=last_compute,
            )
        )
    except Exception as e:
        return ApiResponse.success(
            data=SystemStatus(
                status="unhealthy",
                database=f"error: {str(e)}",
            )
        )


@router.post(
    "/compute",
    response_model=ApiResponse[ComputeResponse],
    summary="手动触发计算",
    description="手动触发指定周期的画像计算",
)
async def trigger_compute(
    request: ComputeRequest,
    background_tasks: BackgroundTasks,
    db: PortraitDB,
):
    """
    手动触发计算

    - **period_type**: 周期类型
    - **period_key**: 周期编号
    - **force**: 是否强制重新计算
    """
    import uuid

    # 检查是否已计算
    stmt = select(PeriodRegistry).where(
        PeriodRegistry.period_type == request.period_type,
        PeriodRegistry.period_key == request.period_key,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing and existing.status == "completed" and not request.force:
        return ApiResponse.success(
            data=ComputeResponse(
                task_id="",
                status="skipped",
                message=f"周期 {request.period_key} 已计算完成，如需重新计算请设置 force=true",
            )
        )

    if existing and existing.status == "computing":
        return ApiResponse.success(
            data=ComputeResponse(
                task_id="",
                status="in_progress",
                message=f"周期 {request.period_key} 正在计算中，请稍后查看",
            )
        )

    # 生成任务ID
    task_id = str(uuid.uuid4())

    # TODO: 添加后台计算任务
    # background_tasks.add_task(
    #     compute_period_snapshot,
    #     request.period_type,
    #     request.period_key,
    #     task_id,
    # )

    return ApiResponse.success(
        data=ComputeResponse(
            task_id=task_id,
            status="submitted",
            message=f"计算任务已提交，周期: {request.period_key}",
        )
    )


@router.get(
    "/periods/status",
    response_model=ApiResponse[dict],
    summary="获取周期计算状态",
    description="返回各周期的计算状态统计",
)
async def get_periods_status(
    db: PortraitDB,
    period_type: Literal["week", "month", "quarter"] = Query(
        default="week",
        description="周期类型",
    ),
):
    """获取周期计算状态统计"""
    # 按状态统计
    stmt = (
        select(PeriodRegistry.status, func.count())
        .where(PeriodRegistry.period_type == period_type)
        .group_by(PeriodRegistry.status)
    )
    result = await db.execute(stmt)
    status_counts = {row[0]: row[1] for row in result.all()}

    return ApiResponse.success(
        data={
            "period_type": period_type,
            "status_counts": status_counts,
            "total": sum(status_counts.values()),
        }
    )
