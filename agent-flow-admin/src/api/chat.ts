import request from './request'

/** 工作流运行状态（与后端 WorkflowRunStatus 枚举一致） */
export type WorkflowRunStatus =
  | 'pending'
  | 'running'
  | 'waiting_input'
  | 'waiting_confirmation'
  | 'waiting_approval'
  | 'success'
  | 'failed'
  | 'cancelled'

/** 工作流步骤状态（与后端 RunStepStatus 枚举一致） */
export type RunStepStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped'

/** SSE 事件名（后端实际会发送的事件） */
export type WorkflowEventName =
  | 'run_snapshot'
  | 'run_started'
  | 'step_started'
  | 'progress'
  | 'content_delta'
  | 'assistant_message'
  | 'run_completed'
  | 'run_failed'
  | 'run_cancelled'

/** 事件作用范围：工作流 / 步骤 / 聊天消息 */
export type WorkflowEventScope = 'run' | 'step' | 'message'

/** 费用明细附件（发票等，后端 display.expense_summary[].attachments 的单条记录） */
export interface BusinessTaskAttachmentItem {
  uid: string
  filename: string
  content_type: string
  file_size: number
  created_at?: string | null
}

/** 费用明细草稿（draft_data.expense_items 的单条记录） */
export interface ExpenseItemDraft {
  id: string
  category?: string | null
  amount?: string | number | null
  description?: string | null
  expense_date?: string | null
  /** 发票状态：至少上传一张，由 missing_fields 的 invoice 路径驱动 */
  invoice_uploaded?: boolean | null
  invoice_count?: number | null
  attachments?: BusinessTaskAttachmentItem[] | null
  [key: string]: unknown
}

/** 任务展示摘要（后端 display 字段，单任务卡片的主数据源） */
export interface BusinessTaskDisplay {
  display_title?: string | null
  total_amount?: string | number | null
  currency?: string | null
  item_count?: number | null
  expense_summary?: ExpenseItemDraft[] | null
  claim_no?: string | null
  created_at?: string | null
}

/** 业务任务卡片（extra_data 协议中的单条任务） */
export interface BusinessTaskCardItem {
  uid: string
  title: string
  task_type: string
  status: string
  /** 字段路径数组（如 expense_items.item-001.category），由前端解析映射，不直接展示 */
  missing_fields: string[]
  /** 正式报销单状态（与任务状态不同维度，可能为 null） */
  claim_status?: string | null
  /** 展示摘要：金额 / 明细 / 单号 / 创建时间 */
  display?: BusinessTaskDisplay | null
  /** 草稿数据（部分卡片路径下发，用于定位缺失字段对应的费用明细） */
  draft_data?: { expense_items?: ExpenseItemDraft[] } | null
}

/** 多个待处理任务：待用户点击选择 */
export interface BusinessTaskListPayload {
  ui_type: 'business_task_list'
  business_tasks: BusinessTaskCardItem[]
}

/** 单个任务：用户已选择或后端自动关联 */
export interface BusinessTaskPayload {
  ui_type: 'business_task'
  business_task: BusinessTaskCardItem
}

/** 报销单列表卡片条目（extra_data.ui_type = expense_claim_list） */
export interface ExpenseClaimCardItem {
  claim_no: string
  title?: string | null
  description?: string | null
  status?: string | null
  total_amount?: string | number | null
  currency?: string | null
  item_count?: number | null
  categories?: string[] | null
  descriptions?: string[] | null
  submitted_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  pre_review?: {
    status?: string | null
    result?: string | null
    risk_level?: string | null
    summary?: string | null
    /** AI 预审结构化结果（卡片内提取关键信息/问题清单） */
    result_data?: {
      problems?: string[] | null
      evidence?: string | null
      is_document_valid?: boolean | null
      extracted_data?: Record<string, unknown> | null
    } | null
    started_at?: string | null
    finished_at?: string | null
  } | null
}

/** 报销单列表分页信息 */
export interface ExpenseClaimPagination {
  total: number
  page: number
  page_size: number
  total_pages: number
}

/** 报销记录列表卡片 */
export interface ExpenseClaimListPayload {
  ui_type: 'expense_claim_list'
  expense_claims: ExpenseClaimCardItem[]
  pagination?: ExpenseClaimPagination | null
}

