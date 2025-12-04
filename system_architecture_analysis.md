# 智能外呼系统工程架构分析

## 一、系统整体架构

系统采用 **Laravel 6.x + Vue.js** 技术栈，分为两个核心平台：

| 平台 | 代码目录 | 定位 |
|------|----------|------|
| **管理端 (deploy-manage)** | 后台运营管理平台 | 系统管理员/代理商使用 |
| **SaaS 租户端 (deploy-saas)** | 企业用户端 | 最终客户使用的核心业务平台 |

### 技术栈详情

- **后端框架**: Laravel 6.x (PHP >= 7.2)
- **前端框架**: Vue.js + iView / Element UI
- **数据库 & 存储**:
  - **MongoDB**: 存储海量通话记录、日志等高频数据
  - **Redis**: 缓存与队列驱动
  - **MySQL**: 核心业务关系数据
- **中间件 & 服务**:
  - **RabbitMQ**: 消息队列，处理异步任务
  - **Elasticsearch**: 全文检索，用于话术匹配、日志搜索
  - **VOS/FreeSWITCH**: 软交换系统集成，用于语音通话落地
- **第三方服务**:
  - **阿里云 OSS / 华为云 OBS**: 文件存储（录音、话术包）
  - **微信/企业微信**: 消息通知与集成
  - **LLM (大模型)**: 集成大语言模型用于语义理解和生成

---

## 二、核心模块详解

### 1. 🤖 AI 机器人模块 (最核心)

**代码位置**: `app/Http/Controllers/Member/Robot/`

**核心功能：**

| 功能 | 控制器 | 说明 |
|------|--------|------|
| 话术流程设计 | `RobotProcessController` | 可视化配置对话流程 |
| 意图识别 | `RobotIntentController` | 识别用户说话意图 |
| 知识库管理 | `RobotKnowledgeController` | 配置机器人问答知识 |
| 话术变量 | `RobotVariableController` | 动态变量替换 |
| 话术市场 | `Market/` | 话术模板共享与分发 |
| 话术训练 | `RobotTrainController` | AI 模型优化 |
| 话术对话测试 | `RobotDialogController` | 模拟对话测试 |
| 话术导出 | `RobotExportController` | 话术备份导出 |

---

### 2. 📞 智能外呼任务模块 (AutoDialer)

**代码位置**: `app/Http/Controllers/Member/AutoDialer/`

**核心功能：**

| 功能 | 文件 | 说明 |
|------|------|------|
| 任务管理 | `Task/Index.php` | 创建/编辑/删除外呼任务 |
| 号码管理 | `Number/` | 批量导入、清洗、去重 |
| 任务启动 | `Task/Start.php` | 启动外呼任务 |
| 任务停止 | `Task/Stop.php` | 停止外呼任务 |
| 任务设置 | `Task/Setting.php` | 最大并发数、呼叫间隔 |
| 通话历史 | `CallHistory.php` | 查看历史通话记录 |
| 禁拨时段 | `DisableTimeGroup.php` | 设置禁止拨打时间段 |
| 任务统计 | `Stats/` | 任务执行统计报表 |

**任务模型关键字段** (`app/Models/AutoDialer/Task.php`):
- `maximumcall` - 最大并发数
- `recycle_limit` - 重拨次数限制
- `caller_line_id` - 关联线路
- `bridge_group_id` - 转接组

---

### 3. 🎙️ 语音引擎服务 (SmartIvr)

**代码位置**: `app/Services/SmartIvr/`

**核心功能：**

#### ASR 语音识别
支持多引擎、多语种、多方言：

| 分类 | 支持内容 |
|------|----------|
| 引擎 | 阿里云、科大讯飞、百度、灵云 |
| 语种 | 普通话、英语、日语、韩语、越南语、泰语、印尼语等 |
| 方言 | 粤语、四川话、河南话、湖北话、广西话、东北话、上海话等20+种 |
| 场景 | 金融、地产、教育、企业服务、运营商、汽车等行业优化 |

#### TTS 语音合成
- 40+ 种音色配置
- 支持男声、女声
- 多语种合成（中文、英文、日语、韩语等）

#### 通话状态处理 (`Notify/`)
- `Enter` - 通话进入
- `Leave` - 通话结束
- `AsrmessageNotify` - ASR 识别结果
- `BridgeResult` - 转接结果
- `PlaybackResult` - 播放结果

---

### 4. 🧠 大模型模块 (LLM)

**代码位置**: `app/Http/Controllers/Member/Outbound/`

**核心功能：**

