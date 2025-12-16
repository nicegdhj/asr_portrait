import axios from 'axios'
import type { ApiResponse, Task, TaskSummary, TaskTrend, Customer, PeriodType, CustomerListResponse, AvailablePeriod } from '@/types'

const api = axios.create({
    baseURL: '/api/v1',
    timeout: 30000,
})

// 获取可用周期列表（从数据库）
export async function fetchAvailablePeriods(periodType: PeriodType): Promise<AvailablePeriod[]> {
    const res = await api.get<ApiResponse<AvailablePeriod[]>>('/task/periods', {
        params: { period_type: periodType }
    })
    return res.data.data
}

// 获取场景列表（支持按周期过滤）
export async function fetchTasks(
    limit = 50,
    periodType?: PeriodType,
    periodKey?: string
): Promise<Task[]> {
    const params: Record<string, any> = { limit }
    if (periodType) params.period_type = periodType
    if (periodKey) params.period_key = periodKey

    const res = await api.get<ApiResponse<Task[]>>('/task', { params })
    return res.data.data
}

// 获取任务汇总
export async function fetchTaskSummary(
    taskId: string,
    periodType: PeriodType,
    periodKey: string
): Promise<TaskSummary> {
    const res = await api.get<ApiResponse<TaskSummary>>(`/task/${taskId}/summary`, {
        params: { period_type: periodType, period_key: periodKey },
    })
    return res.data.data
}

// 获取任务趋势
export async function fetchTaskTrend(
    taskId: string,
    periodType: PeriodType,
    metric: string,
    limit = 12
): Promise<TaskTrend> {
    const res = await api.get<ApiResponse<TaskTrend>>(`/task/${taskId}/trend`, {
        params: { period_type: periodType, metric, limit },
    })
    return res.data.data
}

// 筛选参数类型
interface CustomerFilters {
    phone?: string
    satisfaction?: string
    emotion?: string
    risk_level?: string
    willingness?: string
}

// 获取客户列表（真实 API）
export async function fetchCustomers(
    taskId: string,
    periodType: PeriodType,
    periodKey: string,
    page = 1,
    pageSize = 15,
    filters?: CustomerFilters
): Promise<{ list: Customer[]; total: number }> {
    const params: Record<string, any> = {
        period_type: periodType,
        period_key: periodKey,
        page,
        page_size: pageSize,
    }

    // 添加筛选参数
    if (filters) {
        if (filters.phone) params.phone = filters.phone
        if (filters.satisfaction) params.satisfaction = filters.satisfaction
        if (filters.emotion) params.emotion = filters.emotion
        if (filters.risk_level) params.risk_level = filters.risk_level
        if (filters.willingness) params.willingness = filters.willingness
    }

    const res = await api.get<ApiResponse<CustomerListResponse>>(`/task/${taskId}/customers`, {
        params,
    })
    return {
        list: res.data.data.list,
        total: res.data.data.total,
    }
}

// 工具函数：获取最近的周期列表
export function getRecentPeriods(periodType: PeriodType, count = 8): string[] {
    const periods: string[] = []
    const now = new Date()

    for (let i = 0; i < count; i++) {
        const date = new Date(now)

        if (periodType === 'week') {
            date.setDate(date.getDate() - i * 7)
            const year = date.getFullYear()
            const week = getWeekNumber(date)
            periods.push(`${year}-W${String(week).padStart(2, '0')}`)
        } else if (periodType === 'month') {
            date.setMonth(date.getMonth() - i)
            periods.push(date.toISOString().slice(0, 7))
        } else if (periodType === 'quarter') {
            date.setMonth(date.getMonth() - i * 3)
            const year = date.getFullYear()
            const quarter = Math.floor(date.getMonth() / 3) + 1
            periods.push(`${year}-Q${quarter}`)
        }
    }

    return periods
}

function getWeekNumber(date: Date): number {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
    const dayNum = d.getUTCDay() || 7
    d.setUTCDate(d.getUTCDate() + 4 - dayNum)
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
    return Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
}