/** 报销单详情卡片（extra_data.ui_type = expense_claim_detail） */
export interface ExpenseClaimDetailPayload {
  ui_type: 'expense_claim_detail'
  expense_claim: ExpenseClaimCardItem & {
    /** 费用明细 */
    items?: {
      id?: number
      category?: string | null
      description?: string | null
      amount?: string | number | null
      expense_date?: string | null
    }[] | null
    /** 审批记录（后端 ApprovalRecord.status：pending/approved/rejected，兼容 decision 字段名） */
    approvals?: {
      id?: number
      status?: string | null
      decision?: string | null
      comment?: string | null
      created_at?: string | null
      decided_at?: string | null
      approver_name?: string | null
      approver?: { nickname?: string | null; username?: string | null } | null
    }[] | null
    /** 发票凭证（聊天卡片内只展示数量） */
    attachments?: { original_filename?: string | null; content_type?: string | null }[] | null
  }
}

/** 报销审批进度卡片（extra_data.ui_type = expense_progress） */
export interface ExpenseClaimProgressPayload {
  ui_type: 'expense_progress'
  expense_progress: {
    claim_no: string
    title?: string | null
    status?: string | null
    total_amount?: string | number | null
    currency?: string | null
    submitted_at?: string | null
    /** 审批时间线节点（ApprovalRecord：pending/approved/rejected） */
    approvals?: {
      id?: number
      status?: string | null
      comment?: string | null
      created_at?: string | null
      decided_at?: string | null
      approver?: { username?: string | null; nickname?: string | null } | null
    }[] | null
  }
}

/** 报销审批历史卡片（extra_data.ui_type = expense_approval_history） */
export interface ExpenseClaimApprovalHistoryPayload {
  ui_type: 'expense_approval_history'
  expense_approval_history: {
    claim_no: string
    title?: string | null
    status?: string | null
    total_amount?: string | number | null
    currency?: string | null
    approvals?: {
      id?: number
      status?: string | null
      comment?: string | null
      created_at?: string | null
      decided_at?: string | null
      approver?: { username?: string | null; nickname?: string | null } | null
    }[] | null
  }
}

/** 报销 AI 预审报告卡片（extra_data.ui_type = expense_pre_review） */
export interface ExpensePreReviewPayload {
  ui_type: 'expense_pre_review'
  expense_pre_review: {
    claim_no: string
    title?: string | null
    status?: string | null
    total_amount?: string | number | null
    currency?: string | null
    pre_review?: {
      uid?: string
      status?: string | null
      result?: string | null
      risk_level?: string | null
      summary?: string | null
      result_data?: {
        problems?: string[] | null
        evidence?: string | null
        is_document_valid?: boolean | null
        extracted_data?: Record<string, unknown> | null
      } | null
      started_at?: string | null
      finished_at?: string | null
      error_message?: string | null
    } | null
  }
}

/** 报销统计卡片（extra_data.ui_type = expense_statistics） */
export interface ExpenseStatisticsPayload {
  ui_type: 'expense_statistics'
  total?: number | null
  date_from?: string | null
  date_to?: string | null
  /** 状态 → 数量 */
  status_counts?: Record<string, number> | null
  currency_statistics?: {
    currency?: string | null
    claim_count?: number | null
    total_amount?: string | number | null
    average_amount?: string | number | null
  }[] | null
  category_statistics?: {
    category?: string | null
    currency?: string | null
    item_count?: number | null
    total_amount?: string | number | null
  }[] | null
}

/** 知识库引用来源条目（extra_data.ui_type = knowledge_sources） */
export interface KnowledgeSourceItem {
  index?: number | null
  document_title?: string | null
  knowledge_base_name?: string | null
  location?: string | null
}

/** 知识库引用来源卡片 */
export interface KnowledgeSourcesPayload {
  ui_type: 'knowledge_sources'
  knowledge_sources?: KnowledgeSourceItem[] | null
}

/** 消息 extra_data：卡片协议，未知类型/空值都需兼容 */
export type ChatMessageExtraData =
  | BusinessTaskListPayload
  | BusinessTaskPayload
  | ExpenseClaimListPayload
  | ExpenseClaimDetailPayload
  | ExpenseClaimProgressPayload
  | ExpenseClaimApprovalHistoryPayload
  | ExpensePreReviewPayload
  | ExpenseStatisticsPayload
  | KnowledgeSourcesPayload
  | Record<string, unknown>
  | null

/** 用户发送消息时可携带的业务交互动作 */
export interface MessageSendOptions {
  content: string
  action?: string
  selected_task_uid?: string
}

/** 工作流运行的真实指标（后端 run_metrics，随消息 extra_data / run_completed 下发） */
export interface RunMetrics {
  /** 本次运行实际使用的模型名 */
  engine?: string | null
  /** 运行耗时（毫秒） */
  duration_ms?: number | null
  /** 实际调用大模型的次数 */
  llm_calls?: number | null
  /** 知识库重排后的命中条数（未触发检索时为 0） */
  rag_hits?: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
}

