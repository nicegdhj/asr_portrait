# 用户数据画像系统 - 开发计划

> 项目代号：Portrait  
> 版本：v1.0  
> 创建日期：2024-12-04  
> 架构师：AI Assistant

---

## 一、项目概述

### 1.1 项目背景

基于现有智能外呼系统的通话数据，构建用户行为数据画像服务，为业务决策提供数据支撑。

### 1.2 项目目标

| 目标 | 描述 |
|------|------|
| 数据整合 | 整合通话记录、任务信息、号码数据等多源数据 |
| 画像计算 | 支持用户态度情绪、投诉风险、流失风险等 13+ 指标 |
| 周期统计 | 支持按自然周、自然月、自然季度维度统计展示 |
| 可视化支持 | 提供 RESTful API 支持前端柱状图等统计信息展示 |

### 1.3 技术栈

| 组件 | 技术选型 | 说明 |
|------|----------|------|
| 语言 | Python 3.11+ | 主开发语言 |
| Web 框架 | FastAPI | 高性能异步 API 框架 |
| 包管理 | uv | 现代化 Python 包管理器 |
| ORM | SQLAlchemy 2.0 | 异步数据库操作 |
| 任务调度 | APScheduler | 定时任务调度 |
| 大模型 | OpenAI API / 通义千问 | 情感分析、风险识别 |
| 容器化 | Docker | 部署方案 |
| 数据库 | MySQL (读取源数据) + PostgreSQL (存储画像) | 数据存储 |

---

## 二、系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户数据画像系统                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │   前端应用       │────▶│   FastAPI       │────▶│   PostgreSQL    │       │
│  │   (Dashboard)   │◀────│   (API Server)  │◀────│   (画像存储)     │       │
│  └─────────────────┘     └─────────────────┘     └─────────────────┘       │
│                                   │                                         │
│                                   │ 定时任务                                 │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         数据处理层                                    │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │ 数据抽取     │──▶│ LLM 增强     │──▶│ 画像聚合     │               │   │
│  │  │ (ETL)        │  │ (情感/风险)  │  │ (Snapshot)   │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                   │                                         │
│                                   ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         数据源层                                      │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │   │
│  │  │ MySQL        │  │ MongoDB      │  │ 大模型 API    │               │   │
│  │  │ (外呼系统DB) │  │ (通话详情)   │  │ (通义/GPT)   │               │   │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块

| 模块 | 职责 | 关键组件 |
|------|------|----------|
| API 服务层 | 对外提供 RESTful 接口 | FastAPI, Pydantic |
| 数据抽取层 | 从源系统读取通话记录 | SQLAlchemy, 动态表名处理 |
| LLM 增强层 | 大模型分析情感、风险 | OpenAI SDK, 异步批处理 |
| 画像聚合层 | 按周期汇总计算画像指标 | Pandas, NumPy |
| 任务调度层 | 定时执行预计算任务 | APScheduler |
| 存储层 | 画像数据持久化 | PostgreSQL, Redis (缓存) |

---

## 三、数据模型设计

### 3.1 源数据表 (只读)

来自智能外呼系统 MySQL 数据库：

| 表名 | 分表规则 | 关键字段 |
|------|----------|----------|
| `autodialer_task` | 无分表 | id, create_datetime, status |
| `autodialer_call_record_{YYYY_MM}` | 按任务创建月份 | callid, task_id, user_id, duration, bill, level_name, hangup_disposition |
| `autodialer_call_record_detail_{YYYY_MM}` | 按任务创建月份 | callid, text (ASR文本) |
| `autodialer_number_{task_id}` | 按任务ID | phone, call_count, status |

### 3.2 画像数据表 (读写)

存储于 PostgreSQL：

#### 3.2.1 通话记录增强表 `call_record_enriched`

