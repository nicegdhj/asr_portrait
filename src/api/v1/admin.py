"""
管理接口

提供手动触发计算、数据同步、LLM 分析等管理功能
"""

from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from src.api.deps import PortraitDB
from src.models import CallRecordEnriched, PeriodRegistry, UserPortraitSnapshot
from src.schemas import ApiResponse

router = APIRouter()


class SystemStatus(BaseModel):
    """系统状态"""

    status: str = Field(default="healthy", description="系统状态")
    database: str = Field(default="connected", description="数据库状态")
    source_db: str = Field(default="unknown", description="源数据库状态")
    total_periods: int = Field(default=0, description="已计算周期数")
    total_snapshots: int = Field(default=0, description="画像快照总数")
    total_enriched_records: int = Field(default=0, description="增强记录总数")
    llm_analyzed_records: int = Field(default=0, description="已分析记录数")
    last_compute_time: Optional[datetime] = Field(default=None, description="最后计算时间")


class SyncRequest(BaseModel):
    """数据同步请求"""

    date: str = Field(..., description="同步日期 (YYYY-MM-DD)")


class SyncResponse(BaseModel):
    """数据同步响应"""

    status: str = Field(..., description="状态")
    synced: int = Field(default=0, description="同步记录数")
    date: str = Field(..., description="同步日期")
    message: str = Field(default="", description="消息")


class AnalyzeRequest(BaseModel):
    """LLM 分析请求"""

    limit: int = Field(default=100, description="最大分析数量", ge=1, le=1000)


class AnalyzeResponse(BaseModel):
    """LLM 分析响应"""

    status: str = Field(..., description="状态")
    analyzed: int = Field(default=0, description="已分析数量")
    skipped: int = Field(default=0, description="跳过数量")
    errors: int = Field(default=0, description="错误数量")


class ComputeRequest(BaseModel):
    """计算请求"""

    period_type: Literal["week", "month", "quarter"] = Field(..., description="周期类型")
    period_key: str = Field(..., description="周期编号")
    force: bool = Field(default=False, description="是否强制重新计算")


class ComputeResponse(BaseModel):
    """计算响应"""

    status: str = Field(..., description="状态")
    period_type: str = Field(default="", description="周期类型")
    period_key: str = Field(default="", description="周期编号")
    users: int = Field(default=0, description="用户数")
    records: int = Field(default=0, description="记录数")
    message: str = Field(default="", description="消息")


@router.get(
    "/status",
    response_model=ApiResponse[SystemStatus],
    summary="获取系统状态",
    description="返回系统运行状态和统计信息",
)
async def get_system_status(db: PortraitDB):
    """获取系统状态"""
    from src.core.database import is_source_db_available

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

        # 统计已分析记录数
        stmt = (
            select(func.count()).select_from(CallRecordEnriched).where(CallRecordEnriched.llm_analyzed_at.isnot(None))
        )
        result = await db.execute(stmt)
        llm_analyzed = result.scalar() or 0

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
                source_db="connected" if is_source_db_available() else "disconnected",
                total_periods=total_periods,
                total_snapshots=total_snapshots,
                total_enriched_records=total_enriched,
                llm_analyzed_records=llm_analyzed,
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
    "/sync",
    response_model=ApiResponse[SyncResponse],
    summary="手动触发数据同步",
    description="从源数据库同步指定日期的通话记录",
)
async def trigger_sync(request: SyncRequest):
    """
    手动触发数据同步

    - **date**: 同步日期，格式 YYYY-MM-DD
    """
    from src.services.etl_service import etl_service

    try:
        target_date = date.fromisoformat(request.date)
    except ValueError:
        return ApiResponse.error(
            code=400,
            message=f"日期格式错误: {request.date}，应为 YYYY-MM-DD",
        )

    logger.info(f"[API] 手动触发数据同步: {target_date}")

    try:
        result = await etl_service.sync_call_records(target_date)
        return ApiResponse.success(
            data=SyncResponse(
                status=result.get("status", "unknown"),
                synced=result.get("synced", 0),
                date=str(target_date),
                message=result.get("reason", ""),
            )
        )
    except Exception as e:
        logger.error(f"数据同步失败: {e}")
        return ApiResponse.error(code=500, message=f"同步失败: {str(e)}")