/** 工作流 SSE 事件的统一数据结构（各字段按事件类型可选） */
export interface WorkflowEvent {
  /** 单条事件唯一标识，用于客户端去重 */
  event_uid?: string
  run_uid?: string
  event?: string
  /** 事件影响范围，决定 status 属于工作流维度还是步骤维度 */
  scope?: WorkflowEventScope
  time?: string
  /** 进度说明（不是聊天正文） */
  message?: string
  status?: WorkflowRunStatus | RunStepStatus | null
  step_name?: string
  /** 步骤展示名，优先级高于 step_name / step_key */
  display_name?: string
  /** 步骤稳定标识，用于更新同一步骤节点 */
  step_key?: string
  message_uid?: string
  /** AI 消息正文（assistant_message 的完整内容） */
  content?: string
  /** 增量文本片段（content_delta 事件） */
  delta?: string
  /** Token 用量（assistant_message 事件可能一并下发） */
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
  /** 业务卡片数据（assistant_message 可选携带） */
  extra_data?: ChatMessageExtraData
  /** 运行指标（run_completed / run_failed 事件携带） */
  metrics?: RunMetrics | null
  error_message?: string
}

/** 发送消息后返回的工作流运行信息 */
export interface RunInfo {
  uid: string
  status: WorkflowRunStatus
}

/** 工作流状态查询响应 */
export interface WorkflowRunStatusResponse {
  conversation_uid: string
  run_uid: string
  status: WorkflowRunStatus
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  /** 本次运行实际使用的模型（后端配置） */
  model_name?: string | null
  /** 运行耗时（毫秒），未结束时为 null */
  duration_ms?: number | null
}

export interface ConversationResponse {
  uid: string
  title: string
  created_at: string
  updated_at: string
}

export interface MessageItem {
  uid: string
  role: string
  content: string
  /** Token 用量，后端未统计时为 null */
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
  extra_data: ChatMessageExtraData
  created_at: string
}

export interface MessageSendResponse {
  conversation_uid: string
  user_message: MessageItem
  // AI 回复由后台异步生成，接口返回时可能尚未完成
  assistant_message: MessageItem | null
  run: RunInfo
}

export interface ConversationListResponse {
  items: ConversationResponse[]
  total: number
}

export interface MessageListResponse {
  conversation_uid: string
  items: MessageItem[]
  total: number
}

// 创建会话
export const createConversationApi = (data: { title: string }) => {
  return request.post<ConversationResponse>('/api/v1/conversations', data)
}

// 发送消息（路径参数为会话 uid，返回本次工作流的 run.uid）
// 点击业务任务卡片时额外携带 action / selected_task_uid，走同一套发送与 SSE 流程
export const sendMessageApi = (conversationUid: string, data: MessageSendOptions) => {
  return request.post<MessageSendResponse>(`/api/v1/conversations/${conversationUid}/messages`, data)
}

// 获取会话列表
export const getConversationsApi = () => {
  return request.get<ConversationListResponse>('/api/v1/conversations')
}

// 搜索历史会话（后端按标题 ilike 模糊匹配，关键词为必填 1-50 字）
export const searchConversationsApi = (keyword: string, page = 1, pageSize = 20) => {
  return request.get<ConversationListResponse>('/api/v1/conversations/search', {
    params: { keyword, page, page_size: pageSize }
  })
}

// 修改会话标题（后端会 trim 并截断到 20 字）
export const updateConversationTitleApi = (conversationUid: string, title: string) => {
  return request.patch<ConversationResponse>(`/api/v1/conversations/${conversationUid}`, { title })
}

// 删除会话（幂等：不存在时返回 deleted=false，不报错）
export const deleteConversationApi = (conversationUid: string) => {
  return request.delete<{ conversation_uid: string; deleted: boolean }>(
    `/api/v1/conversations/${conversationUid}`
  )
}

// 获取单个会话的历史消息（路径参数为会话 uid）
export const getConversationMessagesApi = (conversationUid: string) => {
  return request.get<MessageListResponse>(`/api/v1/conversations/${conversationUid}/messages`)
}

// 查询工作流运行状态（断线重连前用于核对真实状态）
export const getWorkflowRunStatusApi = (conversationUid: string, runUid: string) => {
  return request.get<WorkflowRunStatusResponse>(`/api/v1/conversations/${conversationUid}/runs/${runUid}`)
}

/** 会话内业务任务列表（右侧"相关任务"面板） */
export interface ConversationBusinessTaskListResponse {
  conversation_uid: string
  active_business_task_uid: string | null
  total: number
  items: BusinessTaskCardItem[]
}

// 查询会话内的全部业务任务
export const getConversationBusinessTasksApi = (conversationUid: string) => {
  return request.get<ConversationBusinessTaskListResponse>(
    `/api/v1/conversations/${conversationUid}/business-tasks`
  )
}

