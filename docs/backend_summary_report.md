# 客户画像系统后端总结报告

## 一、系统概述

### 1.1 项目背景

本系统旨在构建一个客户数据画像后端服务，基于智能外呼系统的通话记录数据，计算并存储客户画像指标，支持按场景(任务)维度和时间周期进行聚合统计。

### 1.2 技术架构

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| Web 框架 | FastAPI | 高性能异步 API 框架 |
| 数据库 | PostgreSQL | 画像数据存储 |
| 源数据库 | MySQL | 外呼系统业务数据（只读） |
| ORM | SQLAlchemy 2.0 | 异步数据库操作 |
| LLM | 通义千问/自定义网关 | 情感分析与风险识别 |
| 任务调度 | APScheduler | 定时数据同步与计算 |
| 包管理 | uv | Python 依赖管理 |
| 容器化 | Docker | 部署方案 |

---

## 二、数据模型设计

### 2.1 核心概念

- **画像主体**: `customer_id` (被呼叫的客户)
- **聚合维度**: `task_id` (场景/任务) + 时间周期
- **时间粒度**: 周 (week) / 月 (month) / 季度 (quarter)

### 2.2 数据表结构

#### 通话记录增强表 `call_record_enriched`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| callid | VARCHAR(64) | 通话ID（源系统） |
| customer_id | VARCHAR(64) | **客户ID（画像主体）** |
| task_id | UUID | 任务/场景ID |
| call_date | DATE | 通话日期 |
| duration | INTEGER | 通话时长(秒) |
| rounds | INTEGER | 交互轮次 |
| intention_level | VARCHAR(8) | 意向等级 (A/B/C/D/E/F) |
| hangup_by | VARCHAR(16) | 挂断方 |
| sentiment | VARCHAR(16) | 情绪 (positive/neutral/negative) |
| sentiment_score | FLOAT | 情绪得分 (0-1) |
| complaint_risk | VARCHAR(16) | 投诉风险 (high/medium/low) |
| churn_risk | VARCHAR(16) | 流失风险 (high/medium/low) |
| llm_analyzed_at | TIMESTAMP | LLM 分析时间 |

#### 客户画像快照表 `user_portrait_snapshot`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| customer_id | VARCHAR(64) | **客户ID** |
| task_id | UUID | **任务ID** |
| period_type | VARCHAR(16) | 周期类型 |
| period_key | VARCHAR(16) | 周期编号 (如 2025-W48) |
| period_start | DATE | 周期开始日期 |
| period_end | DATE | 周期结束日期 |
| total_calls | INTEGER | 总通话数 |
| connected_calls | INTEGER | 接通数 |
| connect_rate | FLOAT | 接通率 |
| avg_duration | FLOAT | 平均通话时长 |
| positive_count | INTEGER | 正面情绪数 |
| neutral_count | INTEGER | 中性情绪数 |
| negative_count | INTEGER | 负面情绪数 |
| high_complaint_risk | INTEGER | 高投诉风险数 |
| high_churn_risk | INTEGER | 高流失风险数 |

**唯一键**: `(customer_id, task_id, period_type, period_key)`

#### 场景汇总表 `task_portrait_summary`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| task_id | UUID | **任务ID** |
| period_type | VARCHAR(16) | 周期类型 |
| period_key | VARCHAR(16) | 周期编号 |
| total_customers | INTEGER | 总客户数 |
| total_calls | INTEGER | 总通话数 |
| satisfied_count | INTEGER | 满意客户数 |
| satisfied_rate | FLOAT | 满意率 |
| high_complaint_customers | INTEGER | 高投诉风险客户数 |
| high_complaint_rate | FLOAT | 高投诉风险率 |
| high_churn_customers | INTEGER | 高流失风险客户数 |
| high_churn_rate | FLOAT | 高流失风险率 |

**唯一键**: `(task_id, period_type, period_key)`

---

## 三、业务统计口径

### 3.1 基础指标

| 指标 | 计算公式 | 说明 |
|------|---------|------|
| 接通率 | `connected_calls / total_calls` | 成功接通的通话占比 |
| 平均通话时长 | `SUM(duration) / COUNT(*)` | 单位：秒 |
| 平均交互轮次 | `SUM(rounds) / COUNT(*)` | ASR 交互次数 |

