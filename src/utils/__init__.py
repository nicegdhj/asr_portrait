"""工具函数模块"""

from .date_utils import (
    get_week_key,
    get_month_key,
    get_quarter_key,
    get_period_range,
    get_current_week,
    get_current_month,
    get_current_quarter,
    get_recent_periods,
)
from .table_utils import (
    get_call_record_table,
    get_call_record_detail_table,
    get_number_table,
    get_tables_for_period,
)

__all__ = [
    # 日期工具
    "get_week_key",
    "get_month_key",
    "get_quarter_key",
    "get_period_range",
    "get_current_week",
    "get_current_month",
    "get_current_quarter",
    "get_recent_periods",
    # 表名工具
    "get_call_record_table",
    "get_call_record_detail_table",
    "get_number_table",
    "get_tables_for_period",
]