@router.post(
    "/analyze",
    response_model=ApiResponse[AnalyzeResponse],
    summary="手动触发 LLM 分析",
    description="对未分析的通话记录进行 LLM 情感/风险分析",
)
async def trigger_analyze(request: AnalyzeRequest):
    """
    手动触发 LLM 分析

    - **limit**: 最大分析数量
    """
    from src.services.llm_service import llm_service

    logger.info(f"[API] 手动触发 LLM 分析: limit={request.limit}")

    try:
        result = await llm_service.analyze_pending_batch(limit=request.limit)
        return ApiResponse.success(
            data=AnalyzeResponse(
                status=result.get("status", "unknown"),
                analyzed=result.get("analyzed", 0),
                skipped=result.get("skipped", 0),
                errors=result.get("errors", 0),
            )
        )
    except Exception as e:
        logger.error(f"LLM 分析失败: {e}")
        return ApiResponse.error(code=500, message=f"分析失败: {str(e)}")


@router.post(
    "/compute",
    response_model=ApiResponse[ComputeResponse],
    summary="手动触发画像计算",
    description="手动触发指定周期的画像计算",
)
async def trigger_compute(
    request: ComputeRequest,
    db: PortraitDB,
):
    """
    手动触发画像计算

    - **period_type**: 周期类型 (week/month/quarter)
    - **period_key**: 周期编号
    - **force**: 是否强制重新计算
    """
    from src.services.portrait_service import portrait_service

    # 检查是否已计算
    if not request.force:
        stmt = select(PeriodRegistry).where(
            PeriodRegistry.period_type == request.period_type,
            PeriodRegistry.period_key == request.period_key,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing and existing.status == "completed":
            return ApiResponse.success(
                data=ComputeResponse(
                    status="skipped",
                    period_type=request.period_type,
                    period_key=request.period_key,
                    message=f"周期 {request.period_key} 已计算完成，如需重新计算请设置 force=true",
                )
            )

        if existing and existing.status == "computing":
            return ApiResponse.success(
                data=ComputeResponse(
                    status="in_progress",
                    period_type=request.period_type,
                    period_key=request.period_key,
                    message=f"周期 {request.period_key} 正在计算中",
                )
            )

    logger.info(f"[API] 手动触发画像计算: {request.period_type}/{request.period_key}")

    try:
        result = await portrait_service.compute_snapshot(
            request.period_type,
            request.period_key,
        )
        return ApiResponse.success(
            data=ComputeResponse(
                status=result.get("status", "unknown"),
                period_type=result.get("period_type", request.period_type),
                period_key=result.get("period_key", request.period_key),
                users=result.get("users", result.get("customers", 0)),
                records=result.get("records", 0),
            )
        )
    except Exception as e:
        logger.error(f"画像计算失败: {e}")
        return ApiResponse.error(code=500, message=f"计算失败: {str(e)}")


@router.post(
    "/compute-task-summary",
    response_model=ApiResponse[dict],
    summary="计算场景汇总",
    description="手动触发场景汇总统计计算",
)
async def trigger_task_summary(request: ComputeRequest):
    """
    手动触发场景汇总计算

    - **period_type**: 周期类型 (week/month/quarter)
    - **period_key**: 周期编号
    """
    from src.services.portrait_service import portrait_service

    try:
        result = await portrait_service.compute_task_summary(
            request.period_type,
            request.period_key,
        )
        return ApiResponse.success(data=result)
    except Exception as e:
        logger.error(f"场景汇总计算失败: {e}")
        return ApiResponse.error(code=500, message=f"计算失败: {str(e)}")


@router.post(
    "/sync-task-names",
    response_model=ApiResponse[dict],
    summary="同步任务名称",
    description="从源数据库同步任务名称到画像系统",
)
async def sync_task_names():
    """
    同步任务名称

    从源数据库的 autodialer_task 表读取任务名称，更新到 task_portrait_summary 表
    """
    from src.services.etl_service import etl_service

    logger.info("[API] 手动触发任务名称同步")

    try:
        result = await etl_service.sync_task_names()
        return ApiResponse.success(data=result)
    except Exception as e:
        logger.error(f"任务名称同步失败: {e}")
        return ApiResponse.error(code=500, message=f"同步失败: {str(e)}")


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