```sql
CREATE TABLE call_record_enriched (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    callid          VARCHAR(64) NOT NULL UNIQUE,          -- 原始通话ID
    task_id         UUID NOT NULL,                         -- 任务ID
    user_id         UUID NOT NULL,                         -- 用户ID
    call_date       DATE NOT NULL,                         -- 通话日期
    
    -- 原始指标
    duration        INTEGER DEFAULT 0,                     -- 通话时长(ms)
    bill            INTEGER DEFAULT 0,                     -- 计费时长(ms)
    rounds          INTEGER DEFAULT 0,                     -- 交互轮次
    level_name      VARCHAR(32),                           -- 意向等级
    hangup_by       SMALLINT,                              -- 挂断方 1=机器人 2=客户
    call_status     VARCHAR(32),                           -- 通话状态
    
    -- LLM 增强指标
    sentiment       VARCHAR(16),                           -- 情绪: positive/neutral/negative
    sentiment_score FLOAT,                                 -- 情绪得分 0~1
    complaint_risk  VARCHAR(16),                           -- 投诉风险: low/medium/high
    churn_risk      VARCHAR(16),                           -- 流失风险: low/medium/high
    llm_analyzed_at TIMESTAMP,                             -- LLM 分析时间
    
    -- 元数据
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_user_date (user_id, call_date),
    INDEX idx_task_id (task_id),
    INDEX idx_call_date (call_date)
);
```

#### 3.2.2 用户画像快照表 `user_portrait_snapshot`

```sql
CREATE TABLE user_portrait_snapshot (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL,                      -- 用户ID
    period_type         VARCHAR(16) NOT NULL,               -- week/month/quarter
    period_key          VARCHAR(16) NOT NULL,               -- 2024-W49 / 2024-11 / 2024-Q4
    period_start        DATE NOT NULL,                      -- 周期开始日期
    period_end          DATE NOT NULL,                      -- 周期结束日期
    
    -- 通话统计指标
    total_calls         INTEGER DEFAULT 0,                  -- 总通话次数
    connected_calls     INTEGER DEFAULT 0,                  -- 接通次数
    connect_rate        FLOAT DEFAULT 0,                    -- 接通率
    total_duration      INTEGER DEFAULT 0,                  -- 总通话时长(秒)
    avg_duration        FLOAT DEFAULT 0,                    -- 平均通话时长(秒)
    total_rounds        INTEGER DEFAULT 0,                  -- 总交互轮次
    avg_rounds          FLOAT DEFAULT 0,                    -- 平均交互轮次
    
    -- 意向等级分布
    level_a_count       INTEGER DEFAULT 0,                  -- A级意向数
    level_b_count       INTEGER DEFAULT 0,                  -- B级意向数
    level_c_count       INTEGER DEFAULT 0,                  -- C级意向数
    level_d_count       INTEGER DEFAULT 0,                  -- D级意向数
    level_e_count       INTEGER DEFAULT 0,                  -- E级意向数
    level_f_count       INTEGER DEFAULT 0,                  -- F级意向数
    
    -- 挂断分布
    robot_hangup_count  INTEGER DEFAULT 0,                  -- 机器人挂断次数
    user_hangup_count   INTEGER DEFAULT 0,                  -- 客户挂断次数
    
    -- 未接通原因分布 (JSON)
    fail_reason_dist    JSONB DEFAULT '{}',                 -- {"busy": 10, "no_answer": 5, ...}
    
    -- LLM 分析指标
    positive_count      INTEGER DEFAULT 0,                  -- 积极情绪次数
    neutral_count       INTEGER DEFAULT 0,                  -- 中性情绪次数
    negative_count      INTEGER DEFAULT 0,                  -- 消极情绪次数
    avg_sentiment_score FLOAT DEFAULT 0,                    -- 平均情绪得分
    
    high_complaint_risk INTEGER DEFAULT 0,                  -- 高投诉风险次数
    medium_complaint_risk INTEGER DEFAULT 0,                -- 中投诉风险次数
    low_complaint_risk  INTEGER DEFAULT 0,                  -- 低投诉风险次数
    
    high_churn_risk     INTEGER DEFAULT 0,                  -- 高流失风险次数
    medium_churn_risk   INTEGER DEFAULT 0,                  -- 中流失风险次数
    low_churn_risk      INTEGER DEFAULT 0,                  -- 低流失风险次数
    
    -- 元数据
    computed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE (user_id, period_type, period_key),
    INDEX idx_period (period_type, period_key),
    INDEX idx_user_period (user_id, period_type)
);
```

#### 3.2.3 周期管理表 `period_registry`

```sql
CREATE TABLE period_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    period_type     VARCHAR(16) NOT NULL,               -- week/month/quarter
    period_key      VARCHAR(16) NOT NULL,               -- 2024-W49 / 2024-11 / 2024-Q4
    period_start    DATE NOT NULL,                      -- 开始日期
    period_end      DATE NOT NULL,                      -- 结束日期
    status          VARCHAR(16) DEFAULT 'pending',      -- pending/computing/completed
    computed_at     TIMESTAMP,                          -- 计算完成时间
    
    UNIQUE (period_type, period_key)
);
```

