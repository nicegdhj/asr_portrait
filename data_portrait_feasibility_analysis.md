# 数据画像指标可行性分析报告

## 一、结论

✅ **所有请求的画像统计指标均可在现有数据条件下实现**

---

## 二、数据表结构确认

通过分析 `deploy-saas/app/Models/AutoDialer/` 目录下的模型代码，确认以下核心表结构：

### 2.1 通话记录表 `autodialer_call_record_{YYYY_MM}`

```python
# 分表后缀格式: YYYY_MM (如 2024_11)
# 关键字段:
{
    "id": "uuid",                    # 记录ID
    "task_id": "uuid",               # 任务ID
    "callid": "string",              # 通话ID (关联detail表)
    "user_id": "uuid",               # 用户ID
    "callee": "string",              # 被叫号码
    "bill": "int",                   # 计费时长(毫秒)
    "duration": "int",               # 总时长(毫秒)
    "rounds": "int",                 # 交互轮次
    "score": "int",                  # 评分
    "hangup_disposition": "int",     # 挂断方: 1=机器人, 2=客户
    "level_id": "uuid",              # 意向等级ID
    "level_name": "string",          # 意向等级名称
    "intention_results": "string",   # 意向标签(A/B/C/D/E/F)
    "gender": "int",                 # 性别: 0=未知, 1=女, 2=男
    "calldate": "datetime",          # 呼叫时间
    "answerdate": "datetime",        # 应答时间
    "hangupdate": "datetime",        # 挂断时间
    "bridge_answerdate": "datetime", # 转接应答时间(判断转接成功)
    "created_at": "datetime"
}
```

### 2.2 通话详情表 `autodialer_call_record_detail_{YYYY_MM}`

```python
# 分表后缀格式: 与通话记录表一致
# 关键字段:
{
    "id": "uuid",
    "record_id": "uuid",             # 关联通话记录ID
    "callid": "string",              # 通话ID
    "task_id": "uuid",
    "notify": "string",              # 通知类型: "asrmessage_notify"
    "question": "string",            # ⭐ ASR识别的用户说话内容
    "answer_text": "string",         # 机器人回复文本
    "answer_content": "string",      # 回复内容
    "score": "int",
    "speak_ms": "int",               # 说话时长(毫秒)
    "play_ms": "int",                # 播放时长(毫秒)
    "sequence": "int",               # 对话顺序
    "bridge_status": "int",          # 转接状态
    "created_at": "datetime"
}
```

### 2.3 任务表 `autodialer_task`

```python
{
    "uuid": "primary_key",           # 任务ID
    "name": "string",                # 任务名称
    "user_id": "uuid",               # 用户ID
    "create_datetime": "datetime",   # ⭐ 任务创建时间(用于确定分表后缀)
    "destination_extension": "int",  # 话术组ID
    "maximumcall": "int",            # 最大并发
    "enable": "boolean",             # 是否启用
    "start": "int"                   # 任务状态
}
```

### 2.4 号码表 `autodialer_number_{task_uuid}`

```python
# 分表后缀: task_uuid
{
    "id": "int",
    "number": "string",              # 电话号码
    "status": "string",              # 呼叫结果状态码
    "state": "int",                  # 号码状态
    "time": "int",                   # 拨打次数
    "bill": "int",                   # 计费时长
    "callid": "string",              # 最后通话ID
    "recycle": "int",                # 回收次数
    "created_at": "datetime"
}
```

---

## 三、各画像指标计算口径

| 指标名称 | 数据来源表 | 计算逻辑/字段 | 可行性 |
|---------|-----------|-------------|--------|
| **挂断方** | `call_record` | `hangup_disposition`: `1`=机器人挂断, `2`=客户挂断 | ✅ 直接读取 |
| **未接原因** | `number` | `status` 字段，对照 `Number::enumStatusLifeCycle()` 枚举 | ✅ 直接读取 |
| **有效通话率** | `call_record` + `number` | `COUNT(bill > 0) / COUNT(total_calls)` | ✅ 可计算 |
| **通话互动率** | `call_record_detail` | `COUNT(notify='asrmessage_notify') / SUM(rounds)` | ✅ 可计算 |
| **平均交互次数** | `call_record` | `AVG(rounds)` | ✅ 直接聚合 |
| **平均通话时长** | `call_record` | `AVG(bill)` (毫秒需转换秒) | ✅ 直接聚合 |
| **最大通话时长** | `call_record` | `MAX(bill)` | ✅ 直接聚合 |
| **最小通话时长** | `call_record` | `MIN(bill) WHERE bill > 0` | ✅ 直接聚合 |
| **用户态度情绪** | `call_record_detail` | 对 `question` 字段进行 NLP 情感分析 | ⚠️ 需额外 NLP |
| **用户满意度** | `tags` + `taggables` | 关联查询标签 (如"满意"、"一般") | ✅ 可关联 |
| **用户不满意原因** | `tags` + `taggables` | 查询"不满意"相关标签 | ✅ 可关联 |
| **投诉风险** | `call_record_detail` | 检索 `question` 包含敏感词("投诉"、"举报") | ⚠️ 需关键词匹配 |
| **流失风险** | `call_record_detail` | 检索 `question` 包含流失词("换套餐"、"不用了") | ⚠️ 需关键词匹配 |

