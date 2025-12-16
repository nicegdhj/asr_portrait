"""
通话记录增强表

存储从源系统同步并经过 LLM 分析增强的通话记录
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, Index, Integer, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import PortraitBase, TimestampMixin, UUIDPrimaryKeyMixin


class CallRecordEnriched(PortraitBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    通话记录增强表

    存储从源系统同步的通话记录，并附加 LLM 分析结果
    """

    __tablename__ = "call_record_enriched"

    # ===========================================
    # 源数据字段
    # ===========================================

    callid: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="原始通话ID",
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="任务ID",
    )

    user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="被呼客户ID (customer_id)",
    )

    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="被叫手机号 (callee)",
    )

    call_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="通话日期",
    )

    # ===========================================
    # 原始指标
    # ===========================================

    duration: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="通话时长(毫秒)",
    )

    bill: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="计费时长(毫秒)",
    )

    rounds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="交互轮次",
    )

    level_name: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="意向等级名称",
    )

    intention_result: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="意向标签(A/B/C/D/E/F)",
    )

    hangup_by: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="挂断方: 1=机器人, 2=客户",
    )

    call_status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        comment="通话状态",
    )

    fail_reason: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="未接原因状态码",
    )

    # ===========================================
    # LLM 增强指标
    # ===========================================

    sentiment: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="情绪: positive/neutral/negative",
    )

    sentiment_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="情绪得分 0~1",
    )

    complaint_risk: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="投诉风险: low/medium/high",
    )

    churn_risk: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="流失风险: low/medium/high",
    )

    satisfaction: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="满意度: satisfied/neutral/unsatisfied",
    )

    satisfaction_source: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="满意度来源: asr_tag/score/keyword",
    )

    willingness: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="沟通意愿: 深度/一般/较低",
    )

    risk_level: Mapped[Optional[str]] = mapped_column(
        String(16),
        nullable=True,
        comment="综合风险: churn(流失)/complaint(投诉)/medium(一般)/none(无风险)",
    )

    llm_analyzed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="LLM 分析时间",
    )

    llm_raw_response: Mapped[Optional[str]] = mapped_column(
        String(2000),
        nullable=True,
        comment="LLM 原始响应 (用于调试)",
    )

    # ===========================================
    # 索引定义
    # ===========================================

    __table_args__ = (
        Index("idx_customer_date", "user_id", "call_date"),
        Index("idx_customer_task", "user_id", "task_id"),
        Index("idx_task_date", "task_id", "call_date"),
        Index("idx_sentiment", "sentiment"),
        Index("idx_complaint_risk", "complaint_risk"),
        Index("idx_churn_risk", "churn_risk"),
        {"comment": "通话记录增强表"},
    )

    def __repr__(self) -> str:
        return f"<CallRecordEnriched(callid={self.callid}, date={self.call_date})>"