---

## 四、API 接口设计

### 4.1 接口清单

| 接口 | 方法 | 路径 | 描述 |
|------|------|------|------|
| 获取可选周期列表 | GET | `/api/v1/periods` | 返回可查询的周/月/季度列表 |
| 获取用户画像 | GET | `/api/v1/portrait/{user_id}` | 查询单用户画像 |
| 获取画像汇总 | GET | `/api/v1/portrait/summary` | 全量用户画像汇总统计 |
| 获取趋势数据 | GET | `/api/v1/portrait/trend` | 多周期趋势数据(柱状图) |
| 手动触发计算 | POST | `/api/v1/admin/compute` | 手动触发画像计算 |
| 健康检查 | GET | `/health` | 服务健康检查 |

### 4.2 接口详细设计

#### 4.2.1 获取可选周期列表

```
GET /api/v1/periods?type=week&limit=12
```

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "type": "week",
    "periods": [
      {"key": "2024-W49", "label": "2024年第49周", "start": "2024-12-02", "end": "2024-12-08", "status": "completed"},
      {"key": "2024-W48", "label": "2024年第48周", "start": "2024-11-25", "end": "2024-12-01", "status": "completed"},
      {"key": "2024-W47", "label": "2024年第47周", "start": "2024-11-18", "end": "2024-11-24", "status": "completed"}
    ]
  }
}
```

#### 4.2.2 获取用户画像

```
GET /api/v1/portrait/{user_id}?period_type=week&period_key=2024-W49
```

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "user_id": "uuid",
    "period": {
      "type": "week",
      "key": "2024-W49",
      "start": "2024-12-02",
      "end": "2024-12-08"
    },
    "call_stats": {
      "total_calls": 156,
      "connected_calls": 98,
      "connect_rate": 0.628,
      "total_duration": 14520,
      "avg_duration": 148.2,
      "total_rounds": 342,
      "avg_rounds": 3.49
    },
    "intention_dist": {
      "A": 12,
      "B": 28,
      "C": 35,
      "D": 15,
      "E": 5,
      "F": 3
    },
    "hangup_dist": {
      "robot": 45,
      "user": 53
    },
    "fail_reason_dist": {
      "busy": 18,
      "no_answer": 22,
      "power_off": 8,
      "invalid_number": 10
    },
    "sentiment_analysis": {
      "positive": 42,
      "neutral": 38,
      "negative": 18,
      "avg_score": 0.62
    },
    "risk_analysis": {
      "complaint_risk": {"high": 3, "medium": 12, "low": 83},
      "churn_risk": {"high": 5, "medium": 18, "low": 75}
    }
  }
}
```

#### 4.2.3 获取趋势数据

```
GET /api/v1/portrait/trend?period_type=week&limit=12&metric=connect_rate
```

**响应示例：**

```json
{
  "code": 0,
  "data": {
    "metric": "connect_rate",
    "period_type": "week",
    "series": [
      {"period_key": "2024-W38", "value": 0.58, "label": "第38周"},
      {"period_key": "2024-W39", "value": 0.61, "label": "第39周"},
      {"period_key": "2024-W40", "value": 0.59, "label": "第40周"},
      {"period_key": "2024-W41", "value": 0.63, "label": "第41周"}
    ]
  }
}
```

---

## 五、定时任务设计

### 5.1 任务调度方案

采用 **T+1 预计算** 策略，确保数据完整性：

