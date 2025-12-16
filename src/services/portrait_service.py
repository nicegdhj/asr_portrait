"""
画像计算服务

按周期聚合客户画像指标，按 customer_id + task_id + period 维度
参考 data_portrait_feasibility_analysis.md 计算口径

多通电话综合规则：
- 满意度：取最后一次有效评分
- 情绪：负面优先
- 风险：高优先
- 沟通意愿：基于平均时长和轮次
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
from src.services.rule_engine_service import rule_engine


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
        计算指定周期的用户画像快照（优化版：批量 GROUP BY 聚合）

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

            async for session in get_portrait_db():
                # 优化：单次 GROUP BY 批量聚合所有 (customer_id, task_id) 组合
                result = await session.execute(
                    select(
                        CallRecordEnriched.user_id.label("customer_id"),
                        CallRecordEnriched.task_id,
                        # 取第一个非空手机号
                        func.max(CallRecordEnriched.phone).label("phone"),
                        # 通话统计
                        func.count().label("total_calls"),
                        func.sum(case((CallRecordEnriched.bill > 0, 1), else_=0)).label("connected_calls"),
                        func.sum(CallRecordEnriched.bill).label("total_bill"),
                        func.avg(case((CallRecordEnriched.bill > 0, CallRecordEnriched.bill), else_=None)).label("avg_bill"),
                        func.max(CallRecordEnriched.bill).label("max_bill"),
                        func.min(case((CallRecordEnriched.bill > 0, CallRecordEnriched.bill), else_=None)).label("min_bill"),
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
                        func.sum(case((CallRecordEnriched.complaint_risk == "medium", 1), else_=0)).label("medium_complaint"),
                        func.sum(case((CallRecordEnriched.complaint_risk == "low", 1), else_=0)).label("low_complaint"),
                        func.sum(case((CallRecordEnriched.churn_risk == "high", 1), else_=0)).label("high_churn"),
                        func.sum(case((CallRecordEnriched.churn_risk == "medium", 1), else_=0)).label("medium_churn"),
                        func.sum(case((CallRecordEnriched.churn_risk == "low", 1), else_=0)).label("low_churn"),
                        # 满意度分布
                        func.sum(case((CallRecordEnriched.satisfaction == "satisfied", 1), else_=0)).label("satisfied"),
                        func.sum(case((CallRecordEnriched.satisfaction == "neutral", 1), else_=0)).label("neutral_satisfaction"),
                        func.sum(case((CallRecordEnriched.satisfaction == "unsatisfied", 1), else_=0)).label("unsatisfied"),
                        # 沟通意愿分布
                        func.sum(case((CallRecordEnriched.willingness == "深度", 1), else_=0)).label("willingness_deep"),
                        func.sum(case((CallRecordEnriched.willingness == "一般", 1), else_=0)).label("willingness_normal"),
                        func.sum(case((CallRecordEnriched.willingness == "较低", 1), else_=0)).label("willingness_low"),
                        # 综合风险分布
                        func.sum(case((CallRecordEnriched.risk_level == "churn", 1), else_=0)).label("risk_churn"),
                        func.sum(case((CallRecordEnriched.risk_level == "complaint", 1), else_=0)).label("risk_complaint"),
                        func.sum(case((CallRecordEnriched.risk_level == "medium", 1), else_=0)).label("risk_medium"),
                        func.sum(case((CallRecordEnriched.risk_level == "none", 1), else_=0)).label("risk_none"),
                    )
                    .where(
                        and_(
                            CallRecordEnriched.call_date >= start_date,
                            CallRecordEnriched.call_date <= end_date,
                        )
                    )
                    .group_by(CallRecordEnriched.user_id, CallRecordEnriched.task_id)
                )
                rows = result.all()

            if not rows:
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

            logger.info(f"周期内客户-任务组合数: {len(rows)}，开始批量写入...")

            # 获取每个客户的最后一次有效满意度和情感（用于综合规则）
            last_satisfaction_map = await self._get_last_satisfaction(
                session, start_date, end_date
            )
            last_emotion_map = await self._get_last_emotion(
                session, start_date, end_date
            )

            # 批量构建快照数据
            total_records = 0
            snapshot_list = []
            for row in rows:
                total_calls = row.total_calls or 0
                connected_calls = row.connected_calls or 0
                connect_rate = connected_calls / total_calls if total_calls > 0 else 0.0

                # 转换时长 (毫秒 -> 秒)
                total_duration = (row.total_bill or 0) // 1000
                avg_duration = (row.avg_bill or 0) / 1000
                max_duration = (row.max_bill or 0) // 1000
                min_duration = (row.min_bill or 0) // 1000

                # 多通电话综合规则
                key = (row.customer_id, str(row.task_id))
                
                # 1. 满意度：取最后一次有效评分
                final_satisfaction = last_satisfaction_map.get(key)
                
                # 2. 情感：负面优先
                positive_count = row.positive_count or 0
                negative_count = row.negative_count or 0
                if negative_count > 0:
                    final_emotion = 'negative'
                elif positive_count > 0:
                    final_emotion = 'positive'
                else:
                    final_emotion = 'neutral'
                
                # 3. 沟通意愿：基于平均时长和平均轮次
                avg_rounds = float(row.avg_rounds or 0)
                willingness = rule_engine._analyze_willingness(int(avg_duration), int(avg_rounds))
                
                # 4. 综合风险：高优先
                high_complaint = row.high_complaint or 0
                high_churn = row.high_churn or 0
                medium_complaint = row.medium_complaint or 0
                medium_churn = row.medium_churn or 0
                
                if high_churn > 0:
                    risk_level = 'churn'
                elif high_complaint > 0:
                    risk_level = 'complaint'
                elif medium_complaint > 0 or medium_churn > 0:
                    risk_level = 'medium'
                else:
                    risk_level = 'none'

                snapshot_list.append({
                    "customer_id": row.customer_id,
                    "phone": row.phone,
                    "task_id": row.task_id,
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
                    "avg_rounds": round(avg_rounds, 2),
                    "level_a_count": row.level_a or 0,
                    "level_b_count": row.level_b or 0,
                    "level_c_count": row.level_c or 0,
                    "level_d_count": row.level_d or 0,
                    "level_e_count": row.level_e or 0,
                    "level_f_count": row.level_f or 0,
                    "robot_hangup_count": row.robot_hangup or 0,
                    "user_hangup_count": row.user_hangup or 0,
                    "positive_count": positive_count,
                    "neutral_count": row.neutral_count or 0,
                    "negative_count": negative_count,
                    "avg_sentiment_score": round(float(row.avg_sentiment_score or 0.5), 4),
                    "high_complaint_risk": high_complaint,
                    "medium_complaint_risk": medium_complaint,
                    "low_complaint_risk": row.low_complaint or 0,
                    "high_churn_risk": high_churn,
                    "medium_churn_risk": medium_churn,
                    "low_churn_risk": row.low_churn or 0,
                    # 满意度
                    "satisfied_count": row.satisfied or 0,
                    "neutral_satisfaction_count": row.neutral_satisfaction or 0,
                    "unsatisfied_count": row.unsatisfied or 0,
                    "final_satisfaction": final_satisfaction,
                    # 情感
                    "final_emotion": final_emotion,
                    # 沟通意愿
                    "willingness": willingness,
                    "willingness_deep_count": row.willingness_deep or 0,
                    "willingness_normal_count": row.willingness_normal or 0,
                    "willingness_low_count": row.willingness_low or 0,
                    # 综合风险
                    "risk_level": risk_level,
                    "risk_churn_count": row.risk_churn or 0,
                    "risk_complaint_count": row.risk_complaint or 0,
                    "risk_medium_count": row.risk_medium or 0,
                    "risk_none_count": row.risk_none or 0,
                    "computed_at": datetime.now(),
                })
                total_records += total_calls

            # 批量 UPSERT（分批处理，每批 100 条，避免超过 PostgreSQL 32767 参数限制）
            batch_size = 100
            async for session in get_portrait_db():
                for i in range(0, len(snapshot_list), batch_size):
                    batch = snapshot_list[i:i + batch_size]
                    stmt = insert(UserPortraitSnapshot).values(batch)
                    stmt = stmt.on_conflict_do_update(
                        constraint="uq_customer_task_period",
                        set_={
                            "phone": stmt.excluded.phone,
                            "total_calls": stmt.excluded.total_calls,
                            "connected_calls": stmt.excluded.connected_calls,
                            "connect_rate": stmt.excluded.connect_rate,
                            "total_duration": stmt.excluded.total_duration,
                            "avg_duration": stmt.excluded.avg_duration,
                            "max_duration": stmt.excluded.max_duration,
                            "min_duration": stmt.excluded.min_duration,
                            "total_rounds": stmt.excluded.total_rounds,
                            "avg_rounds": stmt.excluded.avg_rounds,
                            "level_a_count": stmt.excluded.level_a_count,
                            "level_b_count": stmt.excluded.level_b_count,
                            "level_c_count": stmt.excluded.level_c_count,
                            "level_d_count": stmt.excluded.level_d_count,
                            "level_e_count": stmt.excluded.level_e_count,
                            "level_f_count": stmt.excluded.level_f_count,
                            "robot_hangup_count": stmt.excluded.robot_hangup_count,
                            "user_hangup_count": stmt.excluded.user_hangup_count,
                            "positive_count": stmt.excluded.positive_count,
                            "neutral_count": stmt.excluded.neutral_count,
                            "negative_count": stmt.excluded.negative_count,
                            "avg_sentiment_score": stmt.excluded.avg_sentiment_score,
                            "high_complaint_risk": stmt.excluded.high_complaint_risk,
                            "medium_complaint_risk": stmt.excluded.medium_complaint_risk,
                            "low_complaint_risk": stmt.excluded.low_complaint_risk,
                            "high_churn_risk": stmt.excluded.high_churn_risk,
                            "medium_churn_risk": stmt.excluded.medium_churn_risk,
                            "low_churn_risk": stmt.excluded.low_churn_risk,
                            # 满意度
                            "satisfied_count": stmt.excluded.satisfied_count,
                            "neutral_satisfaction_count": stmt.excluded.neutral_satisfaction_count,
                            "unsatisfied_count": stmt.excluded.unsatisfied_count,
                            "final_satisfaction": stmt.excluded.final_satisfaction,
                            # 情感
                            "final_emotion": stmt.excluded.final_emotion,
                            # 沟通意愿
                            "willingness": stmt.excluded.willingness,
                            "willingness_deep_count": stmt.excluded.willingness_deep_count,
                            "willingness_normal_count": stmt.excluded.willingness_normal_count,
                            "willingness_low_count": stmt.excluded.willingness_low_count,
                            # 综合风险
                            "risk_level": stmt.excluded.risk_level,
                            "risk_churn_count": stmt.excluded.risk_churn_count,
                            "risk_complaint_count": stmt.excluded.risk_complaint_count,
                            "risk_medium_count": stmt.excluded.risk_medium_count,
                            "risk_none_count": stmt.excluded.risk_none_count,
                            "computed_at": stmt.excluded.computed_at,
                        },
                    )
                    await session.execute(stmt)
                await session.commit()

            # 更新周期状态
            await period_service.update_period_status(
                period_type,
                period_key,
                "completed",
                total_users=len(rows),
                total_records=total_records,
                computed_at=datetime.now(),
            )

            logger.info(f"快照计算完成: {period_key}, customers={len(rows)}, records={total_records}")

            return {
                "status": "success",
                "period_type": period_type,
                "period_key": period_key,
                "customers": len(rows),
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

    async def _get_last_satisfaction(
        self,
        session,
        start_date: date,
        end_date: date,
    ) -> dict[tuple[str, str], str]:
        """
        获取每个客户的最后一次有效满意度评分
        
        实现"取最后一次有效评分"的综合规则
        
        Returns:
            {(customer_id, task_id): satisfaction}
        """
        # 使用 DISTINCT ON 获取每个 (customer_id, task_id) 的最后一条有效记录
        result = await session.execute(
            text("""
                SELECT DISTINCT ON (user_id, task_id)
                    user_id as customer_id,
                    task_id::text,
                    satisfaction
                FROM call_record_enriched
                WHERE call_date >= :start_date
                  AND call_date <= :end_date
                  AND satisfaction IS NOT NULL
                ORDER BY user_id, task_id, call_date DESC
            """),
            {"start_date": start_date, "end_date": end_date},
        )
        
        satisfaction_map = {}
        for row in result.fetchall():
            key = (row.customer_id, row.task_id)
            satisfaction_map[key] = row.satisfaction
        
        return satisfaction_map

    async def _get_last_emotion(
        self,
        session,
        start_date: date,
        end_date: date,
    ) -> dict[tuple[str, str], str]:
        """
        获取每个客户的情感（负面优先）
        
        Returns:
            {(customer_id, task_id): emotion}
        """
        # 简化处理：如果有任何负面情绪记录就是negative
        result = await session.execute(
            text("""
                SELECT 
                    user_id as customer_id,
                    task_id::text,
                    MAX(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as has_negative,
                    MAX(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as has_positive
                FROM call_record_enriched
                WHERE call_date >= :start_date
                  AND call_date <= :end_date
                  AND sentiment IS NOT NULL
                GROUP BY user_id, task_id
            """),
            {"start_date": start_date, "end_date": end_date},
        )
        
        emotion_map = {}
        for row in result.fetchall():
            key = (row.customer_id, row.task_id)
            if row.has_negative:
                emotion_map[key] = 'negative'
            elif row.has_positive:
                emotion_map[key] = 'positive'
            else:
                emotion_map[key] = 'neutral'
        
        return emotion_map

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
            # 先获取客户的手机号（取第一条记录的 phone）
            phone_result = await session.execute(
                select(CallRecordEnriched.phone)
                .where(
                    and_(
                        CallRecordEnriched.user_id == customer_id,
                        CallRecordEnriched.task_id == task_id,
                        CallRecordEnriched.phone.isnot(None),
                    )
                )
                .limit(1)
            )
            phone_row = phone_result.first()
            phone = phone_row.phone if phone_row else None

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
                "phone": phone,
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
                    # 满意度统计
                    func.sum(UserPortraitSnapshot.satisfied_count).label("satisfied_total"),
                    func.sum(UserPortraitSnapshot.neutral_satisfaction_count).label("neutral_satisfaction_total"),
                    func.sum(UserPortraitSnapshot.unsatisfied_count).label("unsatisfied_total"),
                    # 情感统计
                    func.sum(UserPortraitSnapshot.positive_count).label("positive_total"),
                    func.sum(UserPortraitSnapshot.neutral_count).label("neutral_emotion_total"),
                    func.sum(UserPortraitSnapshot.negative_count).label("negative_total"),
                    func.avg(UserPortraitSnapshot.avg_sentiment_score).label("avg_sentiment"),
                    # 风险统计
                    func.sum(case((UserPortraitSnapshot.risk_level == 'complaint', 1), else_=0)).label("high_complaint"),
                    func.sum(case((UserPortraitSnapshot.risk_level == 'churn', 1), else_=0)).label("high_churn"),
                    func.sum(case((UserPortraitSnapshot.risk_level == 'medium', 1), else_=0)).label("medium_risk"),
                    func.sum(case((UserPortraitSnapshot.risk_level == 'none', 1), else_=0)).label("no_risk"),
                    # 沟通意愿统计
                    func.sum(case((UserPortraitSnapshot.willingness == '深度', 1), else_=0)).label("deep_willingness"),
                    func.sum(case((UserPortraitSnapshot.willingness == '一般', 1), else_=0)).label("normal_willingness"),
                    func.sum(case((UserPortraitSnapshot.willingness == '较低', 1), else_=0)).label("low_willingness"),
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
                
                # 满意度统计
                satisfied_total = row.satisfied_total or 0
                neutral_satisfaction_total = row.neutral_satisfaction_total or 0
                unsatisfied_total = row.unsatisfied_total or 0
                total_satisfaction = satisfied_total + neutral_satisfaction_total + unsatisfied_total
                satisfied_rate = satisfied_total / total_satisfaction if total_satisfaction > 0 else 0
                
                # 情感统计
                positive_total = row.positive_total or 0
                neutral_emotion_total = row.neutral_emotion_total or 0
                negative_total = row.negative_total or 0
                total_emotion = positive_total + neutral_emotion_total + negative_total
                positive_rate = positive_total / total_emotion if total_emotion > 0 else 0

                # 风险统计
                high_complaint = row.high_complaint or 0
                high_churn = row.high_churn or 0
                medium_risk = row.medium_risk or 0
                no_risk = row.no_risk or 0
                high_complaint_rate = high_complaint / total_customers if total_customers > 0 else 0
                high_churn_rate = high_churn / total_customers if total_customers > 0 else 0
                high_risk_rate = (high_complaint + high_churn) / total_customers if total_customers > 0 else 0
                
                # 沟通意愿统计
                deep_willingness = row.deep_willingness or 0
                normal_willingness = row.normal_willingness or 0
                low_willingness = row.low_willingness or 0
                deep_willingness_rate = deep_willingness / total_customers if total_customers > 0 else 0

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
                    # 满意度
                    "satisfied_count": satisfied_total,
                    "satisfied_rate": round(satisfied_rate, 4),
                    "neutral_count": neutral_satisfaction_total,
                    "unsatisfied_count": unsatisfied_total,
                    # 情感
                    "positive_count": positive_total,
                    "neutral_emotion_count": neutral_emotion_total,
                    "negative_count": negative_total,
                    "positive_rate": round(positive_rate, 4),
                    "avg_sentiment_score": round(row.avg_sentiment or 0.5, 4),
                    # 风险
                    "high_complaint_customers": high_complaint,
                    "high_complaint_rate": round(high_complaint_rate, 4),
                    "high_churn_customers": high_churn,
                    "high_churn_rate": round(high_churn_rate, 4),
                    "medium_risk_customers": medium_risk,
                    "no_risk_customers": no_risk,
                    "high_risk_rate": round(high_risk_rate, 4),
                    # 沟通意愿
                    "deep_willingness_count": deep_willingness,
                    "normal_willingness_count": normal_willingness,
                    "low_willingness_count": low_willingness,
                    "deep_willingness_rate": round(deep_willingness_rate, 4),
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
