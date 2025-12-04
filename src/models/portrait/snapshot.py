"""
用户画像快照表

按自然周、自然月、自然季度存储用户画像聚合数据
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import PortraitBase, UUIDPrimaryKeyMixin


class UserPortraitSnapshot(PortraitBase, UUIDPrimaryKeyMixin):
    """
    用户画像快照表
    
    存储按周期聚合的用户画像数据，支持按周/月/季度展示柱状图等统计
    """
    
    __tablename__ = "user_portrait_snapshot"
    
    # ===========================================
    # 周期信息
    # ===========================================
    
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="用户ID",
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
    # 通话统计指标
    # ===========================================
    
    total_calls: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="总通话次数",
    )
    
    connected_calls: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="接通次数",
    )
    
    connect_rate: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="接通率",
    )
    
    total_duration: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="总通话时长(秒)",
    )
    
    avg_duration: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="平均通话时长(秒)",
    )
    
    max_duration: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="最大通话时长(秒)",
    )
    
    min_duration: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="最小通话时长(秒)",
    )
    
    total_rounds: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="总交互轮次",
    )
    
    avg_rounds: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="平均交互轮次",
    )
    
    # ===========================================
    # 意向等级分布
    # ===========================================
    
    level_a_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="A级意向数",
    )
    
    level_b_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="B级意向数",
    )
    
    level_c_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="C级意向数",
    )
    
    level_d_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="D级意向数",
    )
    
    level_e_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="E级意向数",
    )
    
    level_f_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="F级意向数",
    )
    
    # ===========================================
    # 挂断分布
    # ===========================================
    
    robot_hangup_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="机器人挂断次数",
    )
    
    user_hangup_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="客户挂断次数",
    )
    
    # ===========================================
    # 未接通原因分布 (JSONB)
    # ===========================================
    
    fail_reason_dist: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        comment="未接原因分布: {'busy': 10, 'no_answer': 5, ...}",
    )
    
    # ===========================================
    # LLM 分析指标
    # ===========================================
    
    positive_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="积极情绪次数",
    )
    
    neutral_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="中性情绪次数",
    )
    
    negative_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="消极情绪次数",
    )
    
    avg_sentiment_score: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        comment="平均情绪得分",
    )
    
    high_complaint_risk: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="高投诉风险次数",
    )
    
    medium_complaint_risk: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="中投诉风险次数",
    )
    
    low_complaint_risk: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="低投诉风险次数",
    )
    
    high_churn_risk: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="高流失风险次数",
    )
    
    medium_churn_risk: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="中流失风险次数",
    )
    
    low_churn_risk: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="低流失风险次数",
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
        UniqueConstraint("user_id", "period_type", "period_key", name="uq_user_period"),
        Index("idx_period", "period_type", "period_key"),
        Index("idx_user_period", "user_id", "period_type"),
        Index("idx_period_start", "period_start"),
        {"comment": "用户画像快照表"},
    )
    
    def __repr__(self) -> str:
        return f"<UserPortraitSnapshot(user={self.user_id}, period={self.period_key})>"

