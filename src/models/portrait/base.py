"""
SQLAlchemy 基础模型

定义所有画像数据表的基类
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PortraitBase(DeclarativeBase):
    """画像数据表基类"""
    
    # 启用类型注解
    type_annotation_map = {
        uuid.UUID: UUID(as_uuid=True),
    }


class TimestampMixin:
    """时间戳混入类"""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )


class UUIDPrimaryKeyMixin:
    """UUID 主键混入类"""
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="主键ID",
    )