---

## 四、数据读取逻辑

### 4.1 动态表名构建

```python
from datetime import datetime

def get_call_record_table(task_create_datetime: datetime) -> str:
    """根据任务创建时间获取通话记录表名"""
    suffix = task_create_datetime.strftime("%Y_%m")  # 如 2024_11
    return f"autodialer_call_record_{suffix}"

def get_call_record_detail_table(task_create_datetime: datetime) -> str:
    """根据任务创建时间获取通话详情表名"""
    suffix = task_create_datetime.strftime("%Y_%m")
    return f"autodialer_call_record_detail_{suffix}"

def get_number_table(task_uuid: str) -> str:
    """根据任务ID获取号码表名"""
    return f"autodialer_number_{task_uuid}"
```

### 4.2 跨月查询策略

按周/月/季度查询时，可能涉及多个分表，建议：

```python
from typing import List
from datetime import datetime, timedelta

def get_tables_for_period(start_date: datetime, end_date: datetime) -> List[str]:
    """获取时间区间内涉及的所有分表"""
    tables = []
    current = start_date.replace(day=1)
    while current <= end_date:
        suffix = current.strftime("%Y_%m")
        tables.append(f"autodialer_call_record_{suffix}")
        # 下个月
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return tables
```

### 4.3 示例：获取一次通话的 ASR 数据

```python
async def get_call_asr_content(callid: str, task_create_datetime: datetime) -> List[dict]:
    """
    获取一次通话的所有 ASR 识别内容
    """
    detail_table = get_call_record_detail_table(task_create_datetime)
    
    sql = f"""
    SELECT 
        sequence,
        question,           -- 用户说话内容 (ASR识别结果)
        answer_text,        -- 机器人回复
        speak_ms,           -- 用户说话时长
        created_at
    FROM {detail_table}
    WHERE callid = :callid
      AND notify = 'asrmessage_notify'
    ORDER BY sequence ASC
    """
    
    return await db.fetch_all(sql, {"callid": callid})
```

---

## 五、未接原因状态码映射

根据 `Number.php` 模型中的常量定义：

```python
NUMBER_STATUS_MAP = {
    0: "等待呼叫",
    1: "呼叫成功",
    2: "运营商拦截",      # 原"线路故障"
    3: "拒接",
    4: "无应答",
    5: "空号",
    6: "关机",
    7: "停机",
    8: "占线/用户正忙",
    9: "呼入限制",
    10: "欠费",
    11: "黑名单",
    12: "用户屏蔽"        # 原"呼损"
}
```

---

## 六、情感分析与风险检测建议

### 6.1 情感分析方案

对于"用户态度情绪"指标，可选方案：

| 方案 | 实现方式 | 优缺点 |
|-----|---------|-------|
| **本地模型** | 使用 `transformers` + 中文情感模型 | 离线可用，需GPU |
| **关键词匹配** | 维护正/负面词库 | 简单高效，精度有限 |
| **LLM API** | 调用 OpenAI/通义千问 | 效果好，有成本和延迟 |

**推荐**：使用关键词匹配作为基础方案，后续可升级为本地模型。

### 6.2 风险关键词库示例

```python
# 投诉风险关键词
COMPLAINT_KEYWORDS = [
    "投诉", "举报", "12315", "消协", "工信部", 
    "律师", "起诉", "骗子", "诈骗", "报警"
]

# 流失风险关键词
CHURN_KEYWORDS = [
    "不用了", "换套餐", "换运营商", "取消", "退订", 
    "停用", "销户", "不需要", "不想要", "别打了"
]

# 正面情绪关键词
POSITIVE_KEYWORDS = [
    "好的", "可以", "没问题", "行", "同意", 
    "感兴趣", "考虑", "了解一下", "谢谢"
]

# 负面情绪关键词
NEGATIVE_KEYWORDS = [
    "不要", "不用", "烦", "别打", "骚扰", 
    "拉黑", "讨厌", "滚", "神经病"
]
```

---

## 七、数据库连接配置

从 `deploy-saas/config/database.php` 推断，数据库连接需要：

