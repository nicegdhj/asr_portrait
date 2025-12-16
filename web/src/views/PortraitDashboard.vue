<template>
  <div class="portrait-dashboard">
    <!-- 页面头部 -->
    <header class="page-header">
      <h1 class="page-title">人群画像统计与分析</h1>
    </header>

    <!-- 筛选条 -->
    <div class="filter-bar">
      <div class="filter-item">
        <el-icon><Filter /></el-icon>
        <span class="filter-label">选择场景</span>
        <el-select
          v-model="selectedTaskId"
          placeholder="选择场景"
          style="width: 240px"
          @change="handleTaskChange"
          :loading="loading"
        >
          <el-option
            v-for="task in tasks"
            :key="task.task_id"
            :label="getTaskLabel(task)"
            :value="task.task_id"
          />
        </el-select>
      </div>

      <div class="filter-item">
        <span class="filter-label">选择周:</span>
        <el-select
          v-model="selectedPeriod"
          placeholder="选择周"
          style="width: 200px"
          @change="handlePeriodChange"
        >
          <el-option
            v-for="period in availablePeriods"
            :key="period"
            :label="getPeriodLabel(period)"
            :value="period"
          />
        </el-select>
      </div>

      <div class="filter-item" style="margin-left: auto;">
        <el-button :icon="Refresh" @click="refreshData" :loading="loading">
          刷新
        </el-button>
      </div>
    </div>

    <!-- 主内容区 -->
    <main class="main-content" v-loading="loading">
      <!-- 统计概览卡片 -->
      <div class="overview-cards">
        <div class="overview-card">
          <div class="overview-icon" style="background: var(--primary-bg);">
            <el-icon :size="24" color="var(--primary-color)"><User /></el-icon>
          </div>
          <div class="overview-info">
            <span class="overview-value">{{ summary?.total_customers || 0 }}</span>
            <span class="overview-label">总客户数</span>
          </div>
        </div>
        <div class="overview-card">
          <div class="overview-icon" style="background: #E6FFFB;">
            <el-icon :size="24" color="#13C2C2"><Phone /></el-icon>
          </div>
          <div class="overview-info">
            <span class="overview-value">{{ summary?.total_calls || 0 }}</span>
            <span class="overview-label">总通话数</span>
          </div>
        </div>
        <div class="overview-card">
          <div class="overview-icon" style="background: #FFF7E6;">
            <el-icon :size="24" color="var(--warning-color)"><Timer /></el-icon>
          </div>
          <div class="overview-info">
            <span class="overview-value">{{ formatDurationShort(summary?.avg_duration) }}</span>
            <span class="overview-label">平均时长</span>
          </div>
        </div>
      </div>

      <!-- 统计卡片区 - 4个维度 -->
      <div class="stats-grid-4">
        <!-- 满意度分布 -->
        <div class="card mini-chart-card">
          <h3 class="card-title">满意度分布</h3>
          <div class="mini-chart-container" ref="satisfactionChartRef"></div>
        </div>

        <!-- 风险分布 -->
        <div class="card mini-chart-card">
          <h3 class="card-title">风险分布</h3>
          <div class="mini-chart-container" ref="riskChartRef"></div>
        </div>

        <!-- 情感分布 -->
        <div class="card mini-chart-card">
          <h3 class="card-title">情感分布</h3>
          <div class="mini-chart-container" ref="emotionChartRef"></div>
        </div>

        <!-- 沟通意愿分布 -->
        <div class="card mini-chart-card">
          <h3 class="card-title">沟通意愿分布</h3>
          <div class="mini-chart-container" ref="willingnessChartRef"></div>
        </div>
      </div>

      <!-- 画像趋势变化 -->
      <div class="stats-grid">
        <div class="card" style="grid-column: span 2;">
          <div class="card-header-with-action">
            <h3 class="card-title">画像趋势变化（4个维度）</h3>
            <el-select
              v-model="trendLimit"
              style="width: 100px"
              @change="handleTrendLimitChange"
            >
              <el-option label="最近4周" :value="4" />
              <el-option label="最近8周" :value="8" />
              <el-option label="最近12周" :value="12" />
            </el-select>
          </div>
          <div class="chart-container" ref="lineChartRef"></div>
        </div>
      </div>

      <!-- 用户画像明细列表 -->
      <div class="table-card">
        <div class="table-header">
          <h3 class="card-title" style="margin-bottom: 0">用户画像明细列表</h3>
          <div class="table-actions">
            <el-input
              v-model="tableSearchKeyword"
              placeholder="搜索手机号..."
              :prefix-icon="Search"
              style="width: 150px"
              clearable
            />
            <el-select
              v-model="satisfactionFilter"
              placeholder="满意度"
              style="width: 100px"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="满意" value="satisfied" />
              <el-option label="一般" value="neutral" />
              <el-option label="不满意" value="unsatisfied" />
            </el-select>
            <el-select
              v-model="emotionFilter"
              placeholder="情感"
              style="width: 90px"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="正向" value="positive" />
              <el-option label="中性" value="neutral" />
              <el-option label="负向" value="negative" />
            </el-select>
            <el-select
              v-model="riskFilter"
              placeholder="风险"
              style="width: 110px"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="流失风险" value="churn" />
              <el-option label="投诉风险" value="complaint" />
              <el-option label="一般" value="medium" />
              <el-option label="无风险" value="none" />
            </el-select>
            <el-select
              v-model="willingnessFilter"
              placeholder="沟通意愿"
              style="width: 110px"
              clearable
              @change="handleFilterChange"
            >
              <el-option label="深度" value="深度" />
              <el-option label="一般" value="一般" />
              <el-option label="较低" value="较低" />
            </el-select>
          </div>
        </div>
        
        <el-table
          :data="customerList"
          style="width: 100%"
          :header-cell-style="{ background: '#F5F7FA', color: '#1F2329', fontWeight: 600 }"
          stripe
          border
          :flexible="true"
          empty-text="暂无客户数据"
        >
          <el-table-column prop="customer_id" label="客户ID" min-width="150" show-overflow-tooltip />
          <el-table-column label="手机号" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.phone || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="所属场景" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              {{ row.task_name || getTaskNameById(row.task_id) }}
            </template>
          </el-table-column>
          <el-table-column label="通话次数" min-width="90" align="center">
            <template #default="{ row }">
              {{ row.total_calls || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="平均通话时长" min-width="120" align="center">
            <template #default="{ row }">
              {{ formatDuration(row.avg_duration) }}
            </template>
          </el-table-column>
          <el-table-column label="满意度" min-width="90" align="center">
            <template #default="{ row }">
              <el-tag
                :type="getSatisfactionType(row.satisfaction)"
                size="small"
              >
                {{ getSatisfactionLabel(row.satisfaction) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="情感" min-width="90" align="center">
            <template #default="{ row }">
              <el-tag
                :type="getEmotionType(row.emotion)"
                size="small"
              >
                {{ getEmotionLabel(row.emotion) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="风险" min-width="100" align="center">
            <template #default="{ row }">
              <span :class="`risk-badge risk-${row.risk_level}`">
                {{ getRiskLevelLabel(row.risk_level) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="沟通意愿" min-width="90" align="center">
            <template #default="{ row }">
              <el-tag
                :type="getWillingnessType(row.willingness)"
                size="small"
              >
                {{ row.willingness || '-' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>

        <div class="table-pagination">
          <span class="pagination-info">
            显示 {{ customerTotal > 0 ? (currentPage - 1) * pageSize + 1 : 0 }} 到 {{ Math.min(currentPage * pageSize, customerTotal) }} 条，共 {{ customerTotal }} 条
          </span>
          <el-pagination
            v-model:current-page="currentPage"
            :page-size="pageSize"
            :total="customerTotal"
            layout="total, prev, pager, next, jumper"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { Filter, Search, Refresh, User, Phone, CircleCheck, Timer } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { fetchTasks, fetchTaskSummary, fetchTaskTrend, fetchCustomers, fetchAvailablePeriods, getRecentPeriods } from '@/api'
import type { Task, TaskSummary, Customer, PeriodType, TrendPoint, AvailablePeriod } from '@/types'

// 状态
const loading = ref(false)
const tasks = ref<Task[]>([])
const selectedTaskId = ref('')
const periodType = ref<PeriodType>('week')  // 固定按周统计
const selectedPeriod = ref('')

// 可用周期列表（从数据库获取）
const availablePeriodsFromDB = ref<AvailablePeriod[]>([])

const summary = ref<TaskSummary | null>(null)
const customerList = ref<Customer[]>([])
const customerTotal = ref(0)
const currentPage = ref(1)
const pageSize = 15

// 表格筛选状态
const tableTaskFilter = ref('')
const tableSearchKeyword = ref('')

// 新增筛选状态
const satisfactionFilter = ref('')  // 满意度筛选
const emotionFilter = ref('')       // 情感筛选
const riskFilter = ref('')          // 风险筛选
const willingnessFilter = ref('')   // 沟通意愿筛选

// 趋势数据（4个维度）
const trendLimit = ref(8)  // 趋势图显示周数
const trendData = ref<{
  satisfaction: TrendPoint[]  // 满意度趋势（满意比例）
  risk: TrendPoint[]          // 风险趋势（流失+投诉比例）
  emotion: TrendPoint[]       // 情感趋势（正向比例）
  willingness: TrendPoint[]   // 沟通意愿趋势（深度比例）
}>({
  satisfaction: [],
  risk: [],
  emotion: [],
  willingness: []
})

// 图表引用
const satisfactionChartRef = ref<HTMLElement | null>(null)
const riskChartRef = ref<HTMLElement | null>(null)
const emotionChartRef = ref<HTMLElement | null>(null)
const willingnessChartRef = ref<HTMLElement | null>(null)
const lineChartRef = ref<HTMLElement | null>(null)

let satisfactionChart: echarts.ECharts | null = null
let riskChart: echarts.ECharts | null = null
let emotionChart: echarts.ECharts | null = null
let willingnessChart: echarts.ECharts | null = null
let lineChart: echarts.ECharts | null = null

// 可选周期列表（优先使用数据库中的，没有则生成默认）
const availablePeriods = computed(() => {
  if (availablePeriodsFromDB.value.length > 0) {
    return availablePeriodsFromDB.value.map(p => p.period_key)
  }
  // 数据库无数据时，生成默认周期列表
  return getRecentPeriods(periodType.value, 12)
})

// 过滤客户列表（支持关键词搜索和多维度筛选）
const filteredCustomerList = computed(() => {
  let result = customerList.value
  
  // 按手机号搜索
  if (tableSearchKeyword.value) {
    const keyword = tableSearchKeyword.value.toLowerCase()
    result = result.filter(c => 
      c.phone && c.phone.includes(keyword)
    )
  }
  
  // 满意度筛选
  if (satisfactionFilter.value) {
    result = result.filter(c => c.satisfaction === satisfactionFilter.value)
  }
  
  // 情感筛选
  if (emotionFilter.value) {
    result = result.filter(c => c.emotion === emotionFilter.value)
  }
  
  // 风险筛选
  if (riskFilter.value) {
    result = result.filter(c => c.risk_level === riskFilter.value)
  }
  
  // 沟通意愿筛选
  if (willingnessFilter.value) {
    result = result.filter(c => c.willingness === willingnessFilter.value)
  }
  
  return result
})

// 是否有激活的筛选条件
const hasActiveFilter = computed(() => {
  return !!tableSearchKeyword.value || 
         !!satisfactionFilter.value || 
         !!emotionFilter.value || 
         !!riskFilter.value || 
         !!willingnessFilter.value
})

// 显示的总数（有筛选时用筛选后的数量，无筛选时用后端返回的总数）
const displayTotal = computed(() => {
  return hasActiveFilter.value ? filteredCustomerList.value.length : customerTotal.value
})

// 显示的客户列表（有筛选时用筛选后的数据，无筛选时用原始数据）
const displayCustomerList = computed(() => {
  return hasActiveFilter.value ? filteredCustomerList.value : customerList.value
})

// 获取周的日期范围
function getWeekDateRange(periodKey: string): { start: string; end: string } {
  // 解析 2025-W48 格式
  const match = periodKey.match(/^(\d{4})-W(\d{2})$/)
  if (!match) return { start: '', end: '' }
  
  const year = parseInt(match[1])
  const week = parseInt(match[2])
  
  // 计算该年第一周的周一
  const jan1 = new Date(year, 0, 1)
  const dayOfWeek = jan1.getDay() || 7  // 周日为7
  
  // ISO周：第一周是包含当年第一个周四的周
  let firstMonday: Date
  if (dayOfWeek <= 4) {
    firstMonday = new Date(year, 0, 1 - dayOfWeek + 1)  // 当周的周一
  } else {
    firstMonday = new Date(year, 0, 1 + (8 - dayOfWeek))  // 下周的周一
  }
  
  // 计算目标周的周一
  const targetMonday = new Date(firstMonday)
  targetMonday.setDate(firstMonday.getDate() + (week - 1) * 7)
  
  // 计算周日
  const targetSunday = new Date(targetMonday)
  targetSunday.setDate(targetMonday.getDate() + 6)
  
  const formatDate = (d: Date) => `${d.getMonth() + 1}月${d.getDate()}日`
  
  return {
    start: formatDate(targetMonday),
    end: formatDate(targetSunday)
  }
}

// 获取周期标签（显示日期范围）
function getPeriodLabel(periodKey: string): string {
  const range = getWeekDateRange(periodKey)
  if (range.start && range.end) {
    return `${periodKey}(${range.start}~${range.end})`
  }
  return periodKey
}

// 获取简短的周期标签（用于趋势图横坐标）
function getPeriodShortLabel(periodKey: string): string {
  const range = getWeekDateRange(periodKey)
  if (range.start && range.end) {
    // 仅显示开始日期
    return `${periodKey.replace(/^\d{4}-/, '')}(${range.start})`
  }
  return periodKey
}

// 获取任务标签
function getTaskLabel(task: Task): string {
  if (task.task_name) {
    return task.task_name
  }
  return `场景 ${task.task_id.slice(0, 8)}...`
}

// 根据任务ID获取任务名称
function getTaskNameById(taskId: string): string {
  const task = tasks.value.find(t => t.task_id === taskId)
  if (task?.task_name) {
    return task.task_name
  }
  return `场景 ${taskId.slice(0, 8)}...`
}

// 初始化图表
function initCharts() {
  if (satisfactionChartRef.value) {
    satisfactionChart = echarts.init(satisfactionChartRef.value)
  }
  if (riskChartRef.value) {
    riskChart = echarts.init(riskChartRef.value)
  }
  if (emotionChartRef.value) {
    emotionChart = echarts.init(emotionChartRef.value)
  }
  if (willingnessChartRef.value) {
    willingnessChart = echarts.init(willingnessChartRef.value)
  }
  if (lineChartRef.value) {
    lineChart = echarts.init(lineChartRef.value)
  }
  updateAllCharts()
}

// 更新所有图表
function updateAllCharts() {
  updateSatisfactionChart()
  updateRiskChart()
  updateEmotionChart()
  updateWillingnessChart()
  updateLineChart()
}

// 创建迷你饼图配置
function createMiniPieOption(data: {value: number, name: string, color: string}[], centerText: string) {
  const hasData = data.some(d => d.value > 0)
  return {
    tooltip: { 
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      avoidLabelOverlap: false,
      data: hasData ? data.map(d => ({
        value: d.value,
        name: d.name,
        itemStyle: { color: d.color }
      })).filter(d => d.value > 0) : [
        { value: 1, name: '暂无数据', itemStyle: { color: '#E5E6EB' } }
      ],
      label: {
        show: true,
        position: 'center',
        formatter: centerText,
        fontSize: 12,
        fontWeight: 'bold',
        color: '#1F2329',
      },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 'bold' }
      }
    }],
  }
}

// 满意度分布图
function updateSatisfactionChart() {
  if (!satisfactionChart) return
  const s = summary.value?.satisfaction
  satisfactionChart.setOption(createMiniPieOption([
    { value: s?.satisfied || 0, name: '满意', color: '#52C41A' },
    { value: s?.neutral || 0, name: '一般', color: '#FAAD14' },
    { value: s?.unsatisfied || 0, name: '不满意', color: '#FF4D4F' },
  ], '满意度'))
}

// 风险分布图
function updateRiskChart() {
  if (!riskChart) return
  const r = summary.value?.risk
  riskChart.setOption(createMiniPieOption([
    { value: r?.high_churn || 0, name: '流失风险', color: '#FF4D4F' },
    { value: r?.high_complaint || 0, name: '投诉风险', color: '#FA8C16' },
    { value: r?.medium || 0, name: '一般', color: '#FAAD14' },
    { value: r?.none || 0, name: '无风险', color: '#52C41A' },
  ], '风险'))
}

// 情感分布图
function updateEmotionChart() {
  if (!emotionChart) return
  const e = summary.value?.emotion
  emotionChart.setOption(createMiniPieOption([
    { value: e?.positive || 0, name: '正向', color: '#52C41A' },
    { value: e?.neutral || 0, name: '中性', color: '#FAAD14' },
    { value: e?.negative || 0, name: '负向', color: '#FF4D4F' },
  ], '情感'))
}

// 沟通意愿分布图
function updateWillingnessChart() {
  if (!willingnessChart) return
  const w = summary.value?.willingness
  willingnessChart.setOption(createMiniPieOption([
    { value: w?.deep || 0, name: '深度', color: '#52C41A' },
    { value: w?.normal || 0, name: '一般', color: '#FAAD14' },
    { value: w?.low || 0, name: '较低', color: '#FF4D4F' },
  ], '沟通意愿'))
}

// 更新折线图（4个维度）
function updateLineChart() {
  if (!lineChart) return

  const satisfactionData = trendData.value.satisfaction
  const riskData = trendData.value.risk
  const emotionData = trendData.value.emotion
  const willingnessData = trendData.value.willingness

  // 获取所有周期标签（使用简短格式显示日期范围）
  // 后端返回的数据已按时间顺序排列（旧→新），无需反转
  const periods = satisfactionData.length > 0 
    ? satisfactionData.map(p => getPeriodShortLabel(p.period))
    : availablePeriods.value.slice(0, trendLimit.value).map(p => getPeriodShortLabel(p))

  // 提取值，转换为百分比
  const satisfactionValues = satisfactionData.map(p => (p.value * 100).toFixed(1))
  const riskValues = riskData.map(p => (p.value * 100).toFixed(1))
  const emotionValues = emotionData.map(p => (p.value * 100).toFixed(1))
  const willingnessValues = willingnessData.map(p => (p.value * 100).toFixed(1))

  lineChart.setOption({
    tooltip: { 
      trigger: 'axis',
      formatter: (params: any) => {
        let result = `${params[0].axisValue}<br/>`
        params.forEach((p: any) => {
          result += `${p.marker} ${p.seriesName}: ${p.value}%<br/>`
        })
        return result
      }
    },
    legend: {
      data: ['满意度', '风险', '正向情感', '深度沟通'],
      top: 0,
      right: 0,
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: '15%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: periods,
      axisLabel: {
        fontSize: 11,
        rotate: periods.length > 6 ? 30 : 0
      }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { formatter: '{value}%' },
    },
    series: [
      {
        name: '满意度',
        type: 'line',
        smooth: true,
        data: satisfactionValues.length > 0 ? satisfactionValues : [0],
        itemStyle: { color: '#52C41A' },
        areaStyle: { color: 'rgba(82, 196, 26, 0.1)' },
      },
      {
        name: '风险',
        type: 'line',
        smooth: true,
        data: riskValues.length > 0 ? riskValues : [0],
        itemStyle: { color: '#FF4D4F' },
        areaStyle: { color: 'rgba(255, 77, 79, 0.1)' },
      },
      {
        name: '正向情感',
        type: 'line',
        smooth: true,
        data: emotionValues.length > 0 ? emotionValues : [0],
        itemStyle: { color: '#1890FF' },
        areaStyle: { color: 'rgba(24, 144, 255, 0.1)' },
      },
      {
        name: '深度沟通',
        type: 'line',
        smooth: true,
        data: willingnessValues.length > 0 ? willingnessValues : [0],
        itemStyle: { color: '#722ED1' },
        areaStyle: { color: 'rgba(114, 46, 209, 0.1)' },
      },
    ],
  })
}

// 加载可用周期列表（从数据库）
async function loadAvailablePeriods() {
  try {
    const data = await fetchAvailablePeriods(periodType.value)
    availablePeriodsFromDB.value = data
    
    // 如果数据库有数据，且当前选中的周期不在列表中，则选择第一个
    if (data.length > 0) {
      const currentPeriodExists = data.some(p => p.period_key === selectedPeriod.value)
      if (!currentPeriodExists) {
        selectedPeriod.value = data[0].period_key
      }
    } else {
      // 数据库无数据，使用默认生成的第一个周期
      const defaultPeriods = getRecentPeriods(periodType.value, 12)
      if (defaultPeriods.length > 0 && !selectedPeriod.value) {
        selectedPeriod.value = defaultPeriods[0]
      }
    }
  } catch (e) {
    console.error('加载可用周期失败:', e)
    availablePeriodsFromDB.value = []
    // 回退到默认周期
    const defaultPeriods = getRecentPeriods(periodType.value, 12)
    if (defaultPeriods.length > 0 && !selectedPeriod.value) {
      selectedPeriod.value = defaultPeriods[0]
    }
  }
}

// 加载场景列表（基于当前选择的周期）
async function loadTasks() {
  try {
    // 传入周期参数，获取该周期内有数据的场景
    const data = await fetchTasks(50, periodType.value, selectedPeriod.value)
    tasks.value = data
    
    // 如果当前选中的场景不在列表中，或者没有选中场景，则默认选择第一个
    const currentTaskExists = tasks.value.some(t => t.task_id === selectedTaskId.value)
    if (!currentTaskExists && tasks.value.length > 0) {
      selectedTaskId.value = tasks.value[0].task_id
      tableTaskFilter.value = selectedTaskId.value
    } else if (tasks.value.length === 0) {
      // 无场景数据，清空选择
      selectedTaskId.value = ''
      tableTaskFilter.value = ''
    }
  } catch (e) {
    console.error('加载场景列表失败:', e)
    tasks.value = []
  }
}

// 加载汇总数据
async function loadSummary() {
  if (!selectedTaskId.value || !selectedPeriod.value) return

  try {
    const data = await fetchTaskSummary(selectedTaskId.value, periodType.value, selectedPeriod.value)
    summary.value = data
    updateAllCharts()
  } catch (e) {
    console.error('加载汇总失败:', e)
    summary.value = null
    updateAllCharts()
  }
}

// 加载趋势数据（4个维度，固定按周显示）
async function loadTrends() {
  if (!selectedTaskId.value) return

  try {
    // 趋势图固定按周显示
    // 满意度趋势：分子为"满意"的比例
    // 风险趋势：分子为"流失风险"+"投诉风险"的比例
    // 情感趋势：分子为"正向"的比例
    // 沟通意愿趋势：分子为"深度"的比例
    const limit = trendLimit.value
    const [satisfactionTrend, riskTrend, emotionTrend, willingnessTrend] = await Promise.all([
      fetchTaskTrend(selectedTaskId.value, 'week', 'satisfied_rate', limit),
      fetchTaskTrend(selectedTaskId.value, 'week', 'high_risk_rate', limit),  // 综合风险率
      fetchTaskTrend(selectedTaskId.value, 'week', 'positive_rate', limit),   // 正向情感率
      fetchTaskTrend(selectedTaskId.value, 'week', 'deep_willingness_rate', limit),  // 深度沟通率
    ])
    
    trendData.value = {
      satisfaction: satisfactionTrend.series || [],
      risk: riskTrend.series || [],
      emotion: emotionTrend.series || [],
      willingness: willingnessTrend.series || []
    }
    updateLineChart()
  } catch (e) {
    console.error('加载趋势失败:', e)
    trendData.value = { satisfaction: [], risk: [], emotion: [], willingness: [] }
    updateLineChart()
  }
}

// 加载所有数据
async function loadData() {
  if (!selectedTaskId.value || !selectedPeriod.value) return
  loading.value = true
  
  try {
    await Promise.all([loadSummary(), loadTrends(), loadCustomers()])
  } finally {
    loading.value = false
  }
}

// 加载客户列表
async function loadCustomers() {
  // 使用表格筛选的场景，如果没有则使用当前选中的场景
  const taskId = tableTaskFilter.value || selectedTaskId.value
  if (!taskId || !selectedPeriod.value) return

  try {
    // 构建筛选参数
    const filters = {
      phone: tableSearchKeyword.value || undefined,
      satisfaction: satisfactionFilter.value || undefined,
      emotion: emotionFilter.value || undefined,
      risk_level: riskFilter.value || undefined,
      willingness: willingnessFilter.value || undefined,
    }
    
    const result = await fetchCustomers(taskId, periodType.value, selectedPeriod.value, currentPage.value, pageSize, filters)
    customerList.value = result.list
    customerTotal.value = result.total
  } catch (e) {
    console.error('加载客户列表失败:', e)
    // API 失败时清空列表
    customerList.value = []
    customerTotal.value = 0
  }
}

// 刷新数据
function refreshData() {
  loadData()
}

// 导出数据
function exportData() {
  // TODO: 实现导出功能
  console.log('导出数据...')
}

function handleTaskChange() {
  currentPage.value = 1
  // 同步表格筛选器为当前选择的场景
  tableTaskFilter.value = selectedTaskId.value
  loadData()
}

// 周期选择变化
async function handlePeriodChange() {
  currentPage.value = 1
  // 周期变化时，重新加载场景列表
  await loadTasks()
  loadData()
}

// 表格场景筛选变化
function handleTableTaskFilterChange() {
  currentPage.value = 1
  loadCustomers()
}

// 筛选条件变化（满意度、情感、风险、沟通意愿）
function handleFilterChange() {
  currentPage.value = 1
  loadCustomers()  // 重新请求后端
}

// 分页变化
function handlePageChange(page: number) {
  currentPage.value = page
  loadCustomers()  // 重新请求后端
}

// 趋势图周数选择变化
function handleTrendLimitChange() {
  loadTrends()
}

// 格式化函数
function formatDuration(seconds: number | undefined): string {
  if (seconds === undefined || seconds === null) return '-'
  const min = Math.floor(seconds / 60)
  const sec = Math.round(seconds % 60)
  return min > 0 ? `${min}分${sec}秒` : `${sec}秒`
}

function formatDurationShort(seconds: number | undefined): string {
  if (seconds === undefined || seconds === null) return '-'
  if (seconds < 60) return `${Math.round(seconds)}秒`
  return `${(seconds / 60).toFixed(1)}分`
}

function formatPercent(rate: number | undefined): string {
  if (rate === undefined || rate === null) return '-'
  return `${(rate * 100).toFixed(1)}%`
}

function getSatisfactionType(satisfaction: string): '' | 'success' | 'warning' | 'danger' {
  switch (satisfaction) {
    case 'satisfied': return 'success'
    case 'neutral': return 'warning'
    case 'unsatisfied': return 'danger'
    default: return ''
  }
}

function getSatisfactionLabel(satisfaction: string): string {
  switch (satisfaction) {
    case 'satisfied': return '满意'
    case 'neutral': return '一般'
    case 'unsatisfied': return '不满意'
    default: return '-'
  }
}

function getRiskLabel(risk: string): string {
  switch (risk) {
    case 'high': return '高'
    case 'medium': return '中'
    case 'low': return '低'
    default: return '-'
  }
}

// 综合风险标签
function getRiskLevelLabel(riskLevel: string): string {
  switch (riskLevel) {
    case 'churn': return '流失风险'
    case 'complaint': return '投诉风险'
    case 'medium': return '一般'
    case 'none': return '无风险'
    default: return '-'
  }
}

// 情感类型
function getEmotionType(emotion: string): '' | 'success' | 'warning' | 'danger' {
  switch (emotion) {
    case 'positive': return 'success'
    case 'neutral': return 'warning'
    case 'negative': return 'danger'
    default: return ''
  }
}

// 情感标签
function getEmotionLabel(emotion: string): string {
  switch (emotion) {
    case 'positive': return '正向'
    case 'neutral': return '中性'
    case 'negative': return '负向'
    default: return '-'
  }
}

// 沟通意愿类型
function getWillingnessType(willingness: string): '' | 'success' | 'warning' | 'info' {
  switch (willingness) {
    case '深度': return 'success'
    case '一般': return 'warning'
    case '较低': return 'info'
    default: return ''
  }
}

// 监听窗口大小变化
function handleResize() {
  satisfactionChart?.resize()
  riskChart?.resize()
  emotionChart?.resize()
  willingnessChart?.resize()
  lineChart?.resize()
}

// 生命周期
onMounted(async () => {
  loading.value = true
  try {
    // 1. 先从数据库加载可用周期（会自动选择第一个有数据的周期）
    await loadAvailablePeriods()
    
    // 2. 加载该周期内的场景列表（会自动选择第一个场景）
    await loadTasks()
    
    // 3. 初始化图表
    await nextTick()
    initCharts()
    
    // 4. 加载数据
    await loadData()
  } finally {
    loading.value = false
  }
  
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  satisfactionChart?.dispose()
  riskChart?.dispose()
  emotionChart?.dispose()
  willingnessChart?.dispose()
  lineChart?.dispose()
})
</script>

<style scoped>
.portrait-dashboard {
  min-height: 100vh;
  background: var(--bg-color);
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 卡片标题带操作 */
.card-header-with-action {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-header-with-action .card-title {
  margin-bottom: 0;
}

/* 概览卡片 */
.overview-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.overview-card {
  background: var(--card-bg);
  border-radius: var(--border-radius);
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: var(--shadow-sm);
}

.overview-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.overview-info {
  display: flex;
  flex-direction: column;
}

.overview-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.overview-label {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* 4个维度统计卡片布局 */
.stats-grid-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.mini-chart-card {
  padding: 16px;
}

.mini-chart-card .card-title {
  margin-bottom: 8px;
  font-size: 14px;
}

.mini-chart-container {
  height: 180px;
}

@media (max-width: 1200px) {
  .stats-grid-4 {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .stats-grid-4 {
    grid-template-columns: 1fr;
  }
}

.table-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.table-pagination {
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--border-color);
  background: var(--card-bg);
}

.pagination-info {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 表格样式优化 */
.table-card :deep(.el-table) {
  --el-table-border-color: var(--border-color);
}

.table-card :deep(.el-table th.el-table__cell) {
  background: #F5F7FA !important;
}

.table-card :deep(.el-table td.el-table__cell) {
  padding: 12px 0;
}

.table-card :deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background: #FAFAFA;
}

/* 标签单元格样式 */
.tags-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tag-item {
  margin: 0 !important;
}

/* 风险标签样式 */
.risk-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.risk-badge.risk-high {
  background: #FFF1F0;
  color: var(--danger-color);
}

.risk-badge.risk-medium {
  background: #FFF7E6;
  color: var(--warning-color);
}

.risk-badge.risk-low {
  background: #F6FFED;
  color: var(--success-color);
}

/* 综合风险标签样式 */
.risk-badge.risk-churn {
  background: #FFF1F0;
  color: #FF4D4F;
}

.risk-badge.risk-complaint {
  background: #FFF7E6;
  color: #FA8C16;
}

.risk-badge.risk-none {
  background: #F6FFED;
  color: var(--success-color);
}

/* 响应式 */
@media (max-width: 1200px) {
  .overview-cards {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .stats-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .overview-cards {
    grid-template-columns: 1fr;
  }
  
  .filter-bar {
    flex-wrap: wrap;
  }
}
</style>
