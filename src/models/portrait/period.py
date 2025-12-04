"""
周期管理表

记录已计算的周期状态，用于增量计算和状态追踪
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import PortraitBase, UUIDPrimaryKeyMixin


class PeriodRegistry(PortraitBase, UUIDPrimaryKeyMixin):
    """
    周期注册表
    
    记录已计算完成的周期，用于：
    1. 避免重复计算
    2. 追踪计算状态
    3. 前端展示可选周期列表
    """
    
    __tablename__ = "period_registry"
    
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
    
    status: Mapped[str] = mapped_column(
        String(16),
        default="pending",
        comment="状态: pending/computing/completed/failed",
    )
    
    total_users: Mapped[Optional[int]] = mapped_column(
        nullable=True,
        comment="涉及用户数",
    )
    
    total_records: Mapped[Optional[int]] = mapped_column(
        nullable=True,
        comment="涉及记录数",
    )
    
    computed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="计算完成时间",
    )
    
    error_message: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="错误信息",
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    
    __table_args__ = (
        UniqueConstraint("period_type", "period_key", name="uq_period_type_key"),
        {"comment": "周期注册表"},
    )
    
    def __repr__(self) -> str:
        return f"<PeriodRegistry(type={self.period_type}, key={self.period_key}, status={self.status})>"
    
    @property
    def label(self) -> str:
        """获取人类可读的周期标签"""
        if self.period_type == "week":
            year, week = self.period_key.split("-W")
            return f"{year}年第{int(week)}周"
        elif self.period_type == "month":
            year, month = self.period_key.split("-")
            return f"{year}年{int(month)}月"
        elif self.period_type == "quarter":
            year, q = self.period_key.split("-Q")
            return f"{year}年第{q}季度"
        return self.period_key
    
    @property
    def is_completed(self) -> bool:
        """是否已完成计算"""
        return self.status == "completed"