```python
# MySQL 连接配置
MYSQL_CONFIG = {
    "host": "xxx",
    "port": 3306,
    "database": "deploy_saas",   # 主库名
    "username": "xxx",
    "password": "xxx"
}

# 如果使用 MongoDB 存储大量通话记录 (可选)
MONGO_CONFIG = {
    "host": "xxx",
    "port": 27017,
    "database": "deploy_saas"
}
```

---

## 八、API 设计建议

### 8.1 时间维度查询参数

```python
from enum import Enum

class TimePeriod(str, Enum):
    WEEK = "week"           # 最近一周
    MONTH = "month"         # 最近一个月
    QUARTER = "quarter"     # 最近一个季度
    CUSTOM = "custom"       # 自定义时间范围
```

### 8.2 API 接口设计

```python
# 1. 获取通话统计概览
GET /api/v1/portrait/call-stats
    ?period=week|month|quarter
    &user_id=xxx (可选)
    &task_id=xxx (可选)

# 返回示例:
{
    "total_calls": 10000,
    "success_calls": 3500,
    "effective_rate": 0.35,
    "avg_duration_seconds": 45.2,
    "max_duration_seconds": 320,
    "min_duration_seconds": 3,
    "avg_rounds": 4.5,
    "hangup_by_robot_rate": 0.42,
    "hangup_by_customer_rate": 0.58
}

# 2. 获取未接原因分布
GET /api/v1/portrait/unanswered-reasons
    ?period=week|month|quarter

# 返回示例:
{
    "total_unanswered": 6500,
    "distribution": [
        {"reason": "无应答", "count": 2000, "rate": 0.31},
        {"reason": "拒接", "count": 1800, "rate": 0.28},
        {"reason": "关机", "count": 1000, "rate": 0.15},
        ...
    ]
}

# 3. 获取情绪/风险分析
GET /api/v1/portrait/sentiment-analysis
    ?period=week|month|quarter

# 返回示例:
{
    "total_analyzed": 3500,
    "positive_rate": 0.45,
    "negative_rate": 0.25,
    "neutral_rate": 0.30,
    "complaint_risk_count": 120,
    "churn_risk_count": 350
}

# 4. 获取单次通话详情 (含ASR)
GET /api/v1/portrait/call-detail/{callid}

# 返回示例:
{
    "callid": "xxx",
    "callee": "138****1234",
    "duration_seconds": 65,
    "rounds": 5,
    "hangup_by": "customer",
    "intention": "B",
    "asr_dialogues": [
        {"seq": 1, "role": "robot", "content": "您好，我是..."},
        {"seq": 2, "role": "customer", "content": "什么事？"},
        ...
    ],
    "sentiment": "neutral",
    "risk_flags": []
}
```

---

## 九、技术实现方案

### 9.1 项目结构

```
data_anlysis/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── config.py               # 配置管理
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # Pydantic 模型
│   ├── services/
│   │   ├── __init__.py
│   │   ├── database.py         # 数据库连接
│   │   ├── table_resolver.py   # 动态表名解析
│   │   ├── call_stats.py       # 通话统计服务
│   │   ├── sentiment.py        # 情感分析服务
│   │   └── risk_detect.py      # 风险检测服务
│   └── routers/
│       ├── __init__.py
│       └── portrait.py         # 画像 API 路由
├── tests/
│   └── test_portrait.py
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml              # uv 项目配置
└── README.md
```

### 9.2 依赖包

```toml
[project]
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "sqlalchemy>=2.0.0",
    "aiomysql>=0.2.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "python-dateutil>=2.8.0",
]

[project.optional-dependencies]
nlp = [
    "transformers>=4.35.0",
    "torch>=2.1.0",
]
```

---

## 十、总结

| 维度 | 评估 |
|-----|------|
| **数据完整性** | ✅ 所有指标所需字段均存在 |
| **分表逻辑** | ✅ 已明确分表规则，可动态构建表名 |
| **关联查询** | ✅ 通过 `callid` 和 `task_id` 可关联 |
| **ASR 数据** | ✅ 详情表 `question` 字段包含识别文本 |
| **情感/风险分析** | ⚠️ 需额外实现 NLP 或关键词匹配 |
| **跨表查询性能** | ⚠️ 季度查询涉及3个分表，需优化 |

---

## 十一、下一步计划

1. **初始化 FastAPI 项目** - 使用 uv 创建项目结构
2. **实现数据库连接** - 支持动态表名和连接池
3. **开发核心 API** - 按周/月/季度统计接口
4. **集成情感分析** - 关键词匹配方案
5. **Docker 化部署** - 编写 Dockerfile 和 docker-compose
6. **性能优化** - 添加缓存、并发查询

---

*文档生成时间: 2024-12-03*

