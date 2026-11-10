import request from './request'

/** AI 预审记录 */
export interface PreReviewInfo {
  uid: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  result: 'pass' | 'fail' | 'manual_review' | null
  risk_level: 'high' | 'medium' | 'low' | 'none' | null
  summary: string | null
  result_data: {
    problems?: string[]
    evidence?: string
    is_document_valid?: boolean
    extracted_data?: Record<string, unknown>
  } | null
  model_name: string | null
  prompt_version: string | null
  started_at: string | null
  finished_at: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

/** 申请人信息（管理员视角） */
export interface ClaimApplicant {
  id: number
  uid: string
  username: string
  nickname: string | null
}

/** 报销单列表项 */
export interface ExpenseClaimItem {
  id: number
  claim_no: string
  title: string
  description: string | null
  status: string
  total_amount: string
  currency: string
  item_count: number
  categories: string[]
  /** 费用明细描述集合（列表「描述」列） */
  descriptions: string[]
  submitted_at: string | null
  created_at: string
  updated_at: string
  pre_review: PreReviewInfo | null
  applicant?: ClaimApplicant
  /** 发票等附件（待审批列表/详情带预签名 preview_url） */
  attachments?: ClaimAttachment[]
}

/** 报销附件（preview_url 为 MinIO 预签名临时链接，约 30 分钟有效） */
export interface ClaimAttachment {
  id: number
  expense_item_id: number | null
  original_filename: string
  content_type: string | null
  file_size: number | null
  created_at: string
  preview_url: string | null
  /** 缩略图预签名链接（原图常达数 MB，列表页只用缩略图；历史附件可能为空） */
  thumb_url?: string | null
}

/** 判断附件是否为图片（用于决定缩略图预览还是文件链接） */
export const isImageAttachment = (a: ClaimAttachment): boolean =>
  !!a.content_type?.startsWith('image/') ||
  /\.(jpe?g|png|gif|webp|bmp)$/i.test(a.original_filename || '')

/** 报销单统计 */
export interface ClaimStats {
  in_progress: number
  completed: number
  abnormal: number
  month_count: number
  month_amount: string
  /** 各状态原始分布（Tab 徽标用） */
  status_counts: Record<string, number>
  total: number
}

/** 列表筛选条件（两个列表接口共用） */
export interface ClaimListFilter {
  status?: string
  keyword?: string
  /** 提交时间起始（含当天），yyyy-MM-dd */
  date_from?: string
  /** 提交时间截止（含当天），yyyy-MM-dd */
  date_to?: string
  page?: number
  page_size?: number
}

/** 人工审批记录 */
export interface ApprovalRecordItem {
  id: number
  status: 'approved' | 'rejected'
  comment: string | null
  decided_at: string | null
  created_at: string
  approver: { id: number; username: string; nickname: string | null } | null
}

/** 报销单详情 */
export interface ExpenseClaimDetail extends Omit<ExpenseClaimItem, 'item_count' | 'categories'> {
  /** 费用明细条数（聊天内详情等场景可能不下发） */
  item_count?: number
  /** 费用类别列表（聊天内详情等场景可能不下发） */
  categories?: string[]
  items: {
    id: number
    category: string
    description: string | null
    amount: string
    expense_date: string | null
  }[]
  attachments: ClaimAttachment[]
  /** 人工审批记录（最新在前，来自 approval_records 连表审批人） */
  approvals?: ApprovalRecordItem[]
}

/** 分页结果 */
export interface ClaimPageResult {
  items: ExpenseClaimItem[]
  total: number
  page: number
  page_size: number
}

/** 审批决策请求 */
export interface ApprovalDecisionPayload {
  decision: 'approved' | 'rejected'
  comment?: string | null
}

/** 我的申请列表 */
export const listMyClaimsApi = (params: ClaimListFilter) =>
  request.get<ClaimPageResult>('/api/v1/expense-claims', { params })

/** 我的申请统计 */
export const getClaimStatsApi = () => request.get<ClaimStats>('/api/v1/expense-claims/stats')

/** 报销单详情（按 claim_no 查询） */
export const getClaimDetailApi = (claimNo: string) =>
  request.get<ExpenseClaimDetail>(`/api/v1/expense-claims/${claimNo}`)

/** 待我审批列表（管理员） */
export const listPendingApprovalsApi = (params: ClaimListFilter) =>
  request.get<ClaimPageResult>('/api/v1/expense-claims/pending-approvals', { params })

/** 审批决策（管理员，按 claim_no 定位单据） */
export const decideApprovalApi = (claimNo: string, data: ApprovalDecisionPayload) =>
  request.post<unknown>(`/api/v1/expense-claims/${claimNo}/approval`, data)

/** 最新 AI 预审结果 */
export const getLatestPreReviewApi = (claimId: number) =>
  request.get<{ claim_id: number; claim_no: string; review: PreReviewInfo | null }>(
    `/api/v1/expense-claims/${claimId}/pre-reviews/latest`
  )

/** 重新触发 AI 初审（初审失败后重试） */
export const retryPreReviewApi = (claimId: number) =>
  request.post<{
    claim_id: number
    claim_no: string
    review: { uid: string; status: string; enqueued: boolean }
  }>(`/api/v1/expense-claims/${claimId}/pre-reviews/retry`)

/**
 * 按当前筛选条件拉取全量数据并导出 CSV（带 BOM，Excel 直接打开不乱码）。
 * 分页循环拉取，安全上限 50 页 × 100 条。
 */
export async function exportClaimsCsv(
  fetcher: (params: ClaimListFilter) => Promise<{ data: ClaimPageResult }>,
  filter: ClaimListFilter,
  headers: string[],
  buildRow: (item: ExpenseClaimItem) => string[],
  filename: string
): Promise<void> {
  const pageSize = 100
  const all: ExpenseClaimItem[] = []
  let page = 1
  for (;;) {
    const res = await fetcher({ ...filter, page, page_size: pageSize })
    all.push(...res.data.items)
    if (all.length >= res.data.total || res.data.items.length === 0) break
    page += 1
    if (page > 50) break
  }
  const escape = (v: string) => (/[",\n\r]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)
  const lines = [headers, ...all.map(buildRow)].map((row) => row.map(escape).join(','))
  const blob = new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
