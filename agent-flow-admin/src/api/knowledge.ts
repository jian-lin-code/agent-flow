import request from './request'

/** 知识库类型：企业共享 / 私有 */
export type KnowledgeBaseVisibility = 'shared' | 'private'

/** 当前用户对知识库的有效权限：read 只读 / manage 完全管理 */
export type KnowledgeBasePermission = 'read' | 'manage'

export interface KnowledgeBaseDto {
  uid: string
  name: string
  description: string | null
  created_by: string | null
  created_at: string
  updated_at: string
  /** 知识库类型（后端下发，缺省按 private 处理） */
  visibility?: KnowledgeBaseVisibility | null
  /** 当前用户对该知识库的有效权限（后端计算，缺省视为无管理权） */
  permission?: KnowledgeBasePermission | null
  /** 知识检索调用频次（后端下发，可能缺省） */
  retrieval_count?: number
}

/** 知识库统计信息（删除等高危操作前的数据盘点） */
export interface KnowledgeBaseStats {
  uid: string
  name: string
  /** 包含文档数 */
  document_count: number
  /** 向量切片总数 */
  chunk_count: number
  /** 知识检索调用频次 */
  retrieval_count: number
  /** 文档物理占用（字节） */
  storage_bytes: number
}

/** 是否可管理知识库（上传/编辑/删除）；后端仍会二次校验 */
export const canManageKb = (kb?: { permission?: KnowledgeBasePermission | null } | null) =>
  kb?.permission === 'manage'

/** 是否只读（有 read 无 manage） */
export const isReadOnlyKb = (kb?: { permission?: KnowledgeBasePermission | null } | null) =>
  kb?.permission === 'read'

export interface KnowledgeBaseListDto {
  items: KnowledgeBaseDto[]
  total: number
}

/** 单条知识库授权记录 */
export interface KnowledgePermissionItem {
  user_uid: string
  username: string
  nickname: string | null
  role: string
  /** read 只读 / manage 可管理 */
  permission: KnowledgeBasePermission
  /** 授权操作人显示名 */
  granted_by: string | null
  created_at: string
}

export interface KnowledgePermissionListDto {
  items: KnowledgePermissionItem[]
  total: number
}

/** 可被授权的用户候选项 */
export interface KnowledgeUserCandidate {
  uid: string
  username: string
  nickname: string | null
  role: string
}

export interface KnowledgeBasePayload {
  name: string
  description: string
  /** 仅创建时使用：private 受限空间（默认）/ shared 公开空间（全员可读） */
  visibility?: 'shared' | 'private'
}

export type DocumentStatus = 'pending' | 'parsing' | 'chunking' | 'embedding' | 'processing' | 'indexed' | 'failed'

/** 文档处理日志（后端持久化，进入页面时展示历史日志） */
export interface DocumentProcessLog {
  document_uid: string
  time: string
  message: string
  /** 所属阶段，前端据此把日志分组展示 */
  stage?: string | null
  /** info / success / warn / error */
  level?: string | null
}

export interface DocumentDto {
  uid: string
  /** 所属知识库的对外唯一标识（用于跳转） */
  knowledge_base_uid: string | null
  title: string
  /** 前端可访问的文件直链（docx 解析后指向 MinerU 生成的 md，用于预览） */
  access_url: string | null
  /** 源文件直链（下载原文件用） */
  source_url?: string | null
  storage_path: string | null
  content_type: string | null
  file_size: number | null
  status: DocumentStatus
  error_message: string | null
  created_by: string | null
  created_at: string
  updated_at: string
  /** 后端部分响应可能不下发这两个字段，做可选处理 */
  chunk_count?: number
  vectorized_count?: number
  /** 完整处理日志（JSONB 持久化），可能不下发 */
  process_logs?: DocumentProcessLog[] | null
  /** 各阶段完成记录，如 [{ stage: 'pending', finished_at: '2026-10-26 21:10' }]，可能不下发 */
  stage_records?: DocumentStageRecord[] | null
}

export interface DocumentChunkDto {
  id: number
  chunk_index: number
  content: string
  has_embedding: boolean
  extra_meta: Record<string, unknown> | null
  created_at: string
}

export interface DocumentListDto {
  items: DocumentDto[]
  total: number
}

/** SSE 处理进度事件中的阶段记录，如 { stage: 'pending', finished_at: '2026-10-26 19:40:00' } */
export interface DocumentStageRecord {
  stage: string
  finished_at?: string | null
}

export interface DocumentProgressEvent {
  document_uid: string
  /** 后端产生该条日志的时间 */
  timestamp?: string | null
  status: DocumentStatus | null
  /** 当前阶段（与 status 一致），用于日志分组 */
  stage?: string | null
  /** 当前阶段进度 0-100，未知为 null */
  progress?: number | null
  /** info / success / warn / error */
  level?: string | null
  message: string
  chunk_count?: number
  vectorized_count?: number
  stage_records?: DocumentStageRecord[] | null
}

/** 文档在线预览内容：docx 走服务端转 HTML，pdf 给直链，md/txt 给文本 */
export type DocumentPreviewDto =
  | { kind: 'html'; html: string }
  | { kind: 'markdown'; content: string }
  | { kind: 'pdf'; url: string | null }
  | { kind: 'none'; reason?: string }

export const getDocumentPreview = (uid: string) =>
  request.get<DocumentPreviewDto>(`/api/v1/knowledge-bases/documents/${uid}/preview`)

