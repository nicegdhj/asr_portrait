"""
场景画像汇总表

按场景(task_id)聚合客户满意度、风险占比等指标，支持趋势展示
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import PortraitBase, UUIDPrimaryKeyMixin


class TaskPortraitSummary(PortraitBase, UUIDPrimaryKeyMixin):
    """
    场景画像汇总表

    存储按场景(task_id)和周期聚合的汇总统计，包括满意度、投诉风险、流失风险占比
    """

    __tablename__ = "task_portrait_summary"

    # ===========================================
    # 场景和周期信息
    # ===========================================

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="任务/场景ID",
    )

    task_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="任务名称",
    )

    period_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="周期类型: week/month/quarter",
    )

    period_key: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="周期编号: 2024-W49 / 2024-11 / 2024-Q4",
    )

    period_start: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="周期开始日期",
    )

    period_end: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="周期结束日期",
    )

    # ===========================================
    # 客户统计
    # ===========================================

    total_customers: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="总客户数",
    )

    total_calls: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="总通话数",
    )

    connected_calls: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="接通数",
    )

    connect_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="接通率",
    )

    avg_duration: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="平均通话时长(秒)",
    )

    # ===========================================
    # 满意度分布
    # ===========================================

    satisfied_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="满意客户数",
    )

    satisfied_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="满意率",
    )

    neutral_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="一般客户数",
    )

    unsatisfied_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="不满意客户数",
    )

    # ===========================================
    # 情绪分布
    # ===========================================

    positive_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="积极情绪客户数",
    )

    negative_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="消极情绪客户数",
    )

    avg_sentiment_score: Mapped[float] = mapped_column(
        Float,
        default=0.5,
        comment="平均情绪得分",
    )

    # ===========================================
    # 风险分布
    # ===========================================

    high_complaint_customers: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="高投诉风险客户数",
    )

    high_complaint_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="高投诉风险占比",
    )

    high_churn_customers: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="高流失风险客户数",
    )

    high_churn_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="高流失风险占比",
    )

    # ===========================================
    # 元数据
    # ===========================================

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="计算时间",
    )

    # ===========================================
    # 约束和索引
    # ===========================================

    __table_args__ = (
        UniqueConstraint("task_id", "period_type", "period_key", name="uq_task_period"),
        Index("idx_task_period", "task_id", "period_type", "period_key"),
        Index("idx_period_key", "period_type", "period_key"),
        {"comment": "场景画像汇总表"},
    )

    def __repr__(self) -> str:
        return f"<TaskPortraitSummary(task={self.task_id}, period={self.period_key})>"
