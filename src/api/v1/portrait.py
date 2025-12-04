"""
用户画像接口

提供用户画像查询和趋势数据
"""

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import select

from src.api.deps import PortraitDB
from src.models import UserPortraitSnapshot, PeriodRegistry
from src.schemas import (
    ApiResponse,
    UserPortraitResponse,
    CallStatsResponse,
    IntentionDistribution,
    HangupDistribution,
    FailReasonDistribution,
    FailReasonItem,
    SentimentAnalysis,
    RiskAnalysis,
    RiskLevel,
    PeriodDetail,
    TrendResponse,
    TrendDataPoint,
    PortraitSummaryResponse,
)
from src.utils import get_period_range, get_recent_periods
from src.utils.table_utils import NUMBER_STATUS_MAP

router = APIRouter()


@router.get(
    "/{user_id}",
    response_model=ApiResponse[UserPortraitResponse],
    summary="获取用户画像",
    description="查询指定用户在某个周期的画像数据",
)
async def get_user_portrait(
    db: PortraitDB,
    user_id: str = Path(..., description="用户ID"),
    period_type: Literal["week", "month", "quarter"] = Query(
        default="week",
        description="周期类型",
    ),
    period_key: Optional[str] = Query(
        default=None,
        description="周期编号，如 2024-W49，不传则返回最近已完成周期",
    ),
):
    """
    获取用户画像
    
    - **user_id**: 用户ID
    - **period_type**: 周期类型
    - **period_key**: 周期编号，不传则返回最近一个已完成周期
    """
    # 如果未指定周期，获取最近已完成周期
    if not period_key:
        stmt = (
            select(PeriodRegistry)
            .where(PeriodRegistry.period_type == period_type)
            .where(PeriodRegistry.status == "completed")
            .order_by(PeriodRegistry.period_start.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        period = result.scalar_one_or_none()
        
        if not period:
            raise HTTPException(
                status_code=404,
                detail=f"暂无已计算完成的{period_type}数据",
            )
        period_key = period.period_key
    
    # 查询用户画像快照
    stmt = select(UserPortraitSnapshot).where(
        UserPortraitSnapshot.user_id == user_id,
        UserPortraitSnapshot.period_type == period_type,
        UserPortraitSnapshot.period_key == period_key,
    )
    
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()
    
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail=f"未找到用户 {user_id} 在周期 {period_key} 的画像数据",
        )
    
    # 构建响应
    response = _build_portrait_response(snapshot)
    return ApiResponse.success(data=response)


@router.get(
    "/summary",
    response_model=ApiResponse[PortraitSummaryResponse],
    summary="获取画像汇总",
    description="获取全量用户的画像汇总统计",
)
async def get_portrait_summary(
    db: PortraitDB,
    period_type: Literal["week", "month", "quarter"] = Query(
        default="week",
        description="周期类型",
    ),
    period_key: Optional[str] = Query(
        default=None,
        description="周期编号",
    ),
):
    """
    获取画像汇总
    
    汇总全量用户的画像数据，用于展示大盘数据
    """
    # 如果未指定周期，获取最近已完成周期
    if not period_key:
        stmt = (
            select(PeriodRegistry)
            .where(PeriodRegistry.period_type == period_type)
            .where(PeriodRegistry.status == "completed")
            .order_by(PeriodRegistry.period_start.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        period = result.scalar_one_or_none()
        
        if not period:
            raise HTTPException(
                status_code=404,
                detail=f"暂无已计算完成的{period_type}数据",
            )
        period_key = period.period_key
    
    # 查询该周期所有用户的画像
    stmt = select(UserPortraitSnapshot).where(
        UserPortraitSnapshot.period_type == period_type,
        UserPortraitSnapshot.period_key == period_key,
    )
    
    result = await db.execute(stmt)
    snapshots = result.scalars().all()
    
    if not snapshots:
        raise HTTPException(
            status_code=404,
            detail=f"周期 {period_key} 暂无画像数据",
        )
    
    # 汇总统计
    start, end = get_period_range(period_type, period_key)
    summary = _aggregate_snapshots(snapshots, period_type, period_key, start, end)
    
    return ApiResponse.success(data=summary)


@router.get(
    "/trend",
    response_model=ApiResponse[TrendResponse],
    summary="获取趋势数据",
    description="获取多周期趋势数据，用于柱状图展示",
)
async def get_portrait_trend(
    db: PortraitDB,
    period_type: Literal["week", "month", "quarter"] = Query(
        default="week",
        description="周期类型",
    ),
    metric: str = Query(
        default="connect_rate",
        description="指标名称: connect_rate/avg_duration/avg_rounds/positive_rate",
    ),
    limit: int = Query(
        default=12,
        ge=1,
        le=52,
        description="返回周期数量",
    ),
    user_id: Optional[str] = Query(
        default=None,
        description="用户ID，不传则返回全量汇总",
    ),
):
    """
    获取趋势数据
    
    返回多个周期的指标数据，用于绘制趋势图/柱状图
    
    支持的指标:
    - connect_rate: 接通率
    - avg_duration: 平均通话时长
    - avg_rounds: 平均交互轮次
    - positive_rate: 积极情绪占比
    - negative_rate: 消极情绪占比
    - total_calls: 总通话次数
    """
    # 查询已完成的周期
    stmt = (
        select(PeriodRegistry)
        .where(PeriodRegistry.period_type == period_type)
        .where(PeriodRegistry.status == "completed")
        .order_by(PeriodRegistry.period_start.desc())
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    periods = result.scalars().all()
    
    if not periods:
        return ApiResponse.success(
            data=TrendResponse(
                metric=metric,
                period_type=period_type,
                series=[],
            )
        )
    
    # 获取每个周期的数据
    series = []
    for period in reversed(periods):  # 按时间正序
        if user_id:
            # 单用户数据
            stmt = select(UserPortraitSnapshot).where(
                UserPortraitSnapshot.user_id == user_id,
                UserPortraitSnapshot.period_type == period_type,
                UserPortraitSnapshot.period_key == period.period_key,
            )
            result = await db.execute(stmt)
            snapshot = result.scalar_one_or_none()
            
            if snapshot:
                value = _get_metric_value(snapshot, metric)
                series.append(TrendDataPoint(
                    period_key=period.period_key,
                    label=period.label,
                    value=value,
                ))
        else:
            # 全量汇总数据
            stmt = select(UserPortraitSnapshot).where(
                UserPortraitSnapshot.period_type == period_type,
                UserPortraitSnapshot.period_key == period.period_key,
            )
            result = await db.execute(stmt)
            snapshots = result.scalars().all()
            
            if snapshots:
                value = _get_aggregated_metric_value(snapshots, metric)
                series.append(TrendDataPoint(
                    period_key=period.period_key,
                    label=period.label,
                    value=value,
                ))
    
    return ApiResponse.success(
        data=TrendResponse(
            metric=metric,
            period_type=period_type,
            series=series,
        )
    )


def _build_portrait_response(snapshot: UserPortraitSnapshot) -> UserPortraitResponse:
    """从快照构建响应"""
    # 构建未接原因分布
    fail_items = []
    fail_dist = snapshot.fail_reason_dist or {}
    total_fail = sum(fail_dist.values())
    for code_str, count in fail_dist.items():
        code = int(code_str)
        fail_items.append(FailReasonItem(
            reason=NUMBER_STATUS_MAP.get(code, f"未知({code})"),
            code=code,
            count=count,
            rate=count / total_fail if total_fail > 0 else 0,
        ))
    fail_items.sort(key=lambda x: x.count, reverse=True)
    
    return UserPortraitResponse(
        user_id=str(snapshot.user_id),
        period=PeriodDetail(
            type=snapshot.period_type,
            key=snapshot.period_key,
            start=snapshot.period_start,
            end=snapshot.period_end,
        ),
        call_stats=CallStatsResponse(
            total_calls=snapshot.total_calls,
            connected_calls=snapshot.connected_calls,
            connect_rate=snapshot.connect_rate,
            total_duration=snapshot.total_duration,
            avg_duration=snapshot.avg_duration,
            max_duration=snapshot.max_duration,
            min_duration=snapshot.min_duration,
            total_rounds=snapshot.total_rounds,
            avg_rounds=snapshot.avg_rounds,
        ),
        intention_dist=IntentionDistribution(
            A=snapshot.level_a_count,
            B=snapshot.level_b_count,
            C=snapshot.level_c_count,
            D=snapshot.level_d_count,
            E=snapshot.level_e_count,
            F=snapshot.level_f_count,
        ),
        hangup_dist=HangupDistribution(
            robot=snapshot.robot_hangup_count,
            user=snapshot.user_hangup_count,
        ),
        fail_reason_dist=FailReasonDistribution(
            total=total_fail,
            items=fail_items,
        ),
        sentiment_analysis=SentimentAnalysis(
            positive=snapshot.positive_count,
            neutral=snapshot.neutral_count,
            negative=snapshot.negative_count,
            avg_score=snapshot.avg_sentiment_score,
        ),
        risk_analysis=RiskAnalysis(
            complaint_risk=RiskLevel(
                high=snapshot.high_complaint_risk,
                medium=snapshot.medium_complaint_risk,
                low=snapshot.low_complaint_risk,
            ),
            churn_risk=RiskLevel(
                high=snapshot.high_churn_risk,
                medium=snapshot.medium_churn_risk,
                low=snapshot.low_churn_risk,
            ),
        ),
    )


def _aggregate_snapshots(
    snapshots: list,
    period_type: str,
    period_key: str,
    start,
    end,
) -> PortraitSummaryResponse:
    """汇总多个用户的快照"""
    total_users = len(snapshots)
    
    # 汇总通话统计
    total_calls = sum(s.total_calls for s in snapshots)
    connected_calls = sum(s.connected_calls for s in snapshots)
    total_duration = sum(s.total_duration for s in snapshots)
    total_rounds = sum(s.total_rounds for s in snapshots)
    
    return PortraitSummaryResponse(
        period=PeriodDetail(type=period_type, key=period_key, start=start, end=end),
        total_users=total_users,
        call_stats=CallStatsResponse(
            total_calls=total_calls,
            connected_calls=connected_calls,
            connect_rate=connected_calls / total_calls if total_calls > 0 else 0,
            total_duration=total_duration,
            avg_duration=total_duration / connected_calls if connected_calls > 0 else 0,
            max_duration=max(s.max_duration for s in snapshots) if snapshots else 0,
            min_duration=min(s.min_duration for s in snapshots if s.min_duration > 0) if snapshots else 0,
            total_rounds=total_rounds,
            avg_rounds=total_rounds / connected_calls if connected_calls > 0 else 0,
        ),
        intention_dist=IntentionDistribution(
            A=sum(s.level_a_count for s in snapshots),
            B=sum(s.level_b_count for s in snapshots),
            C=sum(s.level_c_count for s in snapshots),
            D=sum(s.level_d_count for s in snapshots),
            E=sum(s.level_e_count for s in snapshots),
            F=sum(s.level_f_count for s in snapshots),
        ),
        sentiment_summary=SentimentAnalysis(
            positive=sum(s.positive_count for s in snapshots),
            neutral=sum(s.neutral_count for s in snapshots),
            negative=sum(s.negative_count for s in snapshots),
            avg_score=sum(s.avg_sentiment_score for s in snapshots) / total_users if total_users > 0 else 0,
        ),
        risk_summary=RiskAnalysis(
            complaint_risk=RiskLevel(
                high=sum(s.high_complaint_risk for s in snapshots),
                medium=sum(s.medium_complaint_risk for s in snapshots),
                low=sum(s.low_complaint_risk for s in snapshots),
            ),
            churn_risk=RiskLevel(
                high=sum(s.high_churn_risk for s in snapshots),
                medium=sum(s.medium_churn_risk for s in snapshots),
                low=sum(s.low_churn_risk for s in snapshots),
            ),
        ),
    )


def _get_metric_value(snapshot: UserPortraitSnapshot, metric: str) -> float:
    """获取单个快照的指标值"""
    if metric == "connect_rate":
        return snapshot.connect_rate
    elif metric == "avg_duration":
        return snapshot.avg_duration
    elif metric == "avg_rounds":
        return snapshot.avg_rounds
    elif metric == "total_calls":
        return float(snapshot.total_calls)
    elif metric == "positive_rate":
        total = snapshot.positive_count + snapshot.neutral_count + snapshot.negative_count
        return snapshot.positive_count / total if total > 0 else 0
    elif metric == "negative_rate":
        total = snapshot.positive_count + snapshot.neutral_count + snapshot.negative_count
        return snapshot.negative_count / total if total > 0 else 0
    return 0.0


def _get_aggregated_metric_value(snapshots: list, metric: str) -> float:
    """获取聚合指标值"""
    if not snapshots:
        return 0.0
    
    if metric == "connect_rate":
        total = sum(s.total_calls for s in snapshots)
        connected = sum(s.connected_calls for s in snapshots)
        return connected / total if total > 0 else 0
    elif metric == "avg_duration":
        total_duration = sum(s.total_duration for s in snapshots)
        connected = sum(s.connected_calls for s in snapshots)
        return total_duration / connected if connected > 0 else 0
    elif metric == "avg_rounds":
        total_rounds = sum(s.total_rounds for s in snapshots)
        connected = sum(s.connected_calls for s in snapshots)
        return total_rounds / connected if connected > 0 else 0
    elif metric == "total_calls":
        return float(sum(s.total_calls for s in snapshots))
    elif metric == "positive_rate":
        positive = sum(s.positive_count for s in snapshots)
        total = positive + sum(s.neutral_count for s in snapshots) + sum(s.negative_count for s in snapshots)
        return positive / total if total > 0 else 0
    elif metric == "negative_rate":
        negative = sum(s.negative_count for s in snapshots)
        total = sum(s.positive_count for s in snapshots) + sum(s.neutral_count for s in snapshots) + negative
        return negative / total if total > 0 else 0
    return 0.0

