import { computed, reactive } from 'vue'

export type KbStatus = 'normal' | 'disabled'
export type DocStatus = 'indexed' | 'processing' | 'failed' | 'uploaded'
export type DocType = 'PDF' | 'Word' | 'MD'

export interface KnowledgeBase {
  id: string
  name: string
  description: string
  creator: string
  createdAt: string
  updatedAt: string
  status: KbStatus
}

export interface KnowledgeDoc {
  id: string
  kbId: string
  name: string
  type: DocType
  size: string
  status: DocStatus
  creator: string
  uploadedAt: string
  updatedAt: string
  pages: number
  mimeType: string
  storagePath: string
  chunkCount: number
  vectorizedCount: number
  vectorDim: number
  embeddingModel: string
  errorInfo: string
  summary: string
  description: string
}

export interface ProcessStep {
  title: string
  time: string
  done: boolean
}

export interface DocChunk {
  id: string
  index: number
  content: string
  tokens: number
  vectorized: boolean
}

export interface Citation {
  id: string
  title: string
  location: string
  snippet: string
}

const knowledgeBases = reactive<KnowledgeBase[]>([
  {
    id: 'kb-1',
    name: '差旅报销制度',
    description: '包含差旅报销办法、相关标准等文档',
    creator: '张三',
    createdAt: '2025-10-10 08:12',
    updatedAt: '2025-10-15 16:20',
    status: 'normal'
  },
  {
    id: 'kb-2',
    name: '人力资源知识库',
    description: '包含员工手册、考勤制度等',
    creator: '李四',
    createdAt: '2025-09-22 14:30',
    updatedAt: '2025-10-12 11:05',
    status: 'normal'
  },
  {
    id: 'kb-3',
    name: '产品知识库',
    description: '包含产品介绍、技术文档等',
    creator: '王五',
    createdAt: '2025-09-15 10:20',
    updatedAt: '2025-10-10 09:30',
    status: 'normal'
  },
  {
    id: 'kb-4',
    name: '财务知识库',
    description: '包含报销政策、财务流程等',
    creator: '李四',
    createdAt: '2025-08-30 16:45',
    updatedAt: '2025-10-08 14:12',
    status: 'normal'
  },
  {
    id: 'kb-5',
    name: '公司规章制度',
    description: '包含公司各项规章制度',
    creator: '王五',
    createdAt: '2025-08-20 11:30',
    updatedAt: '2025-09-28 17:40',
    status: 'normal'
  }
])

