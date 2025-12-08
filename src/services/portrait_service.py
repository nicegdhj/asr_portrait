"""
画像计算服务

按周期聚合客户画像指标，按 customer_id + task_id + period 维度
参考 data_portrait_feasibility_analysis.md 计算口径
"""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from loguru import logger
from sqlalchemy import func, select, and_, case, text
from sqlalchemy.dialects.postgresql import insert

from src.core.database import get_portrait_db
from src.models.portrait.call_enriched import CallRecordEnriched
from src.models.portrait.snapshot import UserPortraitSnapshot
from src.services.period_service import (
    period_service,
    get_period_range,
    get_period_label,
    PeriodType,
)


class PortraitService:
    """
    画像计算服务

    聚合通话记录生成用户画像快照
    """

    async def compute_snapshot(
        self,
        period_type: PeriodType,
        period_key: str,
    ) -> dict[str, Any]:
        """
        计算指定周期的用户画像快照

        Args:
            period_type: 周期类型 (week/month/quarter)
            period_key: 周期编号

        Returns:
            计算结果统计
        """
        logger.info(f"开始计算快照: {period_type}/{period_key}")

        # 注册周期并更新状态
        await period_service.register_period(period_type, period_key)
        await period_service.update_period_status(period_type, period_key, "computing")

        try:
            start_date, end_date = get_period_range(period_type, period_key)

            # 查询所有 (customer_id, task_id) 组合
            async for session in get_portrait_db():
                customer_task_result = await session.execute(
                    select(
                        CallRecordEnriched.user_id,  # 存储的是 customer_id
                        CallRecordEnriched.task_id,
                    )
                    .where(
                        and_(
                            CallRecordEnriched.call_date >= start_date,
                            CallRecordEnriched.call_date <= end_date,
                        )
                    )
                    .distinct()
                )
                customer_task_pairs = [(row.user_id, row.task_id) for row in customer_task_result]

            if not customer_task_pairs:
                logger.info(f"周期 {period_key} 没有通话记录")
                await period_service.update_period_status(
                    period_type,
                    period_key,
                    "completed",
                    total_users=0,
                    total_records=0,
                    computed_at=datetime.now(),
                )
                return {"status": "success", "customers": 0, "records": 0}

            logger.info(f"周期内客户-任务组合数: {len(customer_task_pairs)}")

            # 逐客户-任务组合计算画像
            total_records = 0
            for customer_id, task_id in customer_task_pairs:
                snapshot = await self._compute_customer_snapshot(
                    customer_id, task_id, period_type, period_key, start_date, end_date
                )
                if snapshot:
                    total_records += snapshot.total_calls

            # 更新周期状态
            await period_service.update_period_status(
                period_type,
                period_key,
                "completed",
                total_users=len(customer_task_pairs),
                total_records=total_records,
                computed_at=datetime.now(),
            )

            logger.info(f"快照计算完成: {period_key}, customers={len(customer_task_pairs)}, records={total_records}")

            return {
                "status": "success",
                "period_type": period_type,
                "period_key": period_key,
                "customers": len(customer_task_pairs),
                "records": total_records,
            }

        except Exception as e:
            logger.error(f"快照计算失败: {e}")
            await period_service.update_period_status(
                period_type,
                period_key,
                "failed",
                error_message=str(e),
            )
            raise

    async def _compute_customer_snapshot(
        self,
        customer_id: str,
        task_id: UUID,
        period_type: str,
        period_key: str,
        start_date: date,
        end_date: date,
    ) -> UserPortraitSnapshot | None:
        """
        计算单个客户在某任务下的画像快照
        """
        async for session in get_portrait_db():
            # 聚合查询
            result = await session.execute(
                select(
                    # 通话统计
                    func.count().label("total_calls"),
                    func.sum(case((CallRecordEnriched.bill > 0, 1), else_=0)).label("connected_calls"),
                    func.sum(CallRecordEnriched.bill).label("total_bill"),
                    func.avg(case((CallRecordEnriched.bill > 0, CallRecordEnriched.bill), else_=None)).label(
                        "avg_bill"
                    ),
                    func.max(CallRecordEnriched.bill).label("max_bill"),
                    func.min(case((CallRecordEnriched.bill > 0, CallRecordEnriched.bill), else_=None)).label(
                        "min_bill"
                    ),
                    func.sum(CallRecordEnriched.rounds).label("total_rounds"),
                    func.avg(CallRecordEnriched.rounds).label("avg_rounds"),
                    # 意向分布
                    func.sum(case((CallRecordEnriched.intention_result == "A", 1), else_=0)).label("level_a"),
                    func.sum(case((CallRecordEnriched.intention_result == "B", 1), else_=0)).label("level_b"),
                    func.sum(case((CallRecordEnriched.intention_result == "C", 1), else_=0)).label("level_c"),
                    func.sum(case((CallRecordEnriched.intention_result == "D", 1), else_=0)).label("level_d"),
                    func.sum(case((CallRecordEnriched.intention_result == "E", 1), else_=0)).label("level_e"),
                    func.sum(case((CallRecordEnriched.intention_result == "F", 1), else_=0)).label("level_f"),
                    # 挂断分布
                    func.sum(case((CallRecordEnriched.hangup_by == 1, 1), else_=0)).label("robot_hangup"),
                    func.sum(case((CallRecordEnriched.hangup_by == 2, 1), else_=0)).label("user_hangup"),
                    # 情感分布
                    func.sum(case((CallRecordEnriched.sentiment == "positive", 1), else_=0)).label("positive_count"),
                    func.sum(case((CallRecordEnriched.sentiment == "neutral", 1), else_=0)).label("neutral_count"),
                    func.sum(case((CallRecordEnriched.sentiment == "negative", 1), else_=0)).label("negative_count"),
                    func.avg(CallRecordEnriched.sentiment_score).label("avg_sentiment_score"),
                    # 风险分布
                    func.sum(case((CallRecordEnriched.complaint_risk == "high", 1), else_=0)).label("high_complaint"),
                    func.sum(case((CallRecordEnriched.complaint_risk == "medium", 1), else_=0)).label(
                        "medium_complaint"
                    ),
                    func.sum(case((CallRecordEnriched.complaint_risk == "low", 1), else_=0)).label("low_complaint"),
                    func.sum(case((CallRecordEnriched.churn_risk == "high", 1), else_=0)).label("high_churn"),
                    func.sum(case((CallRecordEnriched.churn_risk == "medium", 1), else_=0)).label("medium_churn"),
                    func.sum(case((CallRecordEnriched.churn_risk == "low", 1), else_=0)).label("low_churn"),
                ).where(
                    and_(
                        CallRecordEnriched.user_id == customer_id,  # user_id 存储 customer_id
                        CallRecordEnriched.task_id == task_id,
                        CallRecordEnriched.call_date >= start_date,
                        CallRecordEnriched.call_date <= end_date,
                    )
                )
            )
            row = result.first()

            if not row or not row.total_calls:
                return None

            # 计算接通率
            total_calls = row.total_calls or 0
            connected_calls = row.connected_calls or 0
            connect_rate = connected_calls / total_calls if total_calls > 0 else 0.0

            # 转换时长 (毫秒 -> 秒)
            total_duration = (row.total_bill or 0) // 1000
            avg_duration = (row.avg_bill or 0) / 1000
            max_duration = (row.max_bill or 0) // 1000
            min_duration = (row.min_bill or 0) // 1000

            # 构建快照数据
            snapshot_data = {
                "customer_id": customer_id,
                "task_id": task_id,
                "period_type": period_type,
                "period_key": period_key,
                "period_start": start_date,
                "period_end": end_date,
                "total_calls": total_calls,
                "connected_calls": connected_calls,
                "connect_rate": round(connect_rate, 4),
                "total_duration": total_duration,
                "avg_duration": round(avg_duration, 2),
                "max_duration": max_duration,
                "min_duration": min_duration,
                "total_rounds": row.total_rounds or 0,
                "avg_rounds": round(row.avg_rounds or 0, 2),
                "level_a_count": row.level_a or 0,
                "level_b_count": row.level_b or 0,
                "level_c_count": row.level_c or 0,
                "level_d_count": row.level_d or 0,
                "level_e_count": row.level_e or 0,
                "level_f_count": row.level_f or 0,
                "robot_hangup_count": row.robot_hangup or 0,
                "user_hangup_count": row.user_hangup or 0,
                "positive_count": row.positive_count or 0,
                "neutral_count": row.neutral_count or 0,
                "negative_count": row.negative_count or 0,
                "avg_sentiment_score": round(row.avg_sentiment_score or 0.5, 4),
                "high_complaint_risk": row.high_complaint or 0,
                "medium_complaint_risk": row.medium_complaint or 0,
                "low_complaint_risk": row.low_complaint or 0,
                "high_churn_risk": row.high_churn or 0,
                "medium_churn_risk": row.medium_churn or 0,
                "low_churn_risk": row.low_churn or 0,
                "computed_at": datetime.now(),
            }

            # Upsert 快照
            stmt = insert(UserPortraitSnapshot).values(**snapshot_data)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_customer_task_period",  # 新的唯一约束
                set_=snapshot_data,
            )
            await session.execute(stmt)
            await session.commit()

            # 返回快照对象
            result = await session.execute(
                select(UserPortraitSnapshot).where(
                    and_(
                        UserPortraitSnapshot.customer_id == customer_id,
                        UserPortraitSnapshot.task_id == task_id,
                        UserPortraitSnapshot.period_type == period_type,
                        UserPortraitSnapshot.period_key == period_key,
                    )
                )
            )
            return result.scalar_one_or_none()

    async def get_customer_portrait(
        self,
        customer_id: str,
        task_id: UUID,
        period_type: PeriodType,
        period_key: str,
    ) -> dict[str, Any] | None:
        """
        获取客户画像

        Args:
            customer_id: 客户ID
            task_id: 任务ID
            period_type: 周期类型
            period_key: 周期编号

        Returns:
            画像数据
        """
        async for session in get_portrait_db():
            result = await session.execute(
                select(UserPortraitSnapshot).where(
                    and_(
                        UserPortraitSnapshot.customer_id == customer_id,
                        UserPortraitSnapshot.task_id == task_id,
                        UserPortraitSnapshot.period_type == period_type,
                        UserPortraitSnapshot.period_key == period_key,
                    )
                )
            )
            snapshot = result.scalar_one_or_none()

            if not snapshot:
                return None

            return self._snapshot_to_dict(snapshot)

    async def get_summary(
        self,
        period_type: PeriodType,
        period_key: str,
    ) -> dict[str, Any]:
        """
        获取全量汇总统计

        Args:
            period_type: 周期类型
            period_key: 周期编号

        Returns:
            汇总数据
        """
        async for session in get_portrait_db():
            result = await session.execute(
                select(
                    func.count().label("user_count"),
                    func.sum(UserPortraitSnapshot.total_calls).label("total_calls"),
                    func.sum(UserPortraitSnapshot.connected_calls).label("connected_calls"),
                    func.avg(UserPortraitSnapshot.connect_rate).label("avg_connect_rate"),
                    func.sum(UserPortraitSnapshot.total_duration).label("total_duration"),
                    func.avg(UserPortraitSnapshot.avg_duration).label("avg_duration"),
                    func.avg(UserPortraitSnapshot.avg_rounds).label("avg_rounds"),
                    func.sum(UserPortraitSnapshot.level_a_count).label("level_a_total"),
                    func.sum(UserPortraitSnapshot.level_b_count).label("level_b_total"),
                    func.sum(UserPortraitSnapshot.level_c_count).label("level_c_total"),
                    func.sum(UserPortraitSnapshot.level_d_count).label("level_d_total"),
                    func.sum(UserPortraitSnapshot.level_e_count).label("level_e_total"),
                    func.sum(UserPortraitSnapshot.level_f_count).label("level_f_total"),
                    func.sum(UserPortraitSnapshot.robot_hangup_count).label("robot_hangup_total"),
                    func.sum(UserPortraitSnapshot.user_hangup_count).label("user_hangup_total"),
                    func.sum(UserPortraitSnapshot.positive_count).label("positive_total"),
                    func.sum(UserPortraitSnapshot.neutral_count).label("neutral_total"),
                    func.sum(UserPortraitSnapshot.negative_count).label("negative_total"),
                    func.avg(UserPortraitSnapshot.avg_sentiment_score).label("avg_sentiment_score"),
                    func.sum(UserPortraitSnapshot.high_complaint_risk).label("high_complaint_total"),
                    func.sum(UserPortraitSnapshot.medium_complaint_risk).label("medium_complaint_total"),
                    func.sum(UserPortraitSnapshot.low_complaint_risk).label("low_complaint_total"),
                    func.sum(UserPortraitSnapshot.high_churn_risk).label("high_churn_total"),
                    func.sum(UserPortraitSnapshot.medium_churn_risk).label("medium_churn_total"),
                    func.sum(UserPortraitSnapshot.low_churn_risk).label("low_churn_total"),
                ).where(
                    and_(
                        UserPortraitSnapshot.period_type == period_type,
                        UserPortraitSnapshot.period_key == period_key,
                    )
                )
            )
            row = result.first()

            if not row or not row.user_count:
                return {
                    "period_type": period_type,
                    "period_key": period_key,
                    "label": get_period_label(period_type, period_key),
                    "user_count": 0,
                    "total_calls": 0,
                }

            return {
                "period_type": period_type,
                "period_key": period_key,
                "label": get_period_label(period_type, period_key),
                "user_count": row.user_count,
                "call_stats": {
                    "total_calls": row.total_calls or 0,
                    "connected_calls": row.connected_calls or 0,
                    "connect_rate": round(row.avg_connect_rate or 0, 4),
                    "total_duration": row.total_duration or 0,
                    "avg_duration": round(row.avg_duration or 0, 2),
                    "avg_rounds": round(row.avg_rounds or 0, 2),
                },
                "intention_dist": {
                    "A": row.level_a_total or 0,
                    "B": row.level_b_total or 0,
                    "C": row.level_c_total or 0,
                    "D": row.level_d_total or 0,
                    "E": row.level_e_total or 0,
                    "F": row.level_f_total or 0,
                },
                "hangup_dist": {
                    "robot": row.robot_hangup_total or 0,
                    "user": row.user_hangup_total or 0,
                },
                "sentiment_analysis": {
                    "positive": row.positive_total or 0,
                    "neutral": row.neutral_total or 0,
                    "negative": row.negative_total or 0,
                    "avg_score": round(row.avg_sentiment_score or 0.5, 4),
                },
                "risk_analysis": {
                    "complaint_risk": {
                        "high": row.high_complaint_total or 0,
                        "medium": row.medium_complaint_total or 0,
                        "low": row.low_complaint_total or 0,
                    },
                    "churn_risk": {
                        "high": row.high_churn_total or 0,
                        "medium": row.medium_churn_total or 0,
                        "low": row.low_churn_total or 0,
                    },
                },
            }

    async def get_trend(
        self,
        period_type: PeriodType,
        metric: str,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        """
        获取趋势数据

        Args:
            period_type: 周期类型
            metric: 指标名称 (connect_rate, avg_duration, etc.)
            limit: 返回数量

        Returns:
            趋势数据列表
        """
        # 指标映射
        metric_map = {
            "connect_rate": func.avg(UserPortraitSnapshot.connect_rate),
            "avg_duration": func.avg(UserPortraitSnapshot.avg_duration),
            "avg_rounds": func.avg(UserPortraitSnapshot.avg_rounds),
            "total_calls": func.sum(UserPortraitSnapshot.total_calls),
            "sentiment_score": func.avg(UserPortraitSnapshot.avg_sentiment_score),
        }

        if metric not in metric_map:
            metric = "connect_rate"

        async for session in get_portrait_db():
            result = await session.execute(
                select(
                    UserPortraitSnapshot.period_key,
                    metric_map[metric].label("value"),
                )
                .where(UserPortraitSnapshot.period_type == period_type)
                .group_by(UserPortraitSnapshot.period_key)
                .order_by(UserPortraitSnapshot.period_key.desc())
                .limit(limit)
            )

            series = []
            for row in result:
                series.append(
                    {
                        "period_key": row.period_key,
                        "value": round(float(row.value or 0), 4),
                        "label": get_period_label(period_type, row.period_key),
                    }
                )

            # 按时间正序
            series.reverse()
            return series

    def _snapshot_to_dict(self, snapshot: UserPortraitSnapshot) -> dict[str, Any]:
        """将快照对象转为字典"""
        return {
            "customer_id": str(snapshot.customer_id),
            "task_id": str(snapshot.task_id),
            "period": {
                "type": snapshot.period_type,
                "key": snapshot.period_key,
                "start": snapshot.period_start.isoformat(),
                "end": snapshot.period_end.isoformat(),
            },
            "call_stats": {
                "total_calls": snapshot.total_calls,
                "connected_calls": snapshot.connected_calls,
                "connect_rate": snapshot.connect_rate,
                "total_duration": snapshot.total_duration,
                "avg_duration": snapshot.avg_duration,
                "max_duration": snapshot.max_duration,
                "min_duration": snapshot.min_duration,
                "total_rounds": snapshot.total_rounds,
                "avg_rounds": snapshot.avg_rounds,
            },
            "intention_dist": {
                "A": snapshot.level_a_count,
                "B": snapshot.level_b_count,
                "C": snapshot.level_c_count,
                "D": snapshot.level_d_count,
                "E": snapshot.level_e_count,
                "F": snapshot.level_f_count,
            },
            "hangup_dist": {
                "robot": snapshot.robot_hangup_count,
                "user": snapshot.user_hangup_count,
            },
            "sentiment_analysis": {
                "positive": snapshot.positive_count,
                "neutral": snapshot.neutral_count,
                "negative": snapshot.negative_count,
                "avg_score": snapshot.avg_sentiment_score,
            },
            "risk_analysis": {
                "complaint_risk": {
                    "high": snapshot.high_complaint_risk,
                    "medium": snapshot.medium_complaint_risk,
                    "low": snapshot.low_complaint_risk,
                },
                "churn_risk": {
                    "high": snapshot.high_churn_risk,
                    "medium": snapshot.medium_churn_risk,
                    "low": snapshot.low_churn_risk,
                },
            },
            "computed_at": snapshot.computed_at.isoformat() if snapshot.computed_at else None,
        }

    async def compute_weekly_snapshot(self) -> dict[str, Any]:
        """计算上周快照"""
        from datetime import timedelta

        today = date.today()
        last_week = today - timedelta(days=7)
        period_key = (
            period_service.get_week_key(last_week)
            if hasattr(period_service, "get_week_key")
            else f"{last_week.isocalendar()[0]}-W{last_week.isocalendar()[1]:02d}"
        )
        return await self.compute_snapshot("week", period_key)

    async def compute_monthly_snapshot(self) -> dict[str, Any]:
        """计算上月快照"""
        from dateutil.relativedelta import relativedelta

        today = date.today()
        last_month = today - relativedelta(months=1)
        period_key = last_month.strftime("%Y-%m")
        return await self.compute_snapshot("month", period_key)

    async def compute_quarterly_snapshot(self) -> dict[str, Any]:
        """计算上季度快照"""
        from dateutil.relativedelta import relativedelta

        today = date.today()
        last_quarter = today - relativedelta(months=3)
        q = (last_quarter.month - 1) // 3 + 1
        period_key = f"{last_quarter.year}-Q{q}"
        return await self.compute_snapshot("quarter", period_key)

    async def compute_task_summary(
        self,
        period_type: PeriodType,
        period_key: str,
    ) -> dict[str, Any]:
        """
        计算场景(任务)级别的汇总统计

        聚合 user_portrait_snapshot 到 task_portrait_summary

        Args:
            period_type: 周期类型
            period_key: 周期编号

        Returns:
            计算结果统计
        """
        from src.models import TaskPortraitSummary

        logger.info(f"开始计算场景汇总: {period_type}/{period_key}")

        start_date, end_date = get_period_range(period_type, period_key)

        async for session in get_portrait_db():
            # 按 task_id 聚合客户画像
            result = await session.execute(
                select(
                    UserPortraitSnapshot.task_id,
                    func.count().label("total_customers"),
                    func.sum(UserPortraitSnapshot.total_calls).label("total_calls"),
                    func.sum(UserPortraitSnapshot.connected_calls).label("connected_calls"),
                    func.avg(UserPortraitSnapshot.connect_rate).label("connect_rate"),
                    func.avg(UserPortraitSnapshot.avg_duration).label("avg_duration"),
                    # 满意度统计（基于情绪）
                    func.sum(UserPortraitSnapshot.positive_count).label("positive_total"),
                    func.sum(UserPortraitSnapshot.neutral_count).label("neutral_total"),
                    func.sum(UserPortraitSnapshot.negative_count).label("negative_total"),
                    func.avg(UserPortraitSnapshot.avg_sentiment_score).label("avg_sentiment"),
                    # 风险统计
                    func.sum(case((UserPortraitSnapshot.high_complaint_risk > 0, 1), else_=0)).label("high_complaint"),
                    func.sum(case((UserPortraitSnapshot.high_churn_risk > 0, 1), else_=0)).label("high_churn"),
                )
                .where(
                    and_(
                        UserPortraitSnapshot.period_type == period_type,
                        UserPortraitSnapshot.period_key == period_key,
                    )
                )
                .group_by(UserPortraitSnapshot.task_id)
            )

            rows = result.all()

            if not rows:
                logger.info(f"周期 {period_key} 没有客户画像数据")
                return {"status": "success", "tasks": 0}

            logger.info(f"聚合 {len(rows)} 个任务的汇总数据")

            summaries_created = 0
            for row in rows:
                total_customers = row.total_customers or 0
                total_calls = row.total_calls or 0
                connected_calls = row.connected_calls or 0
                positive_total = row.positive_total or 0
                neutral_total = row.neutral_total or 0
                negative_total = row.negative_total or 0

                # 计算满意率（正面情绪占比）
                total_sentiment = positive_total + neutral_total + negative_total
                satisfied_rate = positive_total / total_sentiment if total_sentiment > 0 else 0

                # 计算风险占比
                high_complaint = row.high_complaint or 0
                high_churn = row.high_churn or 0
                high_complaint_rate = high_complaint / total_customers if total_customers > 0 else 0
                high_churn_rate = high_churn / total_customers if total_customers > 0 else 0

                summary_data = {
                    "task_id": row.task_id,
                    "period_type": period_type,
                    "period_key": period_key,
                    "period_start": start_date,
                    "period_end": end_date,
                    "total_customers": total_customers,
                    "total_calls": total_calls,
                    "connected_calls": connected_calls,
                    "connect_rate": round(row.connect_rate or 0, 4),
                    "avg_duration": round(row.avg_duration or 0, 2),
                    "satisfied_count": positive_total,
                    "satisfied_rate": round(satisfied_rate, 4),
                    "neutral_count": neutral_total,
                    "unsatisfied_count": negative_total,
                    "positive_count": positive_total,
                    "negative_count": negative_total,
                    "avg_sentiment_score": round(row.avg_sentiment or 0.5, 4),
                    "high_complaint_customers": high_complaint,
                    "high_complaint_rate": round(high_complaint_rate, 4),
                    "high_churn_customers": high_churn,
                    "high_churn_rate": round(high_churn_rate, 4),
                    "computed_at": datetime.now(),
                }

                # Upsert
                stmt = insert(TaskPortraitSummary).values(**summary_data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["task_id", "period_type", "period_key"],
                    set_=summary_data,
                )
                await session.execute(stmt)
                summaries_created += 1

            await session.commit()

            logger.info(f"场景汇总计算完成: {period_key}, tasks={summaries_created}")

            return {
                "status": "success",
                "period_type": period_type,
                "period_key": period_key,
                "tasks": summaries_created,
            }


# 全局服务实例
portrait_service = PortraitService()