```
┌───────────────────────────────────────────────────────────────┐
│                     定时任务调度流程                           │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  每日 02:00 AM                                                │
│  ┌─────────────┐                                              │
│  │ 1. 抽取新增 │ ─── 从源库读取昨日新增通话记录                │
│  │    通话记录  │                                              │
│  └──────┬──────┘                                              │
│         │                                                     │
│         ▼                                                     │
│  ┌─────────────┐                                              │
│  │ 2. LLM 分析 │ ─── 调用大模型分析情感、风险 (异步批量)       │
│  │    (批量)   │                                              │
│  └──────┬──────┘                                              │
│         │                                                     │
│         ▼                                                     │
│  ┌─────────────┐                                              │
│  │ 3. 写入增强 │ ─── 存入 call_record_enriched 表              │
│  │    通话记录  │                                              │
│  └──────┬──────┘                                              │
│         │                                                     │
│         ▼                                                     │
│  ┌─────────────┐                                              │
│  │ 4. 检查周期 │ ─── 判断是否需要生成周/月/季度快照             │
│  │    完成状态  │                                              │
│  └──────┬──────┘                                              │
│         │                                                     │
│         ▼ (如果周期完成)                                       │
│  ┌─────────────┐                                              │
│  │ 5. 聚合计算 │ ─── 汇总该周期所有数据，生成画像快照           │
│  │    画像快照  │                                              │
│  └─────────────┘                                              │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### 5.2 任务列表

| 任务名 | 执行时间 | 描述 | 超时时间 |
|--------|----------|------|----------|
| `sync_call_records` | 每日 02:00 | 同步昨日通话记录到增强表 | 2h |
| `llm_analyze_batch` | 每日 02:30 | 批量调用 LLM 分析情感/风险 | 4h |
| `check_period_complete` | 每日 06:00 | 检查并触发周期快照计算 | 30min |
| `compute_week_snapshot` | 每周一 06:30 | 计算上周画像快照 | 1h |
| `compute_month_snapshot` | 每月1日 07:00 | 计算上月画像快照 | 2h |
| `compute_quarter_snapshot` | 每季度首日 08:00 | 计算上季度画像快照 | 4h |

### 5.3 LLM 调用策略

```python
# 批量处理策略
LLM_CONFIG = {
    "batch_size": 50,              # 每批处理50条
    "max_concurrent": 5,           # 最大并发5个请求
    "retry_times": 3,              # 失败重试3次
    "timeout": 30,                 # 单次请求超时30秒
    "rate_limit": 60,              # 每分钟最多60次调用
}