const documents = reactive<KnowledgeDoc[]>([
  {
    id: 'doc-1',
    kbId: 'kb-1',
    name: '差旅报销管理办法.pdf',
    type: 'PDF',
    size: '245 KB',
    status: 'indexed',
    creator: '张三',
    uploadedAt: '2025-10-10 10:23',
    updatedAt: '2025-10-10 16:45',
    pages: 12,
    mimeType: 'application/pdf',
    storagePath: 'uploads/knowledge/2025/10/xxx.pdf',
    chunkCount: 42,
    vectorizedCount: 42,
    vectorDim: 1536,
    embeddingModel: 'text-embedding-3-small',
    errorInfo: '无',
    summary:
      '该文档主要规定了云帆科技有限公司的差旅报销管理办法，涵盖差旅报销范围、标准、流程、时限，禁止报销事项及违规处理等内容。适用于公司全体员工因公出差期间由出差费用报销，旨在规范报销行为，合理控制差旅成本。',
    description: '云帆科技有限公司差旅报销管理的相关制度和规定，包括报销范围、标准、流程及注意事项。'
  },
  {
    id: 'doc-2',
    kbId: 'kb-1',
    name: '员工出差标准.docx',
    type: 'Word',
    size: '320 KB',
    status: 'indexed',
    creator: '张三',
    uploadedAt: '2025-10-11 14:36',
    updatedAt: '2025-10-11 15:02',
    pages: 8,
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    storagePath: 'uploads/knowledge/2025/10/travel-standard.docx',
    chunkCount: 28,
    vectorizedCount: 28,
    vectorDim: 1536,
    embeddingModel: 'text-embedding-3-small',
    errorInfo: '无',
    summary: '明确不同职级员工出差交通、住宿、伙食补助标准，以及特殊情况审批规则。',
    description: '员工出差交通、住宿及补助标准说明。'
  },
  {
    id: 'doc-3',
    kbId: 'kb-1',
    name: '报销流程说明.pdf',
    type: 'PDF',
    size: '186 KB',
    status: 'indexed',
    creator: '李四',
    uploadedAt: '2025-10-12 09:15',
    updatedAt: '2025-10-12 09:40',
    pages: 6,
    mimeType: 'application/pdf',
    storagePath: 'uploads/knowledge/2025/10/reimburse-flow.pdf',
    chunkCount: 18,
    vectorizedCount: 18,
    vectorDim: 1536,
    embeddingModel: 'text-embedding-3-small',
    errorInfo: '无',
    summary: '介绍报销单据提交、审批节点、财务复核及打款时限。',
    description: '报销申请从提交到付款的完整流程说明。'
  },
  {
    id: 'doc-4',
    kbId: 'kb-2',
    name: '员工手册.pdf',
    type: 'PDF',
    size: '1.2 MB',
    status: 'indexed',
    creator: '李四',
    uploadedAt: '2025-09-22 16:10',
    updatedAt: '2025-09-22 17:01',
    pages: 36,
    mimeType: 'application/pdf',
    storagePath: 'uploads/knowledge/2025/09/handbook.pdf',
    chunkCount: 96,
    vectorizedCount: 96,
    vectorDim: 1536,
    embeddingModel: 'text-embedding-3-small',
    errorInfo: '无',
    summary: '公司员工入职、考勤、休假、奖惩等综合制度汇编。',
    description: '人力资源核心制度文件。'
  },
  {
    id: 'doc-5',
    kbId: 'kb-2',
    name: '考勤管理办法.docx',
    type: 'Word',
    size: '210 KB',
    status: 'processing',
    creator: '李四',
    uploadedAt: '2025-10-12 10:40',
    updatedAt: '2025-10-12 10:41',
    pages: 5,
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    storagePath: 'uploads/knowledge/2025/10/attendance.docx',
    chunkCount: 12,
    vectorizedCount: 0,
    vectorDim: 1536,
    embeddingModel: 'text-embedding-3-small',
    errorInfo: '无',
    summary: '正在解析考勤打卡、请假与加班规则。',
    description: '考勤打卡与请假规则。'
  },
  {
    id: 'doc-6',
    kbId: 'kb-4',
    name: '发票合规指引.pdf',
    type: 'PDF',
    size: '540 KB',
    status: 'processing',
    creator: '王五',
    uploadedAt: '2025-10-08 11:20',
    updatedAt: '2025-10-08 11:22',
    pages: 10,
    mimeType: 'application/pdf',
    storagePath: 'uploads/knowledge/2025/10/invoice.pdf',
    chunkCount: 20,
    vectorizedCount: 8,
    vectorDim: 1536,
    embeddingModel: 'text-embedding-3-small',
    errorInfo: '无',
    summary: '正在向量化发票验真、抬头与税率相关条款。',
    description: '发票开具与合规审核指引。'
  }
])