/** 知识库总览统计（当前用户可见范围内聚合） */
export interface KnowledgeOverview {
  kb_count: number
  total_docs: number
  indexed_docs: number
  processing_docs: number
  /** 检索调用频次合计 */
  total_retrievals: number
  kb_doc_counts: { kb_uid: string; total: number; indexed: number; processing: number }[]
  recent_documents: { uid: string; title: string; status: string; kb_name: string; created_at: string }[]
}

export const getKnowledgeOverview = () => request.get<KnowledgeOverview>('/api/v1/knowledge-bases/overview')

export const getKnowledgeBase = (uid: string) => request.get<KnowledgeBaseDto>('/api/v1/knowledge-bases/' + uid)
export const listKnowledgeBases = () => request.get<KnowledgeBaseListDto>('/api/v1/knowledge-bases', { params: { page: 1, page_size: 100 } })
export const createKnowledgeBase = (data: KnowledgeBasePayload) => request.post<KnowledgeBaseDto>('/api/v1/knowledge-bases', data)
export const updateKnowledgeBase = (uid: string, data: KnowledgeBasePayload) => request.put<KnowledgeBaseDto>(`/api/v1/knowledge-bases/${uid}`, data)
export const deleteKnowledgeBase = (uid: string) => request.delete<void>(`/api/v1/knowledge-bases/${uid}`)
/** 获取知识库统计信息（文档数/分块数/检索调用频次/物理占用） */
export const getKnowledgeBaseStats = (uid: string) => request.get<KnowledgeBaseStats>(`/api/v1/knowledge-bases/${uid}/stats`)

/** 获取知识库授权列表（仅管理者） */
export const listKbPermissions = (kbUid: string) => request.get<KnowledgePermissionListDto>(`/api/v1/knowledge-bases/${kbUid}/permissions`)
/** 按账号 / 昵称搜索可授权用户（仅管理者） */
export const searchKbPermissionCandidates = (kbUid: string, keyword?: string) =>
  request.get<KnowledgeUserCandidate[]>(`/api/v1/knowledge-bases/${kbUid}/permissions/candidates`, { params: { keyword: keyword || undefined } })
/** 按账号 / 昵称搜索可授权用户（创建知识库时预选成员，尚无 kbUid） */
export const searchGrantableUsers = (keyword?: string) =>
  request.get<KnowledgeUserCandidate[]>('/api/v1/knowledge-bases/users/search', { params: { keyword: keyword || undefined } })
/** 添加授权：已存在授权时后端会更新权限级别 */
export const grantKbPermission = (kbUid: string, data: { user_uid: string; permission: KnowledgeBasePermission }) =>
  request.post<KnowledgePermissionItem>(`/api/v1/knowledge-bases/${kbUid}/permissions`, data)
/** 撤销授权 */
export const revokeKbPermission = (kbUid: string, userUid: string) =>
  request.delete<void>(`/api/v1/knowledge-bases/${kbUid}/permissions/${userUid}`)
export const listDocuments = (kbUid: string) => request.get<DocumentListDto>(`/api/v1/knowledge-bases/${kbUid}/documents`)
export const getDocument = (documentUid: string) => request.get<DocumentDto>(`/api/v1/knowledge-bases/documents/${documentUid}`)
export const listDocumentChunks = (documentUid: string) => request.get<DocumentChunkDto[]>(`/api/v1/knowledge-bases/documents/${documentUid}/chunks`)
export const uploadDocument = (kbUid: string, file: File) => {
  const form = new FormData()
  form.append('file', file)
  return request.post<DocumentDto>(`/api/v1/knowledge-bases/${kbUid}/documents`, form)
}
export const reprocessDocument = (documentUid: string) => request.post<DocumentDto>(`/api/v1/knowledge-bases/documents/${documentUid}/reprocess`)
export const deleteDocument = (documentUid: string) => request.delete<void>(`/api/v1/knowledge-bases/documents/${documentUid}`)

/** 文档进度订阅句柄：必须显式 abort，否则连接会一直占用浏览器对该后端的并发连接数 */
export interface DocumentProgressHandle {
  abort: () => void
  /** 流自然结束（或中止）后 resolve；中止导致的异常在这里被吞掉 */
  done: Promise<void>
}

/**
 * 订阅文档处理进度（SSE）。
 *
 * 注意：浏览器对同一 origin 的并发连接数有限（HTTP/1.1 为 6），
 * 因此离开页面 / 切换文档时**必须**调用返回句柄的 abort()，
 * 否则残留连接会占满配额，导致后续所有接口请求排队等待（表现为页面切换卡死）。
 */
export function watchDocumentProgress(
  documentUid: string,
  onEvent: (event: DocumentProgressEvent) => void
): DocumentProgressHandle {
  const controller = new AbortController()
  const token = localStorage.getItem('token')

  const done = (async () => {
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/v1/knowledge-bases/documents/${documentUid}/progress`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      signal: controller.signal
    })
    if (!response.ok || !response.body) throw new Error('无法建立文档处理进度连接')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done: streamDone, value } = await reader.read()
      if (streamDone) break
      buffer += decoder.decode(value, { stream: true })
      const messages = buffer.split('\n\n')
      buffer = messages.pop() || ''
      for (const message of messages) {
        const dataLine = message.split('\n').find((line) => line.startsWith('data: '))
        if (dataLine) onEvent(JSON.parse(dataLine.slice(6)) as DocumentProgressEvent)
      }
    }
  })().catch((error) => {
    // 主动 abort 属于预期行为，不作为错误抛出
    if (controller.signal.aborted) return
    throw error
  })

  return {
    abort: () => controller.abort(),
    done
  }
}
