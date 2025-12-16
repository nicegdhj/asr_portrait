// API 类型定义

export interface Task {
    task_id: string
    task_name: string | null
    call_count: number
    customer_count: number
    first_call?: string  // 可选，不按周期查询时返回
    last_call?: string   // 可选，不按周期查询时返回
}

export interface TaskSummary {
    task_id: string
    task_name: string | null
    period_type: string
    period_key: string
    total_customers: number
    total_calls: number
    connected_calls: number
    connect_rate: number
    avg_duration: number
    // 满意度分布
    satisfaction: {
        satisfied: number
        satisfied_rate: number
        neutral: number
        unsatisfied: number
    }
    // 风险分布
    risk: {
        high_complaint: number
        high_complaint_rate: number
        high_churn: number
        high_churn_rate: number
        medium: number
        none: number
        high_risk_rate: number
    }
    // 情感分布
    emotion: {
        positive: number
        neutral: number
        negative: number
        positive_rate: number
    }
    // 沟通意愿分布
    willingness: {
        deep: number
        normal: number
        low: number
        deep_rate: number
    }
}

export interface TrendPoint {
    period: string
    value: number
}

export interface TaskTrend {
    task_id: string
    metric: string
    series: TrendPoint[]
}

export interface Customer {
    customer_id: string
    phone: string | null
    task_id: string
    task_name: string | null
    total_calls: number
    avg_duration: number
    satisfaction: 'satisfied' | 'neutral' | 'unsatisfied' | null
    emotion: 'positive' | 'neutral' | 'negative' | null
    risk_level: 'churn' | 'complaint' | 'medium' | 'none' | null
    willingness: '深度' | '一般' | '较低' | null
}

export interface CustomerListResponse {
    list: Customer[]
    total: number
    page: number
    page_size: number
}

export interface ApiResponse<T> {
    code: number
    message: string
    data: T
}

export type PeriodType = 'week' | 'month' | 'quarter'

export interface AvailablePeriod {
    period_type: string
    period_key: string
    total_users: number
    total_records: number
}