# Prompt 模板
SENTIMENT_PROMPT = """
分析以下通话内容，返回JSON格式结果：
通话内容: {asr_text}

返回格式:
{
    "sentiment": "positive/neutral/negative",
    "sentiment_score": 0.0-1.0,
    "complaint_risk": "low/medium/high",
    "churn_risk": "low/medium/high",
    "reason": "简要分析原因"
}
"""
```

---

## 六、项目目录结构

```
potrait/
├── src/
│   ├── api/                          # API 接口层
│   │   ├── __init__.py
│   │   ├── deps.py                   # 依赖注入
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── periods.py            # 周期接口
│   │   │   ├── portrait.py           # 画像接口
│   │   │   └── admin.py              # 管理接口
│   │   └── router.py                 # 路由汇总
│   │
│   ├── core/                         # 核心配置
│   │   ├── __init__.py
│   │   ├── config.py                 # 配置管理
│   │   ├── database.py               # 数据库连接
│   │   └── security.py               # 安全配置
│   │
│   ├── models/                       # 数据模型
│   │   ├── __init__.py
│   │   ├── source/                   # 源数据模型 (只读)
│   │   │   ├── call_record.py
│   │   │   ├── call_record_detail.py
│   │   │   └── task.py
│   │   └── portrait/                 # 画像数据模型
│   │       ├── call_enriched.py
│   │       ├── snapshot.py
│   │       └── period.py
│   │
│   ├── services/                     # 业务服务层
│   │   ├── __init__.py
│   │   ├── etl_service.py            # 数据抽取服务
│   │   ├── llm_service.py            # LLM 分析服务
│   │   ├── portrait_service.py       # 画像计算服务
│   │   └── period_service.py         # 周期管理服务
│   │
│   ├── tasks/                        # 定时任务
│   │   ├── __init__.py
│   │   ├── scheduler.py              # 调度器
│   │   ├── sync_records.py           # 同步通话记录
│   │   ├── llm_analyze.py            # LLM 分析任务
│   │   └── compute_snapshot.py       # 快照计算任务
│   │
│   ├── schemas/                      # Pydantic 模型
│   │   ├── __init__.py
│   │   ├── period.py
│   │   ├── portrait.py
│   │   └── response.py
│   │
│   ├── utils/                        # 工具函数
│   │   ├── __init__.py
│   │   ├── date_utils.py             # 日期处理
│   │   ├── table_utils.py            # 动态表名处理
│   │   └── llm_utils.py              # LLM 调用工具
│   │
│   └── main.py                       # 应用入口
│
├── tests/                            # 测试
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_api/
│   ├── test_services/
│   └── test_tasks/
│
├── migrations/                       # 数据库迁移
│   └── versions/
│
├── docker/                           # Docker 配置
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .env.example
│
├── scripts/                          # 脚本
│   ├── init_db.py                    # 初始化数据库
│   └── manual_compute.py             # 手动计算脚本
│
├── pyproject.toml                    # uv 项目配置
├── uv.lock                           # 依赖锁定
├── README.md                         # 项目说明
├── .env.example                      # 环境变量示例
└── .gitignore
```

---

## 七、开发阶段规划

### Phase 1: 基础框架搭建 (Week 1)

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 1.1 项目初始化 | 使用 uv 创建项目，配置依赖 | `pyproject.toml` |
| 1.2 数据库设计 | 创建 PostgreSQL 表结构 | 迁移脚本 |
| 1.3 源库连接 | 实现智能外呼 MySQL 只读连接 | `database.py` |
| 1.4 动态表名处理 | 实现分表路由逻辑 | `table_utils.py` |
| 1.5 基础 API | 健康检查、周期列表接口 | API 可访问 |

### Phase 2: 数据抽取层 (Week 2)

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 2.1 ETL 服务 | 实现通话记录同步逻辑 | `etl_service.py` |
| 2.2 任务调度 | 配置 APScheduler | `scheduler.py` |
| 2.3 增量同步 | 实现 T+1 增量抽取 | 定时任务可运行 |
| 2.4 数据校验 | 源数据与目标数据一致性检查 | 测试用例 |

### Phase 3: LLM 分析层 (Week 3)

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 3.1 LLM 服务 | 封装大模型 API 调用 | `llm_service.py` |
| 3.2 批量处理 | 实现异步批量分析 | 批量任务 |
| 3.3 结果存储 | 分析结果写入增强表 | 数据持久化 |
| 3.4 错误处理 | 重试机制、降级策略 | 异常处理完善 |

### Phase 4: 画像聚合层 (Week 4)

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 4.1 周期管理 | 周/月/季度周期识别 | `period_service.py` |
| 4.2 快照计算 | 按周期聚合画像指标 | `portrait_service.py` |
| 4.3 快照任务 | 定时生成快照 | 快照任务可运行 |
| 4.4 画像 API | 用户画像查询接口 | API 完整 |

### Phase 5: 可视化支持 (Week 5)

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 5.1 趋势接口 | 多周期趋势数据接口 | 柱状图数据 |
| 5.2 汇总接口 | 全量统计汇总接口 | 大盘数据 |
| 5.3 缓存优化 | Redis 缓存热点数据 | 性能提升 |
| 5.4 接口文档 | OpenAPI 文档完善 | Swagger UI |

### Phase 6: 容器化部署 (Week 6)

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 6.1 Dockerfile | 编写生产级 Dockerfile | 镜像构建 |
| 6.2 Compose | 编写 docker-compose | 本地部署 |
| 6.3 环境配置 | 生产环境变量配置 | `.env.production` |
| 6.4 部署测试 | 远端机房部署验证 | 服务上线 |

---

## 八、里程碑

| 里程碑 | 日期 | 交付物 | 验收标准 |
|--------|------|--------|----------|
| M1: 框架就绪 | Week 1 | 基础框架 + 数据库 | API 可访问，数据库连接正常 |
| M2: 数据同步 | Week 2 | ETL 流程 | 通话记录可同步，定时任务运行 |
| M3: LLM 集成 | Week 3 | 情感/风险分析 | 分析结果正确存储 |
| M4: 画像计算 | Week 4 | 快照生成 | 周/月/季度画像可查询 |
| M5: API 完整 | Week 5 | 全部接口 | 所有接口通过测试 |
| M6: 生产部署 | Week 6 | Docker 部署 | 远端服务稳定运行 |

---

## 九、技术风险与对策

| 风险 | 级别 | 影响 | 对策 |
|------|------|------|------|
| LLM API 调用成本高 | 高 | 预算超支 | 1. 批量调用优化 2. 结果缓存 3. 关键词预过滤 |
| LLM 响应延迟 | 中 | 任务超时 | 1. 异步处理 2. 超时重试 3. 降级为规则引擎 |
| 源数据分表复杂 | 中 | 查询困难 | 1. 动态表名路由 2. 跨月查询聚合 |
| 数据量大 | 中 | 计算耗时 | 1. 增量计算 2. 分批处理 3. 索引优化 |
| 数据库连接数限制 | 低 | 连接池耗尽 | 1. 连接池配置 2. 读写分离 |

---

## 十、依赖包列表

```toml
# pyproject.toml