### 3.2 满意度指标

| 指标 | 计算公式 | 数据来源 |
|------|---------|---------|
| 满意客户数 | `COUNT(sentiment='positive')` | LLM 分析结果 |
| 满意率 | `positive_count / total_sentiment_count` | 正面情绪占比 |
| 不满意客户数 | `COUNT(sentiment='negative')` | LLM 分析结果 |

### 3.3 风险指标

| 指标 | 计算公式 | 识别方式 |
|------|---------|---------|
| 高投诉风险客户数 | `COUNT(complaint_risk='high')` | LLM + 关键词匹配 |
| 高投诉风险率 | `high_complaint / total_customers` | 高风险客户占比 |
| 高流失风险客户数 | `COUNT(churn_risk='high')` | LLM + 关键词匹配 |
| 高流失风险率 | `high_churn / total_customers` | 高风险客户占比 |

### 3.4 风险关键词库

```python
# 投诉风险关键词
COMPLAINT_KEYWORDS = ["投诉", "举报", "12315", "消协", "工信部", "律师", "起诉"]

# 流失风险关键词
CHURN_KEYWORDS = ["不用了", "换套餐", "换运营商", "取消", "退订", "停用", "销户"]
```

### 3.5 意向等级分布

| 等级 | 含义 |
|------|------|
| A | 强意向 |
| B | 有意向 |
| C | 待跟进 |
| D | 无意向 |
| E | 拒绝 |
| F | 无效 |

---

## 四、服务模块

### 4.1 ETL 服务 (`etl_service.py`)

**职责**: 从 MySQL 源数据库同步通话记录到 PostgreSQL

**核心功能**:

- `sync_call_records(target_date)` - 同步指定日期的通话记录
- `get_asr_text_for_analysis(callid)` - 获取 ASR 对话文本
- `get_pending_records_for_analysis(limit)` - 获取待 LLM 分析的记录

**数据流**:

```
MySQL (autodialer_call_record_YYYY_MM)
    ↓ 提取 customer_id, task_id, callid 等
PostgreSQL (call_record_enriched)
```

### 4.2 LLM 服务 (`llm_service.py`)

**职责**: 情感分析与风险识别

**核心功能**:

- `analyze_sentiment(dialogue)` - 分析对话情感
- `analyze_pending_batch(limit)` - 批量分析待处理记录

**输出字段**:

```json
{
  "sentiment": "positive/neutral/negative",
  "sentiment_score": 0.0-1.0,
  "complaint_risk": "high/medium/low",
  "churn_risk": "high/medium/low"
}
```

**双环境支持**:

- 开发环境: 通义千问 API (DashScope)
- 生产环境: 自定义网关 API

### 4.3 画像计算服务 (`portrait_service.py`)

**职责**: 聚合计算客户画像快照

**核心功能**:

- `compute_snapshot(period_type, period_key)` - 计算客户画像快照
- `compute_task_summary(period_type, period_key)` - 计算场景汇总
- `compute_weekly_snapshot()` - 计算周快照
- `compute_monthly_snapshot()` - 计算月快照
- `compute_quarterly_snapshot()` - 计算季度快照

**聚合维度**: 按 `(customer_id, task_id, period_type, period_key)` 聚合

### 4.4 周期服务 (`period_service.py`)

**职责**: 时间周期管理

**核心功能**:

- `get_period_range(period_type, period_key)` - 获取周期时间范围
- `get_week_key(date)` - 获取周编号 (如 2025-W48)
- `get_current_period(period_type)` - 获取当前周期

---

## 五、定时任务

### 5.1 任务调度配置

| 任务 | 时间 | 功能 |
|------|------|------|
| 数据同步 | 02:00 | 同步昨日通话记录 |
| LLM 分析 | 02:30 | 分析待处理记录 |
| 周期快照 | 06:00 | 周/月/季度快照计算 |
| 场景汇总 | 06:30 | 任务级别汇总统计 |

### 5.2 启用配置

