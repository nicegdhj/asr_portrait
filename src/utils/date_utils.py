"""
日期处理工具

支持自然周、自然月、自然季度的计算
使用 ISO 周编号 (如 2024-W49)
"""

from datetime import date, datetime, timedelta
from typing import Literal

from dateutil.relativedelta import relativedelta

PeriodType = Literal["week", "month", "quarter"]


def get_week_key(dt: date | datetime) -> str:
    """
    获取 ISO 周编号
    
    Args:
        dt: 日期
        
    Returns:
        如 "2024-W49"
    """
    if isinstance(dt, datetime):
        dt = dt.date()
    iso_year, iso_week, _ = dt.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def get_month_key(dt: date | datetime) -> str:
    """
    获取月份编号
    
    Args:
        dt: 日期
        
    Returns:
        如 "2024-12"
    """
    if isinstance(dt, datetime):
        dt = dt.date()
    return dt.strftime("%Y-%m")


def get_quarter_key(dt: date | datetime) -> str:
    """
    获取季度编号
    
    Args:
        dt: 日期
        
    Returns:
        如 "2024-Q4"
    """
    if isinstance(dt, datetime):
        dt = dt.date()
    quarter = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{quarter}"


def get_week_range(dt: date | datetime) -> tuple[date, date]:
    """
    获取指定日期所在周的起止日期
    
    Args:
        dt: 日期
        
    Returns:
        (周一, 周日)
    """
    if isinstance(dt, datetime):
        dt = dt.date()
    # ISO 周从周一开始
    weekday = dt.weekday()
    week_start = dt - timedelta(days=weekday)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def get_month_range(dt: date | datetime) -> tuple[date, date]:
    """
    获取指定日期所在月的起止日期
    
    Args:
        dt: 日期
        
    Returns:
        (月初, 月末)
    """
    if isinstance(dt, datetime):
        dt = dt.date()
    month_start = dt.replace(day=1)
    next_month = month_start + relativedelta(months=1)
    month_end = next_month - timedelta(days=1)
    return month_start, month_end


def get_quarter_range(dt: date | datetime) -> tuple[date, date]:
    """
    获取指定日期所在季度的起止日期
    
    Args:
        dt: 日期
        
    Returns:
        (季度初, 季度末)
    """
    if isinstance(dt, datetime):
        dt = dt.date()
    quarter = (dt.month - 1) // 3
    quarter_start = date(dt.year, quarter * 3 + 1, 1)
    quarter_end = quarter_start + relativedelta(months=3) - timedelta(days=1)
    return quarter_start, quarter_end


def get_period_range(period_type: PeriodType, period_key: str) -> tuple[date, date]:
    """
    根据周期类型和周期编号获取起止日期
    
    Args:
        period_type: "week" | "month" | "quarter"
        period_key: 如 "2024-W49" | "2024-12" | "2024-Q4"
        
    Returns:
        (开始日期, 结束日期)
    """
    if period_type == "week":
        # 解析 ISO 周 "2024-W49"
        year, week = period_key.split("-W")
        year = int(year)
        week = int(week)
        # 计算该周的周一
        jan4 = date(year, 1, 4)  # 1月4日一定在第1周
        week_start = jan4 - timedelta(days=jan4.weekday()) + timedelta(weeks=week - 1)
        week_end = week_start + timedelta(days=6)
        return week_start, week_end
    
    elif period_type == "month":
        # 解析月份 "2024-12"
        year, month = period_key.split("-")
        dt = date(int(year), int(month), 1)
        return get_month_range(dt)
    
    elif period_type == "quarter":
        # 解析季度 "2024-Q4"
        year, q = period_key.split("-Q")
        year = int(year)
        quarter = int(q)
        quarter_start = date(year, (quarter - 1) * 3 + 1, 1)
        quarter_end = quarter_start + relativedelta(months=3) - timedelta(days=1)
        return quarter_start, quarter_end
    
    else:
        raise ValueError(f"不支持的周期类型: {period_type}")


def get_current_week() -> tuple[str, date, date]:
    """
    获取当前周信息
    
    Returns:
        (周编号, 周一, 周日)
    """
    today = date.today()
    week_key = get_week_key(today)
    start, end = get_week_range(today)
    return week_key, start, end


def get_current_month() -> tuple[str, date, date]:
    """
    获取当前月信息
    
    Returns:
        (月份编号, 月初, 月末)
    """
    today = date.today()
    month_key = get_month_key(today)
    start, end = get_month_range(today)
    return month_key, start, end


def get_current_quarter() -> tuple[str, date, date]:
    """
    获取当前季度信息
    
    Returns:
        (季度编号, 季度初, 季度末)
    """
    today = date.today()
    quarter_key = get_quarter_key(today)
    start, end = get_quarter_range(today)
    return quarter_key, start, end


def get_recent_periods(
    period_type: PeriodType,
    count: int = 12,
    include_current: bool = False,
) -> list[tuple[str, date, date]]:
    """
    获取最近 N 个周期
    
    Args:
        period_type: "week" | "month" | "quarter"
        count: 返回的周期数量
        include_current: 是否包含当前周期
        
    Returns:
        [(周期编号, 开始日期, 结束日期), ...]
        按时间倒序排列
    """
    today = date.today()
    periods = []
    
    if period_type == "week":
        # 从当前周或上周开始
        if not include_current:
            today = today - timedelta(weeks=1)
        for i in range(count):
            dt = today - timedelta(weeks=i)
            week_key = get_week_key(dt)
            start, end = get_week_range(dt)
            periods.append((week_key, start, end))
    
    elif period_type == "month":
        # 从当前月或上月开始
        current = today.replace(day=1)
        if not include_current:
            current = current - relativedelta(months=1)
        for i in range(count):
            dt = current - relativedelta(months=i)
            month_key = get_month_key(dt)
            start, end = get_month_range(dt)
            periods.append((month_key, start, end))
    
    elif period_type == "quarter":
        # 从当前季度或上季度开始
        quarter = (today.month - 1) // 3
        current = date(today.year, quarter * 3 + 1, 1)
        if not include_current:
            current = current - relativedelta(months=3)
        for i in range(count):
            dt = current - relativedelta(months=i * 3)
            quarter_key = get_quarter_key(dt)
            start, end = get_quarter_range(dt)
            periods.append((quarter_key, start, end))
    
    # 去重并排序
    seen = set()
    unique_periods = []
    for p in periods:
        if p[0] not in seen:
            seen.add(p[0])
            unique_periods.append(p)
    
    return unique_periods[:count]


def get_period_label(period_type: PeriodType, period_key: str) -> str:
    """
    获取周期的人类可读标签
    
    Args:
        period_type: "week" | "month" | "quarter"
        period_key: 周期编号
        
    Returns:
        如 "2024年第49周" | "2024年12月" | "2024年第4季度"
    """
    if period_type == "week":
        year, week = period_key.split("-W")
        return f"{year}年第{int(week)}周"
    
    elif period_type == "month":
        year, month = period_key.split("-")
        return f"{year}年{int(month)}月"
    
    elif period_type == "quarter":
        year, q = period_key.split("-Q")
        return f"{year}年第{q}季度"
    
    return period_key


def is_period_completed(period_type: PeriodType, period_key: str) -> bool:
    """
    判断周期是否已完成 (已过去)
    
    Args:
        period_type: 周期类型
        period_key: 周期编号
        
    Returns:
        True 如果周期已结束
    """
    _, end = get_period_range(period_type, period_key)
    return date.today() > end

