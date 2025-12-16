# 画像系统数据架构文档

> 更新时间：2025-12-16

## 一、架构概览

```
┌─────────────────┐      ETL 同步       ┌─────────────────┐      API       ┌─────────────────┐
│   MySQL 源库    │ ──────────────────► │  PostgreSQL     │ ────────────► │    前端展示      │
│  (线上业务数据)  │                     │  (画像数据库)    │               │                 │
└─────────────────┘                     └─────────────────┘               └─────────────────┘
```

---

## 二、原始数据层（MySQL - 源系统）

数据库：`outbound_saas`

### 2.1 autodialer_task（任务/场景表）

| 字段 | 类型 | 说明 |
|------|------|------|
| uuid | char(36) | 任务ID（主键） |
| name | varchar(191) | 场景名称，如：台州-装机单竣工回访 |

**当前数据量**：16 条

**用途**：定义外呼任务/场景，是画像分析的分组维度

---

### 2.2 autodialer_call_record_2025_11（通话记录表 - 按月分表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | char(36) | 记录ID（主键） |
| task_id | char(36) | 关联任务ID → autodialer_task.uuid |
| customer_id | char(36) | **被呼客户ID** ★ 这是用户画像的主体 |
| callee | varchar(20) | 被呼手机号 |
| callid | char(36) | 通话唯一ID |
| calldate | datetime | 通话时间 |
| duration | int unsigned | 通话时长（毫秒） |
| bill | int unsigned | 计费时长（毫秒），>0 表示接通 |
| rounds | int unsigned | 对话轮次 |
| hangup_disposition | tinyint | 挂断方：1=机器人挂断, 2=用户挂断 |
| intention_results | tinyint | 意向结果 |

**当前数据量**：62,173 条

**关键关系**：
- `task_id` → `autodialer_task.uuid`（多对一）
- `id` → `autodialer_call_record_detail.record_id`（一对多）

---

### 2.3 autodialer_call_record_detail_2025_11（ASR 通话明细表 - 按月分表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | char(36) | 记录ID（主键） |
| record_id | char(36) | 关联通话记录ID → call_record.id |
| callid | char(36) | 通话唯一ID |
| sequence | int unsigned | 对话序号（轮次） |
| notify | varchar(191) | **事件类型** ★ 关键筛选条件 |
| question | text | **用户说的话**（ASR 识别结果） |
| answer_text | text | 命中的答案节点ID |
| answer_content | text | **机器人回复内容** |
| keyword | varchar(191) | 命中的关键词 |
| word_class | varchar(191) | 词类分类 |

**当前数据量**：423,694 条

**notify 字段分布**：

| notify 值 | 数量 | 含义 |
|-----------|------|------|
| asrmessage_notify | 164,983 | ✅ **真正的用户-机器人交互** |
| asrprogress_notify | 168,272 | 中间过程状态 |
| enter | 80,712 | 进入节点 |
| playback_result | 8,851 | 播放结果 |
| wait_result | 876 | 等待结果 |

**重要**：只有 `notify = 'asrmessage_notify'` 的记录才是有效的用户交互数据！

---

## 三、画像数据层（PostgreSQL - 画像系统）

数据库：`portrait`

### 3.1 period_registry（周期注册表）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | 主键 |
| period_type | varchar | 周期类型：week/month/quarter |
| period_key | varchar | 周期编号：如 2025-W48 |
| period_start | date | 周期开始日期 |
| period_end | date | 周期结束日期 |
| status | varchar | 状态：pending/computing/completed/failed |
| total_users | int | 该周期用户数 |
| total_records | int | 该周期记录数 |
| computed_at | timestamp | 计算完成时间 |

**当前数据量**：4 条（2025-W47 ~ 2025-W50）

**用途**：管理画像计算周期，避免重复计算

---

### 3.2 call_record_enriched（增强通话记录 - 明细层）