function padDocsForStats() {
  const extra: KnowledgeDoc[] = []
  const fillers: Array<[string, number, string]> = [
    ['kb-2', 3, '人事'],
    ['kb-3', 8, '产品'],
    ['kb-4', 3, '财务'],
    ['kb-5', 3, '规章']
  ]
  let i = 100
  for (const [kbId, count, prefix] of fillers) {
    for (let n = 0; n < count; n += 1) {
      i += 1
      extra.push({
        id: `doc-${i}`,
        kbId,
        name: `${prefix}文档${n + 1}.pdf`,
        type: 'PDF',
        size: `${180 + n * 12} KB`,
        status: 'indexed',
        creator: n % 2 === 0 ? '王五' : '李四',
        uploadedAt: '2025-09-18 10:00',
        updatedAt: '2025-09-18 10:20',
        pages: 4 + n,
        mimeType: 'application/pdf',
        storagePath: `uploads/knowledge/2025/09/${kbId}-${n}.pdf`,
        chunkCount: 10 + n,
        vectorizedCount: 10 + n,
        vectorDim: 1536,
        embeddingModel: 'text-embedding-3-small',
        errorInfo: '无',
        summary: `${prefix}相关制度说明文档。`,
        description: `${prefix}补充材料。`
      })
    }
  }
  documents.push(...extra)
}

padDocsForStats()

export const kbStatusLabel: Record<KbStatus, string> = {
  normal: '正常',
  disabled: '已停用'
}

export const docStatusLabel: Record<DocStatus, string> = {
  indexed: '已索引',
  processing: '处理中',
  failed: '失败',
  uploaded: '已上传'
}

export function getKbById(id: string) {
  return knowledgeBases.find((item) => item.id === id)
}

export function getDocsByKb(kbId: string) {
  return documents.filter((item) => item.kbId === kbId)
}

export function getDocById(id: string) {
  return documents.find((item) => item.id === id)
}

export function kbDocStats(kbId: string) {
  const list = getDocsByKb(kbId)
  return {
    total: list.length,
    indexed: list.filter((d) => d.status === 'indexed').length,
    processing: list.filter((d) => d.status === 'processing').length
  }
}

export const kbOverview = computed(() => {
  const totalDocs = documents.length
  const indexed = documents.filter((d) => d.status === 'indexed').length
  const processing = documents.filter((d) => d.status === 'processing').length
  return {
    kbCount: knowledgeBases.length,
    totalDocs,
    indexed,
    processing
  }
})

export function createKnowledgeBase(payload: { name: string; description: string; creator: string }) {
  const now = formatNow()
  const item: KnowledgeBase = {
    id: `kb-${Date.now()}`,
    name: payload.name,
    description: payload.description,
    creator: payload.creator,
    createdAt: now,
    updatedAt: now,
    status: 'normal'
  }
  knowledgeBases.unshift(item)
  return item
}

export function updateKnowledgeBase(id: string, payload: { name: string; description: string }) {
  const item = getKbById(id)
  if (!item) return
  item.name = payload.name
  item.description = payload.description
  item.updatedAt = formatNow()
}

export function removeKnowledgeBase(id: string) {
  const idx = knowledgeBases.findIndex((item) => item.id === id)
  if (idx >= 0) knowledgeBases.splice(idx, 1)
  for (let i = documents.length - 1; i >= 0; i -= 1) {
    if (documents[i].kbId === id) documents.splice(i, 1)
  }
}

export function addDocument(kbId: string, payload: { name: string; type: DocType; size: string; creator: string }) {
  const now = formatNow()
  const item: KnowledgeDoc = {
    id: `doc-${Date.now()}`,
    kbId,
    name: payload.name,
    type: payload.type,
    size: payload.size,
    status: 'processing',
    creator: payload.creator,
    uploadedAt: now,
    updatedAt: now,
    pages: 1,
    mimeType: payload.type === 'PDF' ? 'application/pdf' : 'application/msword',
    storagePath: `uploads/knowledge/2025/10/${payload.name}`,
    chunkCount: 0,
    vectorizedCount: 0,
    vectorDim: 1536,
    embeddingModel: 'text-embedding-3-small',
    errorInfo: '无',
    summary: '文档已上传，正在排队处理。',
    description: '新上传文档'
  }
  documents.unshift(item)
  const kb = getKbById(kbId)
  if (kb) kb.updatedAt = now
  return item
}

export function removeDocument(id: string) {
  const idx = documents.findIndex((item) => item.id === id)
  if (idx >= 0) documents.splice(idx, 1)
}