| 功能 | 控制器 | 说明 |
|------|--------|------|
| RAG 知识库 | `LlmKnowledgeController.php` | 文档向量化检索 |
| 知识库管理 | `LlmKnowledgeDatabaseController.php` | 知识库增删改查 |
| AI 话术生成 | `LlmManage.php` | 智能回复生成 |
| 缓存记忆 | `LLmCacheMemory.php` | 上下文对话管理 |
| Prompt 管理 | `LlmPromptManage.php` | 提示词模板配置 |
| MCP 插件 | `LlmMcpController.php` | 外部能力扩展 |
| 问答导入 | `LlmQuestionAndAnswerController.php` | 批量导入问答对 |
| 测试会话 | `LlmTestSession.php` | 大模型对话测试 |

---

### 5. 📊 通话记录与统计模块

**代码位置**: `app/Http/Controllers/Member/AutoDialer/Record/`

**核心功能：**

| 功能 | 文件 | 说明 |
|------|------|------|
| 通话详情 | `Get.php` | 获取通话记录详情 |
| 录音播放 | `PlayComplete.php` | 完整录音播放 |
| 意向标签 | `BatchTagController.php` | 批量标记客户意向 |
| 质检评论 | `CommentController.php` | 通话质量评估 |
| 点赞收藏 | `PraiseController.php` | 优秀录音收藏 |
| 数据处理 | `DealController.php` | 通话数据处理 |

**统计报表** (`Stats/`):
- 接通率统计
- 通话时长分布
- 意向等级分布 (A/B/C/D)
- 任务完成进度

---

### 6. 👥 CRM 客户管理模块

**代码位置**: `app/Http/Controllers/Member/CrmCustomer/`

**核心功能：**

| 功能 | 控制器 | 说明 |
|------|--------|------|
| 客户资料 | `Customer.php` | 基础信息管理 |
| 公海池 | `CustomerBackPoolController.php` | 未跟进客户池 |
| 客户分配 | `CustomerAllocationController.php` | 分配给销售 |
| 跟进记录 | `CustomerFollowRecordController.php` | 销售跟进日志 |
| 标签管理 | `CustomerTagController.php` | 客户分类标签 |
| 客户分组 | `CustomerGroupController.php` | 客户分组管理 |
| 合同管理 | `Contract/ContractController.php` | 商机合同 |
| 回款管理 | `Contract/ContractScheduleReceivableController.php` | 回款计划 |
| 客户导入 | `CustomerExcel.php` | 批量导入客户 |
| 客户统计 | `CustomerStatisticController.php` | 客户数据统计 |

---

### 7. 📱 线路与坐席管理

**代码位置**: 
- 管理端: `deploy-manage/app/Http/Controllers/CallerLine/`
- SaaS端: `deploy-saas/app/Http/Controllers/Member/Call/`

**核心功能：**

| 功能 | 说明 |
|------|------|
| 线路管理 | VOS 线路接入、网关配置 |
| 号码池 | 主叫号码管理、轮询策略 |
| 坐席管理 | 人工坐席注册、状态监控 |
| AXB 隐私号 | 号码隐藏保护 |
| 线路分配 | 线路分配给代理/租户 |
| 并发控制 | 线路并发数限制 |

---

### 8. 💰 财务计费模块

**代码位置**: 
- 管理端: `deploy-manage/app/Http/Controllers/Bill/`
- SaaS端: `deploy-saas/app/Http/Controllers/Member/Bill/`

**核心功能：**

| 功能 | 说明 |
|------|------|
| 账户充值 | 代理商/租户余额充值 |
| 消费扣费 | 按通话时长/次数计费 |
| 账单统计 | 消费明细与报表 |
| 透支额度 | 设置透支限额 |
| 余额预警 | 低余额提醒 |

---

## 三、核心业务流程

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 1. 话术配置  │ -> │ 2. 导入号码  │ -> │ 3. 创建任务  │
│  Robot模块   │    │  Number模块  │    │  Task模块   │
└─────────────┘    └─────────────┘    └─────────────┘
                                            │
                                            v
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 6. 结果处理  │ <- │ 5. AI对话   │ <- │ 4. 发起呼叫  │
│  意向标签    │    │ ASR->LLM->TTS│    │ (RabbitMQ)  │
│  Record模块  │    │ SmartIvr服务 │    │  Amqp/Jobs  │
└─────────────┘    └─────────────┘    └─────────────┘
        │
        v
