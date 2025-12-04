# 数据画像可行性分析报告

## 1. 结论
经过对现有数据库模型 (`deploy-saas/app/Models`) 和需求文档 (`goal.xlsx`) 的分析，**所有请求的画像统计指标均可在现有条件下实现**。

## 2. 数据映射方案

以下是每个指标的具体计算口径和数据来源：

| 指标名称 | 数据来源表 | 字段/逻辑 | 说明 |
| :--- | :--- | :--- | :--- |
| **挂断方** | `autodialer_call_record_{date}` | `hangup_disposition` | `1`: 机器人挂断, `2`: 客户挂断 |
| **未接原因** | `autodialer_number_{task_id}` | `status` | 状态码对应关系见 `Number` 模型常量 (如 `STATUS_REJECT`, `STATUS_NO_REPLY` 等) |
| **有效通话率** | `autodialer_number_{task_id}` <br> `autodialer_call_record_{date}` | 计算公式 | `有效通话数` (CallRecord 中 `bill` > 0 或 `state`=Success) / `总拨打次数` (Number 表 `time` 字段) |
| **通话互动率** | `autodialer_call_record_detail_{date}` | 计算公式 | `有效交互次数` (Detail 表 `notify`='asrmessage_notify') / `通话总轮次` (Record 表 `rounds`) |
| **平均交互次数** | `autodialer_call_record_{date}` | `rounds` | 对查询周期内的 `rounds` 字段求平均值 |
| **平均通话时长** | `autodialer_call_record_{date}` | `bill` 或 `duration` | 对 `bill` (计费时长) 或 `duration` (总时长) 求平均值 |
| **最大通话时长** | `autodialer_call_record_{date}` | `bill` | `MAX(bill)` |
| **最小通话时长** | `autodialer_call_record_{date}` | `bill` | `MIN(bill)` (需排除 0 或设定阈值) |
| **用户态度情绪** | `autodialer_call_record_detail_{date}` | `question` | 需对 `question` 字段 (ASR 识别文本) 进行 NLP 情感分析，或使用 `score` 字段 (如果已集成评分) |
| **用户满意度** | `tags` & `taggables` | 关联查询 | 通过 `CallRecord` 的 `tags` 关联查询用户打的标签 (如 "满意", "一般" 等) |
| **用户不满意原因** | `tags` & `taggables` | 关联查询 | 同上，查询 "不满意" 相关的具体标签 |
| **投诉风险** | `autodialer_call_record_detail_{date}` | `question` | 检索 `question` 文本中是否包含敏感词 (如 "投诉", "举报" 等) |
| **流失风险** | `autodialer_call_record_detail_{date}` | `question` | 检索 `question` 文本中是否包含流失特征词 (如 "换套餐", "不用了" 等) |

## 3. 数据读取逻辑说明

### 3.1 动态表名处理
根据您的描述和代码分析，数据表存在分表逻辑，读取时需动态构建表名：

1.  **任务信息获取**:
    - 首先查询 `autodialer_task` 表。
    - 获取 `uuid` (即 `task_id`) 和 `create_datetime`。

2.  **通话记录表 (`autodialer_call_record_{suffix}`)**:
    - 后缀 `{suffix}` 基于任务创建时间 (`create_datetime`)。
    - 代码中 `CallRecord` 使用 `SubTableByDateModel`，通常格式为 `Ymd` (如 `20231027`) 或 `Ym`。需根据实际数据库中的表名确认日期格式 (建议检查数据库或参考 `SubTableByDateModel` 的具体实现配置)。
    - **查询逻辑**: 根据任务的 `create_datetime` 确定对应的记录表名，然后使用 `task_id` 进行筛选。

3.  **号码表 (`autodialer_number_{suffix}`)**:
    - 后缀 `{suffix}` 为 `task_id` (根据您的描述)。
    - **查询逻辑**: 直接拼接 `autodialer_number_` + `task_id` 读取该任务的号码数据。

### 3.2 关联查询
- **通话详情**: `autodialer_call_record_detail_{suffix}` 与记录表后缀逻辑一致。通过 `callid` 或 `record_id` 与主记录关联。
- **标签信息**: 使用 Laravel 的多态关联 (`taggables` 表)，`taggable_id` 为通话记录 ID，`taggable_type` 为 `App\Models\AutoDialer\CallRecord`。

## 4. 下一步建议
- **情感与风险分析**: 既然需要分析 "态度情绪" 和 "风险"，建议在后端服务中集成一个简单的 NLP 模块 (或关键词匹配库) 来处理 `question` 文本。
- **性能优化**: 跨分表查询 (如按季度统计) 可能涉及多张表，建议在应用层进行聚合，或使用 ClickHouse 等数仓方案 (如果数据量巨大)。但在当前 Python FastAPI 架构下，可以通过并发查询多个分表来汇总数据。
