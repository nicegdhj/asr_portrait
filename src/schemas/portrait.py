"""
用户画像数据模式
"""

from datetime import date
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CallStatsResponse(BaseModel):
    """通话统计指标"""
    
    total_calls: int = Field(default=0, description="总通话次数")
    connected_calls: int = Field(default=0, description="接通次数")
    connect_rate: float = Field(default=0.0, description="接通率")
    total_duration: int = Field(default=0, description="总通话时长(秒)")
    avg_duration: float = Field(default=0.0, description="平均通话时长(秒)")
    max_duration: int = Field(default=0, description="最大通话时长(秒)")
    min_duration: int = Field(default=0, description="最小通话时长(秒)")
    total_rounds: int = Field(default=0, description="总交互轮次")
    avg_rounds: float = Field(default=0.0, description="平均交互轮次")


class IntentionDistribution(BaseModel):
    """意向等级分布"""
    
    A: int = Field(default=0, description="A级意向数")
    B: int = Field(default=0, description="B级意向数")
    C: int = Field(default=0, description="C级意向数")
    D: int = Field(default=0, description="D级意向数")
    E: int = Field(default=0, description="E级意向数")
    F: int = Field(default=0, description="F级意向数")


class HangupDistribution(BaseModel):
    """挂断分布"""
    
    robot: int = Field(default=0, description="机器人挂断次数")
    user: int = Field(default=0, description="客户挂断次数")


class FailReasonItem(BaseModel):
    """未接原因项"""
    
    reason: str = Field(..., description="原因名称")
    code: int = Field(..., description="状态码")
    count: int = Field(default=0, description="次数")
    rate: float = Field(default=0.0, description="占比")


class FailReasonDistribution(BaseModel):
    """未接原因分布"""
    
    total: int = Field(default=0, description="未接通总数")
    items: List[FailReasonItem] = Field(default_factory=list, description="分布明细")


class SentimentAnalysis(BaseModel):
    """情感分析结果"""
    
    positive: int = Field(default=0, description="积极情绪次数")
    neutral: int = Field(default=0, description="中性情绪次数")
    negative: int = Field(default=0, description="消极情绪次数")
    avg_score: float = Field(default=0.0, description="平均情绪得分")
    
    @property
    def total(self) -> int:
        """总数"""
        return self.positive + self.neutral + self.negative
    
    @property
    def positive_rate(self) -> float:
        """积极占比"""
        return self.positive / self.total if self.total > 0 else 0.0
    
    @property
    def negative_rate(self) -> float:
        """消极占比"""
        return self.negative / self.total if self.total > 0 else 0.0


class RiskLevel(BaseModel):
    """风险等级分布"""
    
    high: int = Field(default=0, description="高风险次数")
    medium: int = Field(default=0, description="中风险次数")
    low: int = Field(default=0, description="低风险次数")


class RiskAnalysis(BaseModel):
    """风险分析结果"""
    
    complaint_risk: RiskLevel = Field(
        default_factory=RiskLevel,
        description="投诉风险分布",
    )
    churn_risk: RiskLevel = Field(
        default_factory=RiskLevel,
        description="流失风险分布",
    )


class PeriodDetail(BaseModel):
    """周期详情"""
    
    type: Literal["week", "month", "quarter"] = Field(..., description="周期类型")
    key: str = Field(..., description="周期编号")
    start: date = Field(..., description="开始日期")
    end: date = Field(..., description="结束日期")


class UserPortraitResponse(BaseModel):
    """用户画像完整响应"""
    
    user_id: str = Field(..., description="用户ID")
    period: PeriodDetail = Field(..., description="周期信息")
    call_stats: CallStatsResponse = Field(
        default_factory=CallStatsResponse,
        description="通话统计",
    )
    intention_dist: IntentionDistribution = Field(
        default_factory=IntentionDistribution,
        description="意向等级分布",
    )
    hangup_dist: HangupDistribution = Field(
        default_factory=HangupDistribution,
        description="挂断分布",
    )
    fail_reason_dist: FailReasonDistribution = Field(
        default_factory=FailReasonDistribution,
        description="未接原因分布",
    )
    sentiment_analysis: SentimentAnalysis = Field(
        default_factory=SentimentAnalysis,
        description="情感分析",
    )
    risk_analysis: RiskAnalysis = Field(
        default_factory=RiskAnalysis,
        description="风险分析",
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "uuid-string",
                "period": {
                    "type": "week",
                    "key": "2024-W49",
                    "start": "2024-12-02",
                    "end": "2024-12-08",
                },
                "call_stats": {
                    "total_calls": 156,
                    "connected_calls": 98,
                    "connect_rate": 0.628,
                    "total_duration": 14520,
                    "avg_duration": 148.2,
                    "max_duration": 320,
                    "min_duration": 10,
                    "total_rounds": 342,
                    "avg_rounds": 3.49,
                },
                "intention_dist": {"A": 12, "B": 28, "C": 35, "D": 15, "E": 5, "F": 3},
                "hangup_dist": {"robot": 45, "user": 53},
                "fail_reason_dist": {
                    "total": 58,
                    "items": [
                        {"reason": "无应答", "code": 4, "count": 22, "rate": 0.38},
                        {"reason": "拒接", "code": 3, "count": 18, "rate": 0.31},
                    ],
                },
                "sentiment_analysis": {
                    "positive": 42,
                    "neutral": 38,
                    "negative": 18,
                    "avg_score": 0.62,
                },
                "risk_analysis": {
                    "complaint_risk": {"high": 3, "medium": 12, "low": 83},
                    "churn_risk": {"high": 5, "medium": 18, "low": 75},
                },
            }
        }


class TrendDataPoint(BaseModel):
    """趋势数据点"""
    
    period_key: str = Field(..., description="周期编号")
    label: str = Field(..., description="周期标签")
    value: float = Field(..., description="指标值")


class TrendResponse(BaseModel):
    """趋势数据响应"""
    
    metric: str = Field(..., description="指标名称")
    period_type: Literal["week", "month", "quarter"] = Field(..., description="周期类型")
    series: List[TrendDataPoint] = Field(default_factory=list, description="数据序列")
    
    class Config:
        json_schema_extra = {
            "example": {
                "metric": "connect_rate",
                "period_type": "week",
                "series": [
                    {"period_key": "2024-W46", "label": "第46周", "value": 0.58},
                    {"period_key": "2024-W47", "label": "第47周", "value": 0.61},
                    {"period_key": "2024-W48", "label": "第48周", "value": 0.59},
                    {"period_key": "2024-W49", "label": "第49周", "value": 0.63},
                ],
            }
        }


class PortraitSummaryResponse(BaseModel):
    """画像汇总响应 (全量用户)"""
    
    period: PeriodDetail = Field(..., description="周期信息")
    total_users: int = Field(default=0, description="用户总数")
    call_stats: CallStatsResponse = Field(
        default_factory=CallStatsResponse,
        description="通话统计汇总",
    )
    intention_dist: IntentionDistribution = Field(
        default_factory=IntentionDistribution,
        description="意向等级分布汇总",
    )
    sentiment_summary: SentimentAnalysis = Field(
        default_factory=SentimentAnalysis,
        description="情感分析汇总",
    )
    risk_summary: RiskAnalysis = Field(
        default_factory=RiskAnalysis,
        description="风险分析汇总",
    )