┌─────────────┐
│ 7. 推送CRM  │
│  /转人工    │
│  CrmCustomer│
└─────────────┘
```

---

## 四、关键技术组件

| 组件 | 用途 | 代码位置 |
|------|------|----------|
| **RabbitMQ** | 任务调度队列 | `app/Jobs/Amqp/` |
| **MongoDB** | 海量通话记录存储 | `app/Models/AutoDialer/CallRecord.php` |
| **Redis** | 缓存/实时状态 | `app/Services/SmartIvr/Handles/Helper/CallCache.php` |
| **Elasticsearch** | 话术检索/日志搜索 | `app/ScoutElastic/` |
| **FreeSWITCH/VOS** | 软交换通话落地 | `app/Services/Esl/` |
| **OSS/OBS** | 录音文件存储 | `config/hwobs.php`, `config/oss.php` |

---

## 五、异步任务 (Jobs)

**代码位置**: `app/Jobs/`

### 主要任务分类

| 分类 | 目录 | 说明 |
|------|------|------|
| AMQP 消息处理 | `Amqp/` | RabbitMQ 消息消费 |
| 大模型处理 | `BigModelOutboundRecord/` | LLM 相关异步任务 |
| 账单结算 | `Bill/` | 计费扣款 |
| 通话记录 | `OutboundRecord/` | 通话记录处理 |
| 任务调度 | `Task/` | 外呼任务状态管理 |
| 统计计算 | `Stat/` | 数据统计汇总 |
| 挂断通知 | `HangupNotify/` | 通话结束回调 |
| CRM 同步 | `CrmCustomer/` | 客户数据同步 |
| 线索处理 | `Clue/` | 第三方线索导入 |

---

## 六、管理端核心功能 (deploy-manage)

### 路由定义: `routes/backend.php`

| 模块 | 路由前缀 | 功能 |
|------|----------|------|
| 代理商管理 | `agent` | 代理商开户、权限、余额 |
| 客户经理 | `admin` | 管理员账号管理 |
| 线路管理 | `line`, `new_line` | 线路接入与分配 |
| 网关管理 | `robot-cli` | RobotCli 网关配置 |
| 终端用户 | `endpoint/member` | 租户用户管理 |
| 统计报表 | `stat`, `new_stat` | 运营数据统计 |
| 财务管理 | `bill` | 充值、扣费、账单 |
| 系统配置 | `setting` | 全局参数配置 |

---

## 七、重点维护建议

### 1. 核心关注模块

| 优先级 | 模块 | 原因 |
|--------|------|------|
| ⭐⭐⭐ | `SmartIvr` 服务 | 通话实时处理逻辑最复杂 |
| ⭐⭐⭐ | `AutoDialer/Task` | 任务调度与并发控制 |
| ⭐⭐⭐ | `Robot` 模块 | AI 话术引擎 |
| ⭐⭐ | `LLM` 模块 | 大模型集成 |
| ⭐⭐ | `Jobs/Amqp` | 消息队列处理 |
| ⭐ | `CrmCustomer` | CRM 业务逻辑 |

### 2. 日志与监控

- **操作日志**: 系统使用 `spatie/laravel-activitylog`，关键操作有审计日志
- **日志位置**: `storage/logs/`
- **活动日志表**: `activity_log`

### 3. 依赖服务监控

| 服务 | 重要性 | 监控要点 |
|------|--------|----------|
| RabbitMQ | 极高 | 队列堆积、连接数 |
| Redis | 极高 | 内存使用、连接数 |
| MongoDB | 高 | 存储空间、查询性能 |
| Elasticsearch | 中 | 索引状态、搜索延迟 |
| FreeSWITCH/VOS | 极高 | 注册状态、并发数 |

### 4. 常见问题排查

1. **任务不执行**: 检查 RabbitMQ 连接和队列消费者
2. **通话异常**: 检查 FreeSWITCH 日志和 SmartIvr 事件处理
3. **识别不准**: 检查 ASR 配置和热词设置
4. **录音丢失**: 检查 OSS/OBS 连接和存储配置

---

## 八、配置文件说明

| 配置文件 | 用途 |
|----------|------|
| `config/smartivr.php` | SmartIvr 核心配置 (ASR/TTS) |
| `config/robot_processes.php` | 机器人流程服务配置 |
| `config/vos.php` | VOS 软交换配置 |
| `config/queue.php` | 队列配置 (RabbitMQ) |
| `config/database.php` | 数据库配置 |
| `config/oss.php` | 阿里云 OSS 配置 |
| `config/hwobs.php` | 华为云 OBS 配置 |

---

*文档生成时间: 2025-12-03*

