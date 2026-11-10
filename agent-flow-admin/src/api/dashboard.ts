import request from './request'

/** 工作台任务统计（基于 workflow_runs，最近 7 天为当前周期） */
export interface DashboardTaskStats {
  total: number
  completed: number
  running: number
  abnormal: number
  success_rate: number
  total_delta: number | null
  completed_delta: number | null
  abnormal_delta: number | null
  today_total: number
  avg_duration_ms: number | null
}

export interface DashboardApprovalItem {
  claim_no: string
  title: string
  applicant: string
  category: string | null
  status: string
  amount: string
  currency: string
  submitted_at: string | null
}

export interface DashboardApprovalSummary {
  pending_count: number
  processing_count: number
  pending_amount: string
  items: DashboardApprovalItem[]
}

export interface DashboardQuickStats {
  pending_approvals: number
  kb_count: number
  doc_total: number
  doc_processing: number
  doc_failed: number
  user_count: number
  /** 解析异常 / 解析中文档最多的知识库 uid（快捷入口直达其文档列表） */
  failed_kb_uid: string | null
  processing_kb_uid: string | null
}

export interface DashboardRecordItem {
  uid: string
  name: string
  executor: string
  status: string
  started_at: string
  duration_ms: number | null
}

export interface DashboardSummary {
  tasks: DashboardTaskStats
  approvals: DashboardApprovalSummary
  quick: DashboardQuickStats
  records: DashboardRecordItem[]
  records_total: number
  generated_at: string
}

export interface DashboardTrendPoint {
  label: string
  bucket: string
  total: number
  success: number
  failed: number
}

export interface DashboardTrend {
  range: DashboardTrendRange
  points: DashboardTrendPoint[]
}

export type DashboardTrendRange = '1h' | '24h' | '7d'

export interface DashboardHealthComponent {
  key: string
  name: string
  status: 'ok' | 'degraded' | 'down'
  latency_ms: number | null
  detail: string | null
}

export interface DashboardWorkerStatus {
  key: string
  name: string
  queue: string
  online: boolean
  status: 'online' | 'busy' | 'offline'
  queued: number
  capacity: number
  last_active_at: string | null
  detail: string | null
}

export interface DashboardHealth {
  cpu_percent: number
  memory_used_gb: number
  memory_total_gb: number
  memory_percent: number
  avg_response_ms: number | null
  components: DashboardHealthComponent[]
  workers: DashboardWorkerStatus[]
  checked_at: string
}

export const getDashboardSummary = () => request.get<DashboardSummary>('/api/v1/admin/dashboard/summary')

export const getDashboardTrend = (range: DashboardTrendRange = '24h') =>
  request.get<DashboardTrend>('/api/v1/admin/dashboard/trend', { params: { range } })

export const getDashboardHealth = () => request.get<DashboardHealth>('/api/v1/admin/dashboard/health')