| 字段 | 类型 | 说明 | 数据来源 |
|------|------|------|----------|
| id | uuid | 主键 | 自动生成 |
| callid | varchar | 通话ID | MySQL call_record.callid |
| task_id | uuid | 任务ID | MySQL call_record.task_id |
| user_id | varchar | **客户ID** | MySQL call_record.customer_id |
| phone | varchar | 手机号 | MySQL call_record.callee |
| call_date | date | 通话日期 | MySQL call_record.calldate |
| bill | int | 计费时长 | MySQL call_record.bill |
| rounds | int | 对话轮次 | MySQL call_record.rounds |
| hangup_by | smallint | 挂断方 | MySQL call_record.hangup_disposition |
| call_status | varchar | 通话状态 | 根据 bill 计算 |
| --- | --- | --- | --- |
| sentiment | varchar | 情感标签 | ⚠️ **待计算** |
| sentiment_score | double | 情感分数 | ⚠️ **待计算** |
| complaint_risk | varchar | 投诉风险 | ⚠️ **待计算** |
| churn_risk | varchar | 流失风险 | ⚠️ **待计算** |

**当前数据量**：28,799 条

**用途**：存储清洗后的通话记录，作为画像计算的数据源

---

### 3.3 user_portrait_snapshot（用户画像快照 - 汇总层）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | 主键 |
| customer_id | varchar | **客户ID** ★ 画像主体 |
| task_id | uuid | 任务ID |
| phone | varchar | 手机号 |
| period_type | varchar | 周期类型 |
| period_key | varchar | 周期编号 |
| period_start | date | 周期开始 |
| period_end | date | 周期结束 |
| --- | --- | --- |
| total_calls | int | 总通话数 |
| connected_calls | int | 接通数 |
| connect_rate | double | 接通率 |
| total_duration | int | 总时长 |
| avg_duration | double | 平均时长 |
| avg_rounds | double | 平均轮次 |
| robot_hangup_count | int | 机器人挂断次数 |
| user_hangup_count | int | 用户挂断次数 |
| --- | --- | --- |
| positive_count | int | 正面情感次数 ⚠️ |
| neutral_count | int | 中性情感次数 ⚠️ |
| negative_count | int | 负面情感次数 ⚠️ |
| avg_sentiment_score | double | 平均情感分 ⚠️ |
| high_complaint_risk | int | 高投诉风险次数 ⚠️ |
| high_churn_risk | int | 高流失风险次数 ⚠️ |

**当前数据量**：11,230 条

**聚合维度**：`customer_id + task_id + period_key`

**用途**：按客户+场景+周期聚合的画像快照，供前端客户列表展示

---

### 3.4 task_portrait_summary（场景画像汇总 - 报表层）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | 主键 |
| task_id | uuid | 任务ID |
| task_name | varchar | 场景名称 |
| period_type | varchar | 周期类型 |
| period_key | varchar | 周期编号 |
| --- | --- | --- |
| total_customers | int | **总客户数** ★ 前端展示 |
| total_calls | int | 总通话数 |
| connected_calls | int | 接通数 |
| connect_rate | double | 接通率 |
| avg_duration | double | 平均时长 |
| --- | --- | --- |
| satisfied_count | int | 满意客户数 ⚠️ |
| satisfied_rate | double | 满意率 ⚠️ |
| high_complaint_customers | int | 高投诉风险客户数 ⚠️ |
| high_complaint_rate | double | 高投诉率 ⚠️ |
| high_churn_customers | int | 高流失风险客户数 ⚠️ |
| high_churn_rate | double | 高流失率 ⚠️ |

**当前数据量**：10 条

**聚合维度**：`task_id + period_key`

**用途**：按场景+周期聚合的汇总统计，供前端场景选择和统计卡片展示

---