[project]
name = "portrait"
version = "1.0.0"
description = "用户数据画像服务"
requires-python = ">=3.11"

dependencies = [
    # Web 框架
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    
    # 数据库
    "sqlalchemy[asyncio]>=2.0.23",
    "asyncpg>=0.29.0",           # PostgreSQL 异步驱动
    "aiomysql>=0.2.0",           # MySQL 异步驱动
    "redis>=5.0.0",              # Redis 客户端
    
    # 任务调度
    "apscheduler>=3.10.0",
    
    # 数据处理
    "pandas>=2.1.0",
    "numpy>=1.26.0",
    
    # LLM
    "openai>=1.3.0",
    "httpx>=0.25.0",
    
    # 工具
    "python-dotenv>=1.0.0",
    "loguru>=0.7.0",
    "tenacity>=8.2.0",           # 重试库
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "httpx>=0.25.0",
    "ruff>=0.1.0",
]
```

---

## 十一、环境配置

```bash
# .env.example

# 应用配置
APP_NAME=portrait
APP_ENV=development
DEBUG=true
LOG_LEVEL=INFO

# API 配置
API_HOST=0.0.0.0
API_PORT=8000
API_PREFIX=/api/v1

# PostgreSQL (画像存储)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=portrait
POSTGRES_PASSWORD=your_password
POSTGRES_DB=portrait

# MySQL (源数据 - 只读)
MYSQL_HOST=source_db_host
MYSQL_PORT=3306
MYSQL_USER=readonly_user
MYSQL_PASSWORD=your_password
MYSQL_DB=outbound_saas

# MongoDB (通话详情 - 只读)
MONGO_URI=mongodb://localhost:27017
MONGO_DB=outbound_saas

# Redis (缓存)
REDIS_URL=redis://localhost:6379/0

# LLM 配置
LLM_PROVIDER=openai  # openai / qwen
LLM_API_KEY=your_api_key
LLM_MODEL=gpt-4o-mini
LLM_BATCH_SIZE=50
LLM_MAX_CONCURRENT=5

# 定时任务
SCHEDULER_ENABLED=true
SCHEDULER_TIMEZONE=Asia/Shanghai
```

---

## 十二、Docker 部署配置

### 12.1 Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装 uv
RUN pip install uv

# 复制依赖文件
COPY pyproject.toml uv.lock ./

# 安装依赖
RUN uv sync --frozen --no-dev

# 复制源代码
COPY src/ ./src/
COPY migrations/ ./migrations/

# 环境变量
ENV PYTHONPATH=/app/src
ENV APP_ENV=production

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 12.2 docker-compose.yml

```yaml
# docker-compose.yml
version: '3.8'

services:
  portrait-api:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: portrait-api
    ports:
      - "8000:8000"
    env_file:
      - .env.production
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    networks:
      - portrait-network

  portrait-scheduler:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: portrait-scheduler
    command: ["uv", "run", "python", "-m", "src.tasks.scheduler"]
    env_file:
      - .env.production
    depends_on:
      - postgres
      - redis
    restart: unless-stopped
    networks:
      - portrait-network

  postgres:
    image: postgres:15-alpine
    container_name: portrait-postgres
    environment:
      POSTGRES_USER: portrait
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: portrait
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    networks:
      - portrait-network

  redis:
    image: redis:7-alpine
    container_name: portrait-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    networks:
      - portrait-network

volumes:
  postgres_data:
  redis_data:

networks:
  portrait-network:
    driver: bridge
```

---

## 十三、下一步行动

1. **确认需求细节**：确认 goal.xlsx 中的具体指标定义
2. **确定 LLM 服务商**：选择通义千问/OpenAI/其他
3. **获取数据库连接信息**：源数据库连接配置
4. **开始 Phase 1**：项目初始化和框架搭建
5. **建立代码仓库**：Git 版本管理

---

*文档版本: v1.0*  
*最后更新: 2024-12-04*

