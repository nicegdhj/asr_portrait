"""
动态表名处理工具

处理智能外呼系统的分表逻辑：
- 通话记录表: autodialer_call_record_{YYYY_MM}
- 通话详情表: autodialer_call_record_detail_{YYYY_MM}
- 号码表: autodialer_number_{task_uuid}

分表后缀基于任务创建时间 (create_datetime)
"""

from datetime import date, datetime
from typing import List

from dateutil.relativedelta import relativedelta


def get_call_record_table(task_create_datetime: datetime | date) -> str:
    """
    根据任务创建时间获取通话记录表名
    
    Args:
        task_create_datetime: 任务创建时间
        
    Returns:
        表名，如 "autodialer_call_record_2024_11"
    """
    if isinstance(task_create_datetime, datetime):
        task_create_datetime = task_create_datetime.date()
    suffix = task_create_datetime.strftime("%Y_%m")
    return f"autodialer_call_record_{suffix}"


def get_call_record_detail_table(task_create_datetime: datetime | date) -> str:
    """
    根据任务创建时间获取通话详情表名
    
    Args:
        task_create_datetime: 任务创建时间
        
    Returns:
        表名，如 "autodialer_call_record_detail_2024_11"
    """
    if isinstance(task_create_datetime, datetime):
        task_create_datetime = task_create_datetime.date()
    suffix = task_create_datetime.strftime("%Y_%m")
    return f"autodialer_call_record_detail_{suffix}"


def get_number_table(task_uuid: str) -> str:
    """
    根据任务ID获取号码表名
    
    Args:
        task_uuid: 任务 UUID
        
    Returns:
        表名，如 "autodialer_number_abc123"
    """
    # 移除 UUID 中的连字符
    clean_uuid = task_uuid.replace("-", "")
    return f"autodialer_number_{clean_uuid}"


def get_tables_for_period(
    start_date: date,
    end_date: date,
    table_type: str = "call_record",
) -> List[str]:
    """
    获取时间区间内涉及的所有分表
    
    按月分表，一个季度最多涉及3-4个月的表
    
    Args:
        start_date: 开始日期
        end_date: 结束日期
        table_type: "call_record" 或 "call_record_detail"
        
    Returns:
        表名列表，如 ["autodialer_call_record_2024_10", "autodialer_call_record_2024_11", ...]
    """
    tables = []
    current = start_date.replace(day=1)
    
    while current <= end_date:
        suffix = current.strftime("%Y_%m")
        if table_type == "call_record":
            tables.append(f"autodialer_call_record_{suffix}")
        elif table_type == "call_record_detail":
            tables.append(f"autodialer_call_record_detail_{suffix}")
        else:
            raise ValueError(f"不支持的表类型: {table_type}")
        
        # 下个月
        current = current + relativedelta(months=1)
    
    return tables


def get_table_suffix_from_date(dt: datetime | date) -> str:
    """
    从日期获取表后缀
    
    Args:
        dt: 日期
        
    Returns:
        后缀，如 "2024_11"
    """
    if isinstance(dt, datetime):
        dt = dt.date()
    return dt.strftime("%Y_%m")


def parse_table_suffix(suffix: str) -> date:
    """
    解析表后缀获取日期
    
    Args:
        suffix: 表后缀，如 "2024_11"
        
    Returns:
        对应月份的第一天
    """
    year, month = suffix.split("_")
    return date(int(year), int(month), 1)


def check_table_exists_sql(table_name: str) -> str:
    """
    生成检查表是否存在的 SQL
    
    Args:
        table_name: 表名
        
    Returns:
        SQL 语句 (MySQL)
    """
    return f"""
    SELECT COUNT(*) as cnt 
    FROM information_schema.tables 
    WHERE table_schema = DATABASE() 
      AND table_name = '{table_name}'
    """


def build_union_query(
    tables: List[str],
    select_clause: str,
    where_clause: str = "",
    order_clause: str = "",
    limit: int | None = None,
) -> str:
    """
    构建多表 UNION ALL 查询
    
    用于跨月查询通话记录
    
    Args:
        tables: 表名列表
        select_clause: SELECT 字段，如 "id, callid, duration"
        where_clause: WHERE 条件，如 "WHERE user_id = 'xxx'"
        order_clause: ORDER BY 子句，如 "ORDER BY created_at DESC"
        limit: LIMIT 数量
        
    Returns:
        SQL 查询语句
    """
    if not tables:
        raise ValueError("表名列表不能为空")
    
    queries = []
    for table in tables:
        q = f"SELECT {select_clause} FROM {table}"
        if where_clause:
            q += f" {where_clause}"
        queries.append(q)
    
    sql = " UNION ALL ".join(queries)
    
    if order_clause:
        sql = f"SELECT * FROM ({sql}) AS combined {order_clause}"
    
    if limit:
        sql += f" LIMIT {limit}"
    
    return sql


# ===========================================
# 源数据表字段映射
# ===========================================

# 通话记录表关键字段
CALL_RECORD_FIELDS = {
    "id": "记录ID (UUID)",
    "task_id": "任务ID",
    "callid": "通话ID (关联详情表)",
    "user_id": "用户ID",
    "callee": "被叫号码",
    "bill": "计费时长(毫秒)",
    "duration": "总时长(毫秒)",
    "rounds": "交互轮次",
    "score": "评分",
    "hangup_disposition": "挂断方: 1=机器人, 2=客户",
    "level_id": "意向等级ID",
    "level_name": "意向等级名称",
    "intention_results": "意向标签(A/B/C/D/E/F)",
    "gender": "性别: 0=未知, 1=女, 2=男",
    "calldate": "呼叫时间",
    "answerdate": "应答时间",
    "hangupdate": "挂断时间",
    "bridge_answerdate": "转接应答时间",
    "created_at": "创建时间",
}

# 通话详情表关键字段
CALL_RECORD_DETAIL_FIELDS = {
    "id": "详情ID",
    "record_id": "关联通话记录ID",
    "callid": "通话ID",
    "task_id": "任务ID",
    "notify": "通知类型",
    "question": "ASR识别的用户说话内容",
    "answer_text": "机器人回复文本",
    "answer_content": "回复内容",
    "score": "评分",
    "speak_ms": "说话时长(毫秒)",
    "play_ms": "播放时长(毫秒)",
    "sequence": "对话顺序",
    "bridge_status": "转接状态",
    "created_at": "创建时间",
}

# 号码状态映射
NUMBER_STATUS_MAP = {
    0: "等待呼叫",
    1: "呼叫成功",
    2: "运营商拦截",
    3: "拒接",
    4: "无应答",
    5: "空号",
    6: "关机",
    7: "停机",
    8: "占线/用户正忙",
    9: "呼入限制",
    10: "欠费",
    11: "黑名单",
    12: "用户屏蔽",
}


def get_number_status_label(status: int) -> str:
    """获取号码状态的中文标签"""
    return NUMBER_STATUS_MAP.get(status, f"未知状态({status})")