## 四、数据流转关系

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              ETL 数据流                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   MySQL                              PostgreSQL                              │
│   ─────                              ──────────                              │
│                                                                              │
│   autodialer_task ──────────────────► task_portrait_summary.task_name        │
│         │              sync_task_names()                                     │
│         │                                    ▲                               │
│         ▼                                    │                               │
│   autodialer_call_record_2025_11            │                               │
│         │                                    │                               │
│         │ sync_call_records()               │ compute_task_summary()        │
│         │ (按天同步，最近30天)               │ (按 task_id+period 聚合)      │
│         ▼                                    │                               │
│   ─────────────────► call_record_enriched ───┼──► user_portrait_snapshot     │
│                            │                 │           │                   │
│                            │                 │           │                   │
│                            │                 └───────────┘                   │
│                            │  compute_snapshot()                             │
│                            │  (按 customer_id+task_id+period 聚合)           │
│                            │                                                 │
│   autodialer_call_record   │                                                 │
│   _detail_2025_11          │                                                 │
│         │                  │                                                 │
│         ▼                  ▼                                                 │
│   ─────────────────► 待实现: 情感分析/风险计算                                │
│   (ASR 文本分析)     填充 sentiment / complaint_risk / churn_risk            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 五、前端 API 数据使用

| API | 数据来源 | 说明 |
|-----|----------|------|
| `GET /task/periods` | period_registry | 获取可选周期列表 |
| `GET /task` | task_portrait_summary | 获取场景列表及客户数 |
| `GET /task/{id}/summary` | task_portrait_summary | 获取场景统计（饼图、卡片） |
| `GET /task/{id}/trend` | task_portrait_summary | 获取趋势数据（折线图） |
| `GET /task/{id}/customers` | user_portrait_snapshot | 获取客户明细列表 |

---

## 六、当前数据状态

| 层级 | 表名 | 数据量 | 状态 |
|------|------|--------|------|
| **MySQL 源数据** | autodialer_task | 16 | ✅ 完整 |
| | autodialer_call_record_2025_11 | 62,173 | ✅ 完整 |
| | autodialer_call_record_detail_2025_11 | 423,694 | ✅ 完整 |
| **PostgreSQL 画像** | period_registry | 4 | ✅ 周期记录 |
| | call_record_enriched | 28,799 | ✅ 已同步 |
| | user_portrait_snapshot | 11,230 | ✅ 已聚合 |
| | task_portrait_summary | 10 | ✅ 已汇总 |

---

## 七、待实现功能

| 功能 | 数据来源 | 目标字段 | 实现方式 |
|------|----------|----------|----------|
| **情感分析** | ASR `question` 文本 | sentiment, sentiment_score | 关键词匹配 / AI 模型 |
| **投诉风险** | ASR 关键词 + 挂断行为 | complaint_risk | 规则引擎 |
| **流失风险** | 未接通 + 多次呼叫 | churn_risk | 规则引擎 |
| **满意度标签** | 综合情感 + 风险 | satisfied_count 等 | 聚合计算 |

---

## 八、关键业务规则

### 8.1 ASR 交互识别

```sql
-- 只有 notify = 'asrmessage_notify' 的记录才是真正的用户交互
SELECT question, answer_content
FROM autodialer_call_record_detail_2025_11
WHERE notify = 'asrmessage_notify'
```

### 8.2 通话接通判断

```python
# bill > 0 表示通话接通
call_status = "connected" if bill > 0 else "not_connected"
```

### 8.3 画像聚合维度

```
用户画像快照：customer_id + task_id + period_key
场景画像汇总：task_id + period_key
```

---

## 附录：ER 关系图

```
┌─────────────────────┐
│   autodialer_task   │
│   (任务/场景)       │
│─────────────────────│
│ PK: uuid            │
│     name            │
└──────────┬──────────┘
           │ 1:N
           ▼
┌─────────────────────────────────┐
│ autodialer_call_record_2025_11  │
│ (通话记录)                      │
│─────────────────────────────────│
│ PK: id                          │
│ FK: task_id → task.uuid         │
│     customer_id  ★ 画像主体     │
│     callee (手机号)             │
│     callid                      │
│     calldate, bill, rounds...   │
└──────────┬──────────────────────┘
           │ 1:N
           ▼
┌──────────────────────────────────────┐
│ autodialer_call_record_detail_2025_11│
│ (ASR 明细)                           │
│──────────────────────────────────────│
│ PK: id                               │
│ FK: record_id → call_record.id       │
│     callid                           │
│     notify  ★ 'asrmessage_notify'    │
│     sequence                         │
│     question (用户说的话)            │
│     answer_content (机器人回复)      │
└──────────────────────────────────────┘
```