export function reprocessDocument(id: string) {
  const doc = getDocById(id)
  if (!doc) return
  doc.status = 'processing'
  doc.updatedAt = formatNow()
  doc.vectorizedCount = 0
}

export function getProcessSteps(doc: KnowledgeDoc): ProcessStep[] {
  if (doc.status === 'processing') {
    return [
      { title: '文件上传', time: doc.uploadedAt, done: true },
      { title: '解析完成', time: doc.uploadedAt, done: true },
      { title: '分块完成', time: '', done: false },
      { title: '向量化完成', time: '', done: false }
    ]
  }
  return [
    { title: '文件上传', time: '2025-10-10 10:23', done: true },
    { title: '解析完成', time: '2025-10-10 10:25', done: true },
    { title: '分块完成', time: '2025-10-10 10:32', done: true },
    { title: '向量化完成', time: '2025-10-10 10:40', done: true }
  ]
}

export function getProcessPipeline(doc: KnowledgeDoc) {
  const indexed = doc.status === 'indexed'
  return [
    { title: '已上传', time: '10-10 10:23', done: true },
    { title: '解析中', time: '10-10 10:25', done: true },
    { title: '分块完成', time: '10-10 10:32', done: true },
    { title: '向量化完成', time: indexed ? '10-10 10:40' : '', done: indexed },
    { title: '已索引', time: indexed ? '10-10 11:05' : '', done: indexed }
  ]
}

export function getChunks(doc: KnowledgeDoc): DocChunk[] {
  const samples = [
    '第一章 总则 第一条 为规范公司差旅报销管理，明确报销标准和流程，合理控制差旅费用，根据国家相关法律法规及公司实际情况，特制定本办法。',
    '第二条 本办法适用于公司全体员工因公出差发生的交通费、住宿费、伙食补助费、市内交通费等费用的报销管理。',
    '第三条 报销范围：1. 因公出差期间发生的城市间交通费；2. 出差期间的住宿费；3. 伙食补助费；4. 市内交通费；5. 其他与公务活动相关的合理费用。',
    '第四条 报销原则：1. 真实、合法、合规原则；2. 节约、有效、合理原则；3. 先审批后发生，先报销后付款原则。',
    '交通费标准：飞机经济舱、高铁二等座为默认标准；总监及以上职级经审批可乘坐商务舱或一等座。',
    '住宿标准按职级与城市档位执行，一线城市普通员工上限 500 元/晚，超出部分需专项审批。',
    '伙食补助按自然日发放，不与招待费重复报销。出差当日往返按半天计算。',
    '禁止报销事项包括：旅游景点门票、个人消费、酒水、违规超标部分及无合法票据的费用。'
  ]
  const count = Math.min(doc.chunkCount || samples.length, 12)
  return Array.from({ length: count }, (_, index) => ({
    id: `${doc.id}-chunk-${index + 1}`,
    index: index + 1,
    content: samples[index % samples.length],
    tokens: 180 + index * 12,
    vectorized: doc.status === 'indexed' || index < doc.vectorizedCount
  }))
}

export function getCitations(doc: KnowledgeDoc): Citation[] {
  if (doc.id !== 'doc-1') {
    return [
      {
        id: 'c-1',
        title: doc.name,
        location: '第 1 页',
        snippet: doc.summary
      }
    ]
  }
  return [
    {
      id: 'c-1',
      title: '差旅报销管理办法.pdf',
      location: '第 1 页 · 第一条',
      snippet: '为规范公司差旅报销管理，明确报销标准和流程，合理控制差旅费用。'
    },
    {
      id: 'c-2',
      title: '差旅报销管理办法.pdf',
      location: '第 1 页 · 第三条',
      snippet: '报销范围包括城市间交通费、住宿费、伙食补助费及市内交通费。'
    },
    {
      id: 'c-3',
      title: '员工出差标准.docx',
      location: '第 2 页',
      snippet: '一线城市普通员工住宿上限 500 元/晚。'
    }
  ]
}

function formatNow() {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export { knowledgeBases, documents }
