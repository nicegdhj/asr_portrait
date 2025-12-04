"""
周期相关数据模式
"""

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PeriodInfo(BaseModel):
    """周期信息"""
    
    key: str = Field(..., description="周期编号", examples=["2024-W49", "2024-12", "2024-Q4"])
    label: str = Field(..., description="周期标签", examples=["2024年第49周", "2024年12月", "2024年第4季度"])
    start: date = Field(..., description="开始日期")
    end: date = Field(..., description="结束日期")
    status: str = Field(
        default="completed",
        description="状态: pending/computing/completed",
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "key": "2024-W49",
                "label": "2024年第49周",
                "start": "2024-12-02",
                "end": "2024-12-08",
                "status": "completed",
            }
        }


class PeriodListResponse(BaseModel):
    """周期列表响应"""
    
    type: Literal["week", "month", "quarter"] = Field(..., description="周期类型")
    periods: List[PeriodInfo] = Field(default_factory=list, description="周期列表")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "week",
                "periods": [
                    {
                        "key": "2024-W49",
                        "label": "2024年第49周",
                        "start": "2024-12-02",
                        "end": "2024-12-08",
                        "status": "completed",
                    },
                    {
                        "key": "2024-W48",
                        "label": "2024年第48周",
                        "start": "2024-11-25",
                        "end": "2024-12-01",
                        "status": "completed",
                    },
                ],
            }
        }


class PeriodQuery(BaseModel):
    """周期查询参数"""
    
    period_type: Literal["week", "month", "quarter"] = Field(
        default="week",
        description="周期类型",
    )
    period_key: Optional[str] = Field(
        default=None,
        description="指定周期编号，不传则返回最近一个已完成周期",
    )