/**
 * 上传发票接口的返回结构（统一响应包装里的 data）。
 *
 * 只回显文件信息；最新的任务数据由后端随上传一起写入的 assistant 消息携带，
 * 因此上传成功后前端需要重新拉取消息列表来刷新任务卡片。
 */
export interface ExpenseAttachmentUploadResult {
  success: string
  uploaded_file: {
    uid?: number | string | null
    filename: string
    file_size: number
  }
}

// 上传发票（PDF/JPG/JPEG/PNG，≤10MB）：接口已迁到 conversations 路由，
// 走统一响应包装 {code,msg,data}，data 里带最新任务快照
export const uploadExpenseItemAttachmentApi = (
  conversationUid: string,
  taskUid: string,
  expenseItemUid: string,
  file: File
) => {
  const form = new FormData()
  form.append('file', file)
  return request.post<ExpenseAttachmentUploadResult>(
    `/api/v1/conversations/${conversationUid}/${taskUid}/expense-items/${expenseItemUid}/attachments`,
    form
  )
}

/**
 * 构造指定工作流的 SSE 订阅地址。
 * 集中定义路径，避免 URL 散落在页面组件中。
 */
export function getWorkflowEventsPath(conversationUid: string, runUid: string): string {
  return `/api/v1/conversations/${encodeURIComponent(conversationUid)}/runs/${encodeURIComponent(runUid)}/events`
}

export interface WorkflowStreamHandlers {
  /** 收到一条 SSE 事件；data 为 JSON 解析结果，解析失败时为 null */
  onEvent: (name: string, data: WorkflowEvent | null) => void
  /** 连接异常（网络中断、HTTP 错误等）。注意：不代表工作流失败 */
  onError?: (error: unknown) => void
  /** 服务端正常结束响应流 */
  onClose?: () => void
}

/**
 * 订阅工作流进度 SSE。
 *
 * 后端 SSE 依赖 Authorization 请求头，浏览器原生 EventSource 不支持自定义头，
 * 因此复用 knowledge 模块已有的 fetch + ReadableStream 方式（不把 token 放入 URL）。
 */
export function watchWorkflowEvents(
  conversationUid: string,
  runUid: string,
  handlers: WorkflowStreamHandlers
) {
  const controller = new AbortController()
  const token = localStorage.getItem('token')
  const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
  const url = `${baseUrl}${getWorkflowEventsPath(conversationUid, runUid)}`
  let finished = false

  // ===== 静默中断看门狗 =====
  // 后端每 15s 发送一次 ": ping" 心跳；若超过 45s 没有收到任何字节，
  // 视为连接已静默死亡（read() 会永远挂起、不触发 onClose/onError），主动断开重连。
  const STALL_TIMEOUT_MS = 45000
  const WATCHDOG_TICK_MS = 15000
  let lastActivityAt = Date.now()
  let stalled = false
  const watchdog = setInterval(() => {
    if (Date.now() - lastActivityAt > STALL_TIMEOUT_MS) {
      stalled = true
      controller.abort()
    }
  }, WATCHDOG_TICK_MS)
  const clearWatchdog = () => clearInterval(watchdog)

  const parseFrame = (frame: string): { name: string; data: WorkflowEvent | null } | null => {
    let name = 'message'
    const dataLines: string[] = []
    for (const line of frame.split('\n')) {
      // 空行与 ": ping" 心跳注释直接忽略
      if (!line || line.startsWith(':')) continue
      if (line.startsWith('event:')) {
        name = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart())
      }
    }
    if (dataLines.length === 0) return null
    try {
      return { name, data: JSON.parse(dataLines.join('\n')) as WorkflowEvent }
    } catch {
      // 非法 JSON 只上报事件名，交由上层忽略
      return { name, data: null }
    }
  }

  const run = async () => {
    try {
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        signal: controller.signal
      })
      if (!response.ok || !response.body) {
        throw new Error(`工作流进度连接失败（${response.status}）`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        lastActivityAt = Date.now()
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        // 最后一段可能不完整，留到下一轮拼接
        buffer = frames.pop() ?? ''
        for (const frame of frames) {
          const parsed = parseFrame(frame)
          if (parsed) handlers.onEvent(parsed.name, parsed.data)
        }
      }

      clearWatchdog()
      if (!finished) {
        finished = true
        handlers.onClose?.()
      }
    } catch (error) {
      clearWatchdog()
      // 外部主动 abort（切换会话/终态收尾）不算异常
      if (controller.signal.aborted && !stalled) return
      if (!finished) {
        finished = true
        handlers.onError?.(error)
      }
    }
  }

  void run()

  return {
    abort: () => {
      clearWatchdog()
      finished = true
      controller.abort()
    }
  }
}