```env
SCHEDULER_ENABLED=true
SYNC_CRON_HOUR=2
SYNC_CRON_MINUTE=0
```

---

## 六、对外 API 接口

### 6.1 场景(任务)接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/task` | GET | 获取任务列表 |
| `/api/v1/task/{task_id}/summary` | GET | 获取任务汇总统计 |
| `/api/v1/task/{task_id}/trend` | GET | 获取任务指标趋势 |

#### GET /api/v1/task

获取任务列表，包含通话数和客户数统计。

**响应示例**:

```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "task_id": "eca85f1e-3558-40ec-8140-79f75f36eb57",
      "call_count": 637,
      "customer_count": 637,
      "first_call": "2025-11-25",
      "last_call": "2025-11-28"
    }
  ]
}
```

#### GET /api/v1/task/{task_id}/summary

获取指定任务在指定周期的汇总统计。

**参数**:

- `period_type`: week/month/quarter
- `period_key`: 周期编号 (如 2025-W48)

**响应示例**:

```json
{
  "code": 0,
  "data": {
    "task_id": "eca85f1e-3558-40ec-8140-79f75f36eb57",
    "total_customers": 637,
    "total_calls": 637,
    "connect_rate": 1.0,
    "avg_duration": 35.8,
    "satisfaction": {
      "satisfied": 0,
      "satisfied_rate": 0.0,
      "neutral": 0,
      "unsatisfied": 0
    },
    "risk": {
      "high_complaint": 0,
      "high_complaint_rate": 0.0,
      "high_churn": 0,
      "high_churn_rate": 0.0
    }
  }
}
```

#### GET /api/v1/task/{task_id}/trend

获取指定任务的指标趋势数据。

**参数**:

- `period_type`: week/month/quarter
- `metric`: connect_rate/satisfied_rate/high_complaint_rate/high_churn_rate/avg_duration
- `limit`: 返回周期数 (默认12)

**响应示例**:

```json
{
  "code": 0,
  "data": {
    "task_id": "eca85f1e-...",
    "metric": "connect_rate",
    "series": [
      {"period": "2025-W46", "value": 0.95},
      {"period": "2025-W47", "value": 0.98},
      {"period": "2025-W48", "value": 1.0}
    ]
  }
}
```

### 6.2 管理接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/admin/status` | GET | 系统状态 |
| `/api/v1/admin/sync` | POST | 手动触发数据同步 |
| `/api/v1/admin/analyze` | POST | 手动触发 LLM 分析 |
| `/api/v1/admin/compute` | POST | 手动触发画像计算 |
| `/api/v1/admin/compute-task-summary` | POST | 手动触发场景汇总 |
| `/api/v1/admin/periods/status` | GET | 周期计算状态 |

---

## 七、部署配置

### 7.1 环境变量

```env
# PostgreSQL (画像存储)
PORTRAIT_DB_HOST=localhost
PORTRAIT_DB_PORT=5432
PORTRAIT_DB_USER=portrait
PORTRAIT_DB_PASSWORD=portrait123
PORTRAIT_DB_NAME=portrait

# MySQL (源数据，只读)
SOURCE_DB_HOST=localhost
SOURCE_DB_PORT=3306
SOURCE_DB_USER=readonly
SOURCE_DB_PASSWORD=xxx
SOURCE_DB_NAME=deploy_saas

# LLM 配置
LLM_API_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=sk-xxx
LLM_MODEL=qwen-turbo

# 调度器
SCHEDULER_ENABLED=true
```

### 7.2 Docker 启动

```bash
docker-compose up -d portrait-postgres portrait-mysql
uv run uvicorn src.main:app --host 0.0.0.0 --port 8000
```

---

## 八、数据验证结果

| 指标 | 数值 |
|------|------|
| 增强记录数 | 1673 |
| 客户画像快照 | 1616 |
| 任务数 | 9 |
| 场景汇总 | 9 |

---

## 九、待优化项

1. **客户列表 API** - 待开发，用于前端明细列表展示
2. **Alembic 迁移** - 建立稳定的数据库迁移策略
3. **缓存层** - 高频查询结果缓存
4. **监控告警** - 数据同步和计算任务监控
