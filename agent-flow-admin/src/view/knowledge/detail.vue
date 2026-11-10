<template>
  <div class="kb-detail" v-if="kb">
    <el-button class="back-btn" text @click="router.push('/kb-manage')">
      <el-icon><ArrowLeft /></el-icon>
      {{ $t('kb.back') }}
    </el-button>

    <div class="page-card">
      <div class="kb-hero">
        <div class="hero-left">
          <div class="kb-icon"><el-icon><Collection /></el-icon></div>
          <div class="hero-info">
            <div class="hero-title">
              <span>{{ kb.name }}</span>
              <el-tag type="success" effect="light" round>{{ $t('kb.normal') }}</el-tag>
              <el-tag :type="kb.visibility === 'shared' ? 'info' : 'warning'" effect="plain" round>
                {{ kb.visibility === 'shared' ? $t('kb.typeShared') : $t('kb.typePrivate') }}
              </el-tag>
              <el-tag v-if="!canManage" type="info" effect="light" round>{{ $t('kb.readOnly') }}</el-tag>
            </div>
            <p class="hero-desc">{{ kb.description }}</p>
            <div class="hero-meta">
              {{ $t('kb.colCreator') }}：{{ kb.creator }}
              <span>{{ $t('kb.colCreatedAt') }}：{{ kb.createdAt }}</span>
              <span>{{ $t('kb.colUpdatedAt') }}：{{ kb.updatedAt }}</span>
            </div>
          </div>
        </div>
        <div class="hero-right">
          <div class="mini-stats">
            <div class="mini-stat">
              <div class="mini-icon blue"><el-icon><Document /></el-icon></div>
              <div>
                <div class="mini-label">{{ $t('kb.colDocCount') }}</div>
                <div class="mini-value">{{ stats.total }}</div>
              </div>
            </div>
            <div class="mini-stat">
              <div class="mini-icon green"><el-icon><CircleCheck /></el-icon></div>
              <div>
                <div class="mini-label">{{ $t('kb.statIndexed') }}</div>
                <div class="mini-value">{{ stats.indexed }}</div>
              </div>
            </div>
            <div class="mini-stat">
              <div class="mini-icon orange"><el-icon><Loading /></el-icon></div>
              <div>
                <div class="mini-label">{{ $t('kb.statProcessing') }}</div>
                <div class="mini-value">{{ stats.processing }}</div>
              </div>
            </div>
          </div>
          <div v-if="canManage" class="hero-actions">
            <el-button @click="permissionVisible = true">{{ $t('kb.permMenu') }}</el-button>
            <el-button @click="openEdit">{{ $t('common.edit') }}</el-button>
            <el-button type="danger" plain @click="handleDeleteKb">{{ $t('common.del') }}</el-button>
          </div>
        </div>
      </div>

      <el-tabs v-model="activeTab">
        <el-tab-pane :label="$t('kb.tabDocs')" name="docs">
          <div class="toolbar">
            <el-input
              v-model="keyword"
              :placeholder="$t('kb.searchDocs')"
              clearable
              :prefix-icon="Search"
              class="search-input"
            />
            <el-select v-model="statusFilter" :placeholder="$t('kb.allStatus')" clearable style="width: 140px">
              <el-option :label="$t('kb.stIndexed')" value="indexed" />
              <el-option :label="$t('kb.stProcessing')" value="processing" />
              <el-option :label="$t('kb.stFailed')" value="failed" />
            </el-select>
            <el-select v-model="typeFilter" :placeholder="$t('kb.allTypes')" clearable style="width: 140px">
              <el-option label="PDF" value="PDF" />
              <el-option label="Word" value="Word" />
              <el-option label="MD" value="MD" />
            </el-select>
            <el-button v-if="canManage" type="primary" class="upload-btn" @click="uploadVisible = true">
              <el-icon><Upload /></el-icon>
              {{ $t('kb.uploadDoc') }}
            </el-button>
          </div>

          <!-- PC 表格 -->
          <el-table :data="filteredDocs" class="doc-table">
            <el-table-column :label="$t('kb.colDocName')" min-width="240">
              <template #default="{ row }">
                <div class="name-cell" @click="goDoc(row.id)">
                  <div class="file-icon" :class="row.type === 'PDF' ? 'pdf' : row.type === 'MD' ? 'md' : 'word'">
                    {{ row.type }}
                  </div>
                  <span>{{ row.name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="type" :label="$t('doc.metaType')" width="110" />
            <el-table-column prop="size" :label="$t('doc.metaSize')" width="100" />
            <el-table-column :label="$t('common.status')" width="110">
              <template #default="{ row }">
                <el-tag :type="statusType(row.status)" effect="light" round>
                  {{ getDocStatusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="creator" :label="$t('kb.colCreator')" width="100" />
            <el-table-column prop="uploadedAt" :label="$t('kb.colUploadTime')" width="170" />
            <el-table-column :label="$t('common.actions')" width="160" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="goDoc(row.id)">{{ $t('kb.view') }}</el-button>
                <el-button link type="primary" @click="goDoc(row.id)">{{ $t('kb.detail') }}</el-button>
                <el-dropdown
                  v-if="canManage"
                  trigger="click"
                  @command="(cmd: string) => handleDocMore(cmd, row)"
                >
                  <el-button link type="primary"><el-icon><MoreFilled /></el-icon></el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="reprocess">{{ $t('doc.reprocess') }}</el-dropdown-item>
                      <el-dropdown-item command="delete" divided>{{ $t('common.del') }}</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </template>
            </el-table-column>
          </el-table>

          <!-- 移动端卡片列表 -->
          <div class="mobile-doc-list">
            <div class="doc-card" v-for="row in filteredDocs" :key="row.id" @click="goDoc(row.id)">
              <div class="doc-card-head">
                <div class="file-icon" :class="row.type === 'PDF' ? 'pdf' : row.type === 'MD' ? 'md' : 'word'">{{ row.type }}</div>
                <div class="doc-card-info">
                  <div class="doc-card-name">{{ row.name }}</div>
                  <div class="doc-card-meta">{{ row.size }} · {{ row.creator }}</div>
                </div>
                <el-tag :type="statusType(row.status)" effect="light" round size="small">
                  {{ getDocStatusLabel(row.status) }}
                </el-tag>
              </div>
              <div class="doc-card-foot">
                <span class="doc-card-time">{{ row.uploadedAt }}</span>
                <div class="doc-card-ops">
                  <span class="op-link" @click.stop="goDoc(row.id)">{{ $t('kb.view') }}</span>
                  <template v-if="canManage">
                    <span class="op-link" @click.stop="handleDocMore('reprocess', row)">{{ $t('doc.reprocess') }}</span>
                    <span class="op-link danger" @click.stop="handleDocMore('delete', row)">{{ $t('common.del') }}</span>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane :label="$t('doc.tabInfo')" name="info">
          <el-descriptions :column="2" border>
            <el-descriptions-item :label="$t('kb.labelName')">{{ kb.name }}</el-descriptions-item>
            <el-descriptions-item :label="$t('common.status')">{{ $t('kb.normal') }}</el-descriptions-item>
            <el-descriptions-item :label="$t('kb.colCreator')">{{ kb.creator }}</el-descriptions-item>
            <el-descriptions-item :label="$t('kb.colDocCount')">{{ stats.total }}</el-descriptions-item>
            <el-descriptions-item :label="$t('kb.colCreatedAt')">{{ kb.createdAt }}</el-descriptions-item>
            <el-descriptions-item :label="$t('kb.colUpdatedAt')">{{ kb.updatedAt }}</el-descriptions-item>
            <el-descriptions-item :label="$t('kb.labelDesc')" :span="2">{{ kb.description }}</el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="editVisible" :title="$t('kb.editKb')" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item :label="$t('kb.labelName')" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item :label="$t('kb.labelDesc')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitEdit">{{ $t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="uploadVisible" :title="$t('kb.uploadTitle')" width="480px">
      <el-upload drag :auto-upload="false" :show-file-list="true" :on-change="onFileChange" accept=".pdf,.doc,.docx,.md">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">{{ $t('kb.dropHere') }}<em>{{ $t('kb.clickUpload') }}</em></div>
        <template #tip>
          <div class="el-upload__tip">{{ $t('kb.uploadTip') }}</div>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="uploadVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :disabled="!pendingFile" @click="confirmUpload">{{ $t('kb.startUpload') }}</el-button>
      </template>
    </el-dialog>

    <PermissionDialog
      v-model="permissionVisible"
      :kb-uid="kb.uid"
      :kb-name="kb.name"
      :visibility="kb.visibility"
    />

    <!-- 删除知识库 / 删除文档：与列表页共用的高危确认弹窗（全真实数据） -->
    <DeleteKbDialog v-model="deleteKbVisible" :kb="kb" @deleted="onKbDeleted" />
    <DeleteDocDialog v-model="deleteDocVisible" :doc="deleteDocRaw" :chunk-count="deleteDocRaw?.chunk_count ?? 0" @deleted="onDocDeleted" />
  </div>
  <el-empty v-else :description="loadError || $t('kb.kbNotExist')">
    <el-button type="primary" @click="router.push('/kb-manage')">{{ $t('kb.back') }}</el-button>
  </el-empty>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance, type FormRules, type UploadFile } from 'element-plus'
import { ArrowLeft, Collection, Document, CircleCheck, Loading, Search, Upload, MoreFilled, UploadFilled } from '@element-plus/icons-vue'
import { getKnowledgeBase, listDocuments, reprocessDocument, updateKnowledgeBase, uploadDocument, watchDocumentProgress, type DocumentProgressHandle, type DocumentDto, type KnowledgeBaseDto } from '@/api/knowledge'
import type { KnowledgeDoc, DocStatus } from '@/mock/knowledge'
import PermissionDialog from './PermissionDialog.vue'
import DeleteKbDialog from './DeleteKbDialog.vue'
import DeleteDocDialog from './DeleteDocDialog.vue'

const { t } = useI18n()

// 后端文档状态 → 前端列表展示状态（列表只区分 已索引/处理中/失败/已上传）
const toListStatus = (status: string): DocStatus => {
  if (status === 'pending') return 'uploaded'
  if (['processing', 'parsing', 'chunking', 'embedding'].includes(status)) return 'processing'
  if (status === 'indexed') return 'indexed'
  return 'failed'
}

interface KnowledgeBaseView { uid: string; name: string; description: string; creator: string; createdAt: string; updatedAt: string; status: 'normal'; visibility: 'shared' | 'private'; permission: 'read' | 'manage' | null }
const route = useRoute()
const router = useRouter()
const kbId = computed(() => String(route.params.kbId || ''))
const kb = ref<KnowledgeBaseView | null>(null)
const docs = ref<KnowledgeDoc[]>([])
const activeTab = ref('docs')
const keyword = ref('')
const statusFilter = ref('')
const typeFilter = ref('')
const editVisible = ref(false)
const uploadVisible = ref(false)
const permissionVisible = ref(false)
const pendingFile = ref<UploadFile | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({ name: '', description: '' })
const rules = computed<FormRules>(() => ({ name: [{ required: true, message: t('kb.phName'), trigger: 'blur' }] }))
const formatDate = (value: string) => value ? value.replace('T', ' ').slice(0, 16) : '-'
const formatSize = (value: number | null) => value == null ? '-' : value < 1024 * 1024 ? `${Math.max(1, Math.round(value / 1024))} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
const typeOf = (title: string) => {
  const ext = title.toLowerCase().split('.').pop() || ''
  if (ext === 'pdf') return 'PDF'
  if (ext === 'md') return 'MD'
  return 'Word'
}
const toKb = (item: KnowledgeBaseDto): KnowledgeBaseView => ({ uid: item.uid, name: item.name, description: item.description || '-', creator: item.created_by || '-', createdAt: formatDate(item.created_at), updatedAt: formatDate(item.updated_at), status: 'normal', visibility: item.visibility === 'shared' ? 'shared' : 'private', permission: item.permission ?? null })
/** 只有 manage 权限才能编辑/删除知识库、上传/重处理/删除文档；read 为只读 */
const canManage = computed(() => kb.value?.permission === 'manage')
const loadError = ref('')
const toDoc = (item: DocumentDto): KnowledgeDoc => ({
  id: String(item.uid), kbId: String(item.knowledge_base_uid || ''), name: item.title, type: typeOf(item.title), size: formatSize(item.file_size), status: toListStatus(item.status), creator: item.created_by || '-', uploadedAt: formatDate(item.created_at), updatedAt: formatDate(item.updated_at), pages: 1, mimeType: item.content_type || '-', storagePath: item.access_url || item.storage_path || '-', chunkCount: item.chunk_count ?? 0, vectorizedCount: item.vectorized_count ?? 0, vectorDim: 1024, embeddingModel: 'configured model', errorInfo: item.error_message || '无', summary: '', description: item.error_message || t('doc.desc')
})
/** 删除弹窗需要后端原始 DTO（标题/时间/上传者/状态），列表视图模型不含这些字段 */
const rawDocs = ref<DocumentDto[]>([])
const load = async () => {
  loadError.value = ''
  try {
    const [kbResponse, docsResponse] = await Promise.all([getKnowledgeBase(kbId.value), listDocuments(kbId.value)])
    kb.value = toKb(kbResponse.data)
    rawDocs.value = docsResponse.data.items
    docs.value = docsResponse.data.items.map(toDoc)
  } catch (error) {
    // 无权限 / 不存在等错误：后端错误信息由请求拦截器统一提示，这里只负责页面兜底
    const detail = (error as { response?: { data?: { msg?: string; detail?: string } } })?.response?.data
    loadError.value = detail?.msg || detail?.detail || t('kb.noPermission')
    kb.value = null
  }
}
const stats = computed(() => ({ total: docs.value.length, indexed: docs.value.filter((item) => item.status === 'indexed').length, processing: docs.value.filter((item) => item.status === 'processing' || item.status === 'uploaded').length }))
const filteredDocs = computed(() => docs.value.filter((item) => (!keyword.value.trim() || item.name.includes(keyword.value.trim())) && (!statusFilter.value || item.status === statusFilter.value) && (!typeFilter.value || item.type === typeFilter.value)))
const STATUS_KEYS: Record<string, string> = {
  uploaded: 'kb.docUploaded',
  processing: 'kb.stProcessing',
  indexed: 'kb.stIndexed',
  failed: 'kb.stFailed'
}
const getDocStatusLabel = (status: unknown) => {
  const key = STATUS_KEYS[String(status)]
  return key ? t(key) : t('doc.st_pending')
}
const statusType = (status: DocStatus) => status === 'indexed' ? 'success' : status === 'processing' ? 'warning' : status === 'failed' ? 'danger' : 'info'
const goDoc = (docId: string) => router.push(`/kb-manage/${kbId.value}/docs/${docId}`)
const openEdit = () => { if (kb.value) { form.name = kb.value.name; form.description = kb.value.description === '-' ? '' : kb.value.description; editVisible.value = true } }
const submitEdit = async () => { const valid = await formRef.value?.validate().catch(() => false); if (!valid || !kb.value) return; await updateKnowledgeBase(kb.value.uid, { ...form }); editVisible.value = false; await load(); ElMessage.success(t('kb.saved')) }
// ===== 删除确认弹窗（与列表页共用组件，高危二次确认） =====
const deleteKbVisible = ref(false)
const deleteDocVisible = ref(false)
const deleteDocRaw = ref<DocumentDto | null>(null)
/** 记录正在删除的文档 uid：弹窗的 deleted 事件只带知识库 uid，列表移除要用文档 uid */
const deleteDocUid = ref('')
const handleDeleteKb = () => { deleteKbVisible.value = true }
const onKbDeleted = () => { ElMessage.success(t('kb.deleted')); router.push('/kb-manage') }
const onDocDeleted = () => {
  ElMessage.success(t('kb.deleted'))
  // 文档已删除：释放其进度连接并从列表移除
  const uid = deleteDocUid.value
  progressHandles.get(uid)?.abort()
  progressHandles.delete(uid)
  rawDocs.value = rawDocs.value.filter((item) => item.uid !== uid)
  docs.value = docs.value.filter((item) => item.id !== uid)
  deleteDocUid.value = ''
  deleteDocRaw.value = null
  deleteDocVisible.value = false
}
/** 文档进度订阅句柄：按文档 uid 管理，离开页面时统一断开，防止连接泄漏 */
const progressHandles = new Map<string, DocumentProgressHandle>()
const applyProgress = (event: { document_uid: string; status: string | null; chunk_count?: number; vectorized_count?: number; message: string }) => {  const index = docs.value.findIndex((item) => item.id === event.document_uid)
  if (index < 0) return
  const item = docs.value[index]
  item.status = event.status ? toListStatus(event.status) : item.status
  item.chunkCount = event.chunk_count ?? item.chunkCount
  item.vectorizedCount = event.vectorized_count ?? item.vectorizedCount
  item.description = event.message
  if (event.status === 'failed') item.errorInfo = event.message
}
const subscribeProgress = (documentUid: string) => {
  // 同一文档重复订阅前先断开旧连接，避免连接堆积占满浏览器并发配额
  progressHandles.get(documentUid)?.abort()
  let handle: DocumentProgressHandle
  handle = watchDocumentProgress(documentUid, (event) => {
    applyProgress(event)
    // 终态后不再需要实时进度，立即释放连接
    if (event.status === 'indexed' || event.status === 'failed') {
      handle.abort()
      progressHandles.delete(documentUid)
    }
  })
  progressHandles.set(documentUid, handle)
  handle.done.catch((error) => {
    progressHandles.delete(documentUid)
    console.warn('文档 SSE 已断开', error)
  })
}
const onFileChange = (file: UploadFile) => { pendingFile.value = file }
const confirmUpload = async () => {
  const raw = pendingFile.value?.raw
  if (!raw || !kb.value) return
  const { data } = await uploadDocument(kb.value.uid, raw)
  uploadVisible.value = false
  pendingFile.value = null
  ElMessage.success(t('kb.uploadedProcessing'))
  // 直接跳到文档详情页的处理记录界面，实时跟踪处理进度
  await router.push(`/kb-manage/${kb.value.uid}/docs/${data.uid}`)
}
const handleDocMore = async (cmd: string, row: KnowledgeDoc) => {
  const id = row.id
  if (cmd === 'reprocess') { const { data } = await reprocessDocument(id); const index = docs.value.findIndex((item) => item.id === row.id); if (index >= 0) docs.value[index] = toDoc(data); const rawIndex = rawDocs.value.findIndex((item) => item.uid === id); if (rawIndex >= 0) rawDocs.value[rawIndex] = data; void subscribeProgress(id); ElMessage.success(t('doc.reprocessSubmitted')); return }
  if (cmd === 'delete') {
    deleteDocUid.value = id
    deleteDocRaw.value = rawDocs.value.find((item) => item.uid === id) || null
    deleteDocVisible.value = true
    return
  }
}
watch(kb, (value) => { if (value) { form.name = value.name; form.description = value.description === '-' ? '' : value.description } }, { immediate: true })
onMounted(() => {
  // 支持外部入口（如管理员工作台快捷入口）通过 ?status=failed|processing 直达过滤
  const statusQuery = String(route.query.status || '')
  if (['indexed', 'processing', 'failed'].includes(statusQuery)) {
    statusFilter.value = statusQuery
  }
  load()
})
onBeforeUnmount(() => {
  // 离开页面必须断开所有文档进度连接，否则会占用浏览器对后端的并发连接配额
  progressHandles.forEach((handle) => handle.abort())
  progressHandles.clear()
})
</script>

<style scoped>
.kb-detail { display: flex; flex-direction: column; gap: 12px; }
.back-btn { align-self: flex-start; color: var(--af-text-2); }
.page-card {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 12px;
  padding: 20px 24px 24px;
}

.kb-hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 8px;
  flex-wrap: wrap;
}

.hero-left {
  display: flex;
  gap: 14px;
  min-width: 0;
}

.kb-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.hero-info { min-width: 0; }

.hero-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 20px;
  font-weight: 700;
  color: var(--af-text);
  flex-wrap: wrap;
}

.hero-desc {
  margin: 6px 0;
  color: var(--af-text-2);
  font-size: 13px;
}

.hero-meta {
  font-size: 12px;
  color: var(--af-text-3);
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.hero-right {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.mini-stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.mini-stat {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--af-card-soft, rgba(255, 255, 255, 0.04));
  border: 1px solid var(--af-border-soft);
  border-radius: 10px;
  padding: 8px 12px;
  min-width: 110px;
}

.mini-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mini-icon.blue { background: rgba(77, 142, 255, 0.15); color: #4d8eff; }
.mini-icon.green { background: var(--af-success-soft); color: var(--af-success); }
.mini-icon.orange { background: var(--af-primary-soft); color: var(--af-primary); }

.mini-label { font-size: 12px; color: var(--af-text-3); }
.mini-value { font-size: 18px; font-weight: 700; color: var(--af-text); }

.hero-actions { display: flex; gap: 8px; }

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.search-input { width: 240px; }
.upload-btn { margin-left: auto; }

.name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  font-weight: 600;
  color: var(--af-text);
}

.file-icon {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.file-icon.pdf { background: linear-gradient(135deg, #ff5c33, #e03131); }
.file-icon.word { background: #4d8eff; }
.file-icon.md { background: #12b76a; }

/* 移动端卡片列表（默认隐藏） */
.mobile-doc-list { display: none; }

/* ===== 响应式 ===== */
@media (max-width: 768px) {
  .page-card { padding: 14px; }
  .hero-right { width: 100%; }
  .toolbar { flex-direction: column; }
  .search-input { width: 100%; }
  .upload-btn { margin-left: 0; }
  .doc-table { display: none; }
  .mobile-doc-list { display: flex; flex-direction: column; gap: 10px; }
  .doc-card {
    background: var(--af-card-soft, rgba(255, 255, 255, 0.04));
    border: 1px solid var(--af-border-soft);
    border-radius: 12px;
    padding: 12px;
  }
  .doc-card-head { display: flex; align-items: center; gap: 10px; }
  .doc-card-info { flex: 1; min-width: 0; }
  .doc-card-name { font-weight: 600; font-size: 14px; color: var(--af-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .doc-card-meta { font-size: 12px; color: var(--af-text-3); margin-top: 2px; }
  .doc-card-foot {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
    margin-top: 10px; font-size: 11px; color: var(--af-text-3);
  }
  .doc-card-ops { display: flex; gap: 12px; }
  .op-link { color: var(--af-primary); cursor: pointer; font-size: 12px; }
  .op-link.danger { color: var(--af-danger); }
}
</style>
