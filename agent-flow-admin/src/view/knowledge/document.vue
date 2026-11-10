<template>
  <div class="doc-page" v-if="doc">
    <div class="crumb">
      <span class="link" @click="router.push('/kb-manage')">{{ $t('nav.knowledge') }}</span>
      <el-icon><ArrowRight /></el-icon>
      <span class="link" @click="router.push(`/kb-manage/${kb?.uid ?? doc.knowledge_base_uid}`)">{{ kb?.name || $t('nav.knowledge') }}</span>
      <el-icon><ArrowRight /></el-icon>
      <span class="current">{{ doc.title }}</span>
    </div>

    <!-- 文档头卡 -->
    <div class="doc-head card">
      <div class="head-left">
        <div class="file-icon" :class="iconClass">{{ typeLabel }}</div>
        <div class="head-info">
          <div class="title-row">
            <h2>{{ doc.title }}</h2>
            <span class="status-pill" :class="'sp-' + statusType">
              <span v-if="isProcessing" class="pulse-dot" />
              {{ statusLabel }}
            </span>
            <span class="doc-id">DOC-UID: {{ doc.uid }}</span>
          </div>
          <p v-if="description" class="head-desc">{{ description }}</p>
          <div class="meta-tags">
            <span class="meta-kb"><el-icon><Collection /></el-icon>{{ kb?.name || '-' }}</span>
            <i class="dot-sep" />
            <span>{{ typeLabel }} {{ $t('doc.format') }}</span>
            <i class="dot-sep" />
            <span>{{ sizeLabel }}</span>
            <i class="dot-sep" />
            <span>{{ $t('doc.uploader') }}：{{ doc.created_by || '-' }}</span>
            <i class="dot-sep" />
            <span>{{ $t('doc.uploadTime') }}：{{ formatDate(doc.created_at) }}</span>
          </div>
        </div>
      </div>
      <div class="head-actions">
        <button class="act-btn" @click="goPreview">
          <el-icon><View /></el-icon> {{ $t('doc.tabPreview') }}
        </button>
        <button class="act-btn" @click="onDownload">
          <el-icon><Download /></el-icon> {{ $t('doc.downloadSource') }}
        </button>
        <el-dropdown v-if="canManage" trigger="click" @command="handleMore">
          <button class="act-btn icon-only"><el-icon><MoreFilled /></el-icon></button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="reprocess">{{ $t('doc.reprocess') }}</el-dropdown-item>
              <el-dropdown-item command="delete" divided>{{ $t('doc.deleteDoc') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span v-else class="readonly-badge" :title="$t('kb.readOnlyHint')">{{ $t('kb.readOnly') }}</span>
      </div>
    </div>

    <div class="doc-body">
      <div class="main-col">
        <div class="card tabs-card">
          <el-tabs v-model="activeTab">
            <el-tab-pane :label="$t('doc.tabPreview')" name="preview">
              <!-- PDF：浏览器原生预览 -->
              <div v-if="previewKind === 'pdf'" class="pdf-viewer">
                <iframe :src="fileUrl || ''" class="pdf-frame" frameborder="0" />
              </div>

              <!-- Markdown：解析后渲染进统一"纸张"主题，浏览器原生 Ctrl+F 可直接搜索 -->
              <div v-else-if="previewKind === 'md'" class="doc-viewer">
                <div v-if="mdLoading" class="md-tip"><el-skeleton :rows="8" animated /></div>
                <div v-else-if="mdError" class="md-tip">
                  <el-empty :description="mdError" :image-size="80" />
                </div>
                <div v-else ref="paperScrollRef" class="doc-paper-scroll" @scroll="onPaperScroll">
                  <!-- 标题导航：右侧留同宽占位，保证纸张仍居中 -->
                  <nav v-if="showToc" class="doc-toc" aria-label="TOC">
                    <div class="doc-toc-title">{{ $t('doc.toc') }}</div>
                    <a
                      v-for="item in tocItems"
                      :key="item.id"
                      :class="['doc-toc-item', `lv${item.level}`, { active: item.id === activeTocId }]"
                      :title="item.text"
                      @click="jumpToHeading(item.id)"
                    >{{ item.text }}</a>
                  </nav>
                  <div class="doc-markdown" :class="{ 'is-doc-gongwen': isOfficialDoc }" v-html="mdHtml" />
                  <div v-if="showToc" class="doc-toc-balance" aria-hidden="true" />
                </div>
              </div>

              <!-- Word：服务端转成 HTML 后渲染，与 md 共用同一套文档主题 -->
              <div v-else-if="previewKind === 'docx'" class="doc-viewer">
                <div v-if="docxLoading" class="md-tip"><el-skeleton :rows="10" animated /></div>
                <div v-else-if="docxError" class="md-tip">
                  <el-empty :description="docxError" :image-size="80">
                    <el-button type="primary" @click="onDownload">
                      <el-icon><Download /></el-icon> {{ $t('doc.downloadDoc') }}
                    </el-button>
                  </el-empty>
                </div>
                <div v-else ref="paperScrollRef" class="doc-paper-scroll" @scroll="onPaperScroll">
                  <nav v-if="showToc" class="doc-toc" aria-label="TOC">
                    <div class="doc-toc-title">{{ $t('doc.toc') }}</div>
                    <a
                      v-for="item in tocItems"
                      :key="item.id"
                      :class="['doc-toc-item', `lv${item.level}`, { active: item.id === activeTocId }]"
                      :title="item.text"
                      @click="jumpToHeading(item.id)"
                    >{{ item.text }}</a>
                  </nav>
                  <div class="doc-markdown docx-plain" v-html="docxHtml" />
                  <div v-if="showToc" class="doc-toc-balance" aria-hidden="true" />
                </div>
              </div>

              <!-- 其他类型暂不支持 -->
              <div v-else class="doc-viewer">
                <el-empty :description="$t('doc.unsupported', { type: typeLabel })" :image-size="100">
                  <el-button type="primary" @click="onDownload">
                    <el-icon><Download /></el-icon> {{ $t('doc.downloadDoc') }}
                  </el-button>
                </el-empty>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="$t('doc.tabInfo')" name="info">
              <el-descriptions :column="2" border>
                <el-descriptions-item :label="$t('doc.metaName')">{{ doc.title }}</el-descriptions-item>
                <el-descriptions-item :label="$t('doc.metaType')">{{ typeLabel }}</el-descriptions-item>
                <el-descriptions-item :label="$t('doc.metaSize')">{{ sizeLabel }}</el-descriptions-item>
                <el-descriptions-item :label="$t('doc.metaUploader')">{{ doc.created_by || '-' }}</el-descriptions-item>
                <el-descriptions-item :label="$t('doc.metaUploadTime')">{{ formatDate(doc.created_at) }}</el-descriptions-item>
                <el-descriptions-item :label="$t('doc.metaUpdated')">{{ formatDate(doc.updated_at) }}</el-descriptions-item>
                <el-descriptions-item :label="$t('doc.metaAccess')" :span="2">{{ doc.access_url || '-' }}</el-descriptions-item>
                <el-descriptions-item :label="$t('doc.metaStorage')" :span="2">{{ doc.storage_path || '-' }}</el-descriptions-item>
                <el-descriptions-item :label="$t('doc.metaContentType')" :span="2">{{ doc.content_type || '-' }}</el-descriptions-item>
              </el-descriptions>
            </el-tab-pane>

            <el-tab-pane :label="$t('doc.tabProcess')" name="process">
              <div class="process-panel">
                <!-- 智能处理流水线 -->
                <div class="pipeline">
                  <div class="pipeline-head">
                    <div class="pipeline-title">
                      <el-icon class="pt-icon"><Connection /></el-icon>
                      <span>{{ $t('doc.pipelineTitle') }}</span>
                    </div>
                    <div v-if="isProcessing" class="pipeline-live">
                      <el-icon class="is-loading"><Loading /></el-icon>
                      {{ $t('doc.streaming') }}
                    </div>
                  </div>
                  <div class="pipeline-steps">
                    <div class="pipe-track"><div class="pipe-fill" :style="{ width: trackPercent }" /></div>
                    <div
                      v-for="(stage, index) in stageViews"
                      :key="stage.key"
                      class="pipe-step"
                      :class="{ done: stage.done, current: stage.current, failed: stage.failed }"
                    >
                      <div class="pipe-icon">
                        <el-icon v-if="stage.done"><CircleCheckFilled /></el-icon>
                        <el-icon v-else-if="stage.current" class="is-loading"><Loading /></el-icon>
                        <el-icon v-else-if="stage.failed"><CircleCloseFilled /></el-icon>
                        <span v-else class="pipe-num">{{ index + 1 }}</span>
                      </div>
                      <div class="pipe-text">
                        <div class="pipe-name">{{ index + 1 }}. {{ $t(pipeTitles[stage.key] || stage.key) }}</div>
                        <div class="pipe-state">
                          {{ stage.done ? stage.time : stage.failed ? $t('doc.stageFailed') : stage.current ? $t('doc.stageCurrent') : $t('doc.stageWaiting') }}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-if="doc.status === 'failed' && doc.error_message" class="error-tip">
                  <el-alert type="error" :closable="false" :title="$t('doc.failReason')" :description="doc.error_message" />
                </div>

                <!-- 处理日志：按阶段分组的运行记录 -->
                <div class="log-panel">
                  <div class="log-head">
                    <span class="mac-dots"><i /><i /><i /></span>
                    <span class="log-title"><el-icon><Monitor /></el-icon>{{ $t('doc.logTitle') }}</span>
                    <span v-if="liveStageLabel" class="log-live" :class="{ on: isProcessing }">
                      <i class="log-live-dot" />
                      {{ liveStageLabel }}<template v-if="liveProgress != null"> · {{ liveProgress }}%</template>
                    </span>
                    <span class="log-count">{{ $t('doc.logRecords', { n: logs.length }) }}</span>
                    <button class="log-btn" :disabled="logs.length === 0" @click="logs = []">
                      <el-icon><Delete /></el-icon> {{ $t('doc.logClear') }}
                    </button>
                  </div>
                  <div v-if="liveProgress != null" class="log-progress">
                    <span :style="{ width: liveProgress + '%' }" />
                  </div>
                  <div ref="logBodyEl" class="log-body">
                    <div v-for="group in logGroups" :key="group.key" class="log-group">
                      <div class="lg-head">
                        <i class="lg-dot" :class="'lg-' + group.tone" />
                        <span class="lg-name">{{ group.label }}</span>
                        <span class="lg-count">{{ group.items.length }}</span>
                      </div>
                      <div
                        v-for="(log, index) in group.items"
                        :key="index"
                        class="log-line"
                        :class="['lv-' + (log.level || 'info')]"
                        :title="log.fullTime || log.time"
                      >
                        <span class="log-time">{{ log.time }}</span>
                        <i class="log-dot" />
                        <span class="log-msg">{{ log.message }}</span>
                      </div>
                    </div>
                    <div v-if="logs.length === 0" class="log-empty">
                      {{ isProcessing ? $t('doc.logEmptyConnecting') : $t('doc.logEmpty') }}
                    </div>
                  </div>
                  <div class="log-foot">
                    <div class="log-foot-meta">
                      <span>{{ $t('doc.logUpdated') }}: <b>{{ lastLogTime || '-' }}</b></span>
                      <span v-if="liveStageLabel">{{ $t('doc.logStage') }}: <b>{{ liveStageLabel }}</b></span>
                      <span v-if="!isProcessing">{{ $t('doc.logTotal') }}: <b>{{ logs.length }}</b></span>
                    </div>
                    <button class="log-copy" @click="copyLogs">
                      <el-icon><CopyDocument /></el-icon> {{ $t('doc.logCopy') }}
                    </button>
                  </div>
                </div>
              </div>
            </el-tab-pane>

            <el-tab-pane :label="$t('doc.tabChunks')" name="chunks">
              <div v-if="chunksLoading" class="md-tip"><el-skeleton :rows="6" animated /></div>
              <el-empty v-else-if="chunks.length === 0" :description="$t('doc.chunksEmpty')" />
              <div v-else class="chunk-list">
                <div v-for="(chunk, index) in chunks" :key="chunk.id" class="chunk-item">
                  <div class="chunk-head">
                    <span>{{ $t('doc.chunk') }} {{ index + 1 }}</span>
                    <el-tag size="small" :type="chunk.has_embedding ? 'success' : 'warning'" round>
                      {{ chunk.has_embedding ? $t('doc.vectorized') : $t('doc.notVectorized') }}
                    </el-tag>
                  </div>
                  <p>{{ chunk.content }}</p>
                </div>
              </div>
            </el-tab-pane>

          </el-tabs>
        </div>
      </div>

      <aside class="side-col">
        <!-- 文档状态 -->
        <div class="card">
          <div class="side-head">
            <span>{{ $t('doc.docStatus') }}</span>
            <span class="status-pill" :class="'sp-' + statusType">{{ statusLabel }}</span>
          </div>
          <div class="status-timeline">
            <div v-for="stage in sideStages" :key="stage.title" class="tl-item" :class="{ dim: !stage.done && !stage.current && !stage.failed }">
              <div class="tl-dot" :class="{ done: stage.done, current: stage.current, failed: stage.failed }">
                <el-icon v-if="stage.done"><Check /></el-icon>
                <el-icon v-else-if="stage.current" class="is-loading"><Loading /></el-icon>
                <el-icon v-else-if="stage.failed"><Close /></el-icon>
              </div>
              <div class="tl-body">
                <div class="tl-title">{{ stage.title }}</div>
                <div class="tl-time">
                  {{ stage.done ? stage.time : stage.failed ? $t('doc.stageFailed') : stage.current ? $t('doc.stageCurrent') : $t('doc.stageWaiting') }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 文档元数据信息 -->
        <div class="card">
          <div class="side-title">{{ $t('doc.docMeta') }}</div>
          <ul class="info-list">
            <li><span>{{ $t('doc.metaName') }}</span><b>{{ doc.title }}</b></li>
            <li><span>{{ $t('doc.metaType') }}</span><b>{{ typeLabel }} ({{ doc.content_type || 'Document' }})</b></li>
            <li><span>{{ $t('doc.metaSize') }}</span><b>{{ sizeLabel }}<template v-if="doc.file_size != null"> ({{ doc.file_size.toLocaleString() }} B)</template></b></li>
            <li><span>{{ $t('doc.metaUploader') }}</span><b>{{ doc.created_by || '-' }}</b></li>
            <li><span>{{ $t('doc.metaUploadTime') }}</span><b>{{ formatDate(doc.created_at) }}</b></li>
            <li><span>{{ $t('doc.metaUpdated') }}</span><b>{{ formatDate(doc.updated_at) }}</b></li>
          </ul>
        </div>

        <!-- 所属知识库关联 -->
        <div class="card">
          <div class="side-title">{{ $t('doc.kbRelated') }}</div>
          <div class="kb-link" @click="router.push(`/kb-manage/${doc.knowledge_base_uid}`)">
            <div class="kb-mini"><el-icon><Collection /></el-icon></div>
            <div class="kb-link-text">
              <span class="kb-link-name">{{ kb?.name || '-' }}</span>
              <span class="kb-link-sub">{{ $t('doc.kbDocsCount', { n: (kb as any)?.doc_count ?? '-' }) }}</span>
            </div>
            <el-icon class="kb-link-arrow"><ArrowRight /></el-icon>
          </div>
        </div>

        <!-- 处理信息 -->
        <div class="card">
          <div class="side-title">{{ $t('doc.processInfo') }}</div>
          <ul class="info-list">
            <li><span>{{ $t('doc.chunkCount') }}</span><b>{{ chunkCountLabel }}</b></li>
            <li><span>{{ $t('doc.vectorizedCount') }}</span><b>{{ vectorizedCountLabel }}</b></li>
          </ul>
          <el-button type="primary" link @click="activeTab = 'chunks'">{{ $t('doc.viewChunks') }} ></el-button>
        </div>

        <!-- 操作：仅 manage 权限可见（read 只读；后端仍会二次校验） -->
        <div v-if="canManage" class="card">
          <div class="side-title">{{ $t('common.operation') }}</div>
          <div class="side-actions">
            <el-button @click="onReprocess">
              <el-icon><RefreshRight /></el-icon> {{ $t('doc.reprocess') }}
            </el-button>
            <el-button type="danger" plain @click="onDelete">
              <el-icon><Delete /></el-icon> {{ $t('doc.deleteDoc') }}
            </el-button>
          </div>
        </div>
      </aside>
    </div>
  </div>
  <div v-else-if="loadError" class="doc-page">
    <el-empty :description="loadError">
      <el-button type="primary" @click="router.push('/kb-manage')">{{ $t('doc.backToKb') }}</el-button>
    </el-empty>
  </div>
  <div v-else class="doc-page">
    <el-skeleton :rows="10" animated />
  </div>

  <!-- 删除确认弹窗（按设计稿还原，全部使用真实数据） -->
  <DeleteDocDialog
    v-model="delDialogVisible"
    :doc="doc"
    :chunk-count="chunkCountLabel"
    @deleted="onDeleted"
  />
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { renderMarkdown } from '@/utils/markdown'
import {
  ArrowRight, Download, View, MoreFilled,
  Collection, RefreshRight, Delete, Connection, Loading, Monitor,
  CircleCheckFilled, CircleCloseFilled, Check, Close, CopyDocument
} from '@element-plus/icons-vue'
import {
  getDocument, getDocumentPreview, getKnowledgeBase, listDocumentChunks,
  reprocessDocument, watchDocumentProgress,
  type DocumentProgressHandle,
  type DocumentChunkDto, type DocumentDto, type DocumentProcessLog, type DocumentProgressEvent, type KnowledgeBaseDto
} from '@/api/knowledge'
import DeleteDocDialog from './DeleteDocDialog.vue'

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()

const doc = ref<DocumentDto | null>(null)
const kb = ref<KnowledgeBaseDto | null>(null)
/** 删除确认弹窗 */
const delDialogVisible = ref(false)
/** 仅 manage 权限可重新处理/删除文档；read 只读，按钮隐藏（后端仍二次校验） */
const canManage = computed(() => kb.value?.permission === 'manage')
const chunks = ref<DocumentChunkDto[]>([])
const chunksLoading = ref(false)
const loadError = ref('')
const activeTab = ref('preview')
const mdLoading = ref(false)
const mdError = ref('')
/** md 渲染后的 HTML（由 marked 解析 + 基础净化），套用统一文档主题 */
const mdHtml = ref('')
/** 识别为公文（含"第X条"体例）时，正文段落走首行缩进版式 */
const isOfficialDoc = ref(false)
// Word 预览：服务端转好 HTML 再下发，前端只负责渲染
const docxLoading = ref(false)
const docxError = ref('')
const docxHtml = ref('')

const extOf = (title: string) => (title.includes('.') ? title.split('.').pop()!.toLowerCase() : '')
const ext = computed(() => extOf(doc.value?.title || ''))
const typeLabel = computed(() => {
  if (ext.value === 'pdf') return 'PDF'
  if (ext.value === 'md') return 'MD'
  return ext.value ? ext.value.toUpperCase() : t('doc.unknown')
})
const previewKind = computed<'pdf' | 'md' | 'docx' | 'unsupported'>(() => {
  if (ext.value === 'pdf') return 'pdf'
  if (ext.value === 'md') return 'md'
  // docx 解析完成后 access_url 指向 MinerU 生成的 md，直接按 Markdown 渲染
  if (ext.value === 'docx' && extOf(doc.value?.access_url || '') === 'md') return 'md'
  // .doc 是老式二进制格式，服务端 mammoth 解析不了，仍走"不支持预览 + 下载"
  if (ext.value === 'docx') return 'docx'
  return 'unsupported'
})
const iconClass = computed(() => (ext.value === 'pdf' ? 'pdf' : ext.value === 'md' ? 'md' : 'other'))
// 预览/下载统一走 access_url；storage_path 是对象存储内部 key，不用于前端访问
const fileUrl = computed(() => doc.value?.access_url || '')

const sizeLabel = computed(() => {
  const size = doc.value?.file_size
  if (size == null) return '-'
  return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`
})
// 时间显示统一转本地时区：后端 ISO 字符串多为 UTC（带 Z），直接截取会差 8 小时
const formatDate = (value?: string | null) => {
  if (!value) return '-'
  if (!value.includes('T') && !value.endsWith('Z') && !value.includes('+')) {
    // 已是 "YYYY-MM-DD HH:mm:ss" 本地时间格式（如 finished_at），直接截取
    return value.replace('T', ' ').slice(0, 16)
  }
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value.replace('T', ' ').slice(0, 16)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const statusKey = (status: string) => `doc.st_${status}`
const statusLabel = computed(() => {
  const status = doc.value?.status || 'pending'
  const key = statusKey(status)
  const label = t(key)
  return label === key ? t('doc.st_pending') : label
})
const statusType = computed(() => {
  const status = doc.value?.status
  return status === 'indexed' ? 'success' as const : status === 'failed' ? 'danger' as const : 'warning' as const
})
const isProcessing = computed(() => !!doc.value && ['pending', 'processing', 'parsing', 'chunking', 'embedding'].includes(doc.value.status))
const description = computed(() => {
  if (!doc.value) return ''
  if (doc.value.status === 'failed' && doc.value.error_message) return doc.value.error_message
  return t('doc.desc')
})

/**
 * 处理阶段模型（与后端 DocumentStatus 对应）。
 * stage_records 来自 SSE 事件，形如 [{ stage: 'pending', finished_at: '...' }]，
 * 列表中出现的阶段视为已完成，其后第一个阶段为"进行中"（显示转圈）。
 */
interface StageDef { key: string; titleKey: string }
const STAGES: StageDef[] = [
  { key: 'pending', titleKey: 'doc.stageUpload' },
  { key: 'parsing', titleKey: 'doc.stageParsed' },
  { key: 'chunking', titleKey: 'doc.stageChunked' },
  { key: 'embedding', titleKey: 'doc.stageEmbedded' },
  { key: 'indexed', titleKey: 'doc.stageIndexed' }
]
// 流水线面板的阶段名（与右侧状态时间线的"完成态"命名区分）
const pipeTitles: Record<string, string> = {
  pending: 'doc.pipeUpload',
  parsing: 'doc.pipeParsing',
  chunking: 'doc.pipeChunking',
  embedding: 'doc.pipeEmbedding',
  indexed: 'doc.pipeIndexed'
}

const stageTimes = ref<Record<string, string>>({})
const applyStageRecords = (records?: { stage: string; finished_at?: string | null }[] | null) => {
  if (!records?.length) return
  const map: Record<string, string> = { ...stageTimes.value }
  for (const record of records) {
    if (record?.stage) map[record.stage] = record.finished_at ? formatDate(record.finished_at) : map[record.stage] || ''
  }
  stageTimes.value = map
}

interface StageView { key: string; titleKey: string; title: string; time: string; done: boolean; current: boolean; failed: boolean }
const stageViews = computed<StageView[]>(() => {
  const d = doc.value
  if (!d) return []
  const rawDone = STAGES.filter((stage) => stageTimes.value[stage.key]).length
  const failed = d.status === 'failed'
  // 已索引 → 全部完成；失败 → 只统计有时间戳的阶段；其余至少把"文件上传"算作完成
  const doneCount = d.status === 'indexed'
    ? STAGES.length
    : failed
      ? rawDone
      : Math.max(rawDone, 1)
  return STAGES.map((stage, index) => ({
    key: stage.key,
    titleKey: stage.titleKey,
    title: t(stage.titleKey),
    time: stageTimes.value[stage.key] || formatDate(d.updated_at),
    done: index < doneCount,
    current: !failed && d.status !== 'indexed' && index === doneCount,
    failed: failed && index === doneCount
  }))
})
const trackPercent = computed(() => {
  const list = stageViews.value
  if (!list.length) return '0%'
  const doneIdx = list.findIndex((s) => !s.done)
  const pct = doneIdx === -1 ? list.length : doneIdx
  return `${Math.round((pct / list.length) * 100)}%`
})

// 右侧时间线：五阶段 + 失败时追加"处理失败"
interface SideStep { title: string; time: string; done: boolean; current?: boolean; failed?: boolean }
const sideStages = computed<SideStep[]>(() => {
  const list: SideStep[] = stageViews.value.map((stage) => ({
    title: stage.title,
    time: stage.time,
    done: stage.done,
    current: stage.current,
    failed: stage.failed
  }))
  if (doc.value?.status === 'failed') {
    list.push({ title: t('doc.stageFailedName'), time: formatDate(doc.value.updated_at), done: false, failed: true })
  }
  return list
})

/** 日志条目：stage/level 由后端下发，前端只做分组和着色 */
interface LogLine {
  time: string
  fullTime?: string
  docId: string
  message: string
  stage?: string | null
  level?: string | null
}
const logs = ref<LogLine[]>([])
const logBodyEl = ref<HTMLElement>()
const nowTime = () => {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
// 日志时间统一取时分秒：兼容 "2026-10-26 21:00:32"（本地）与 ISO（UTC，转本地）
const logTimeOf = (value?: string | null) => {
  if (!value) return nowTime()
  const p = (n: number) => String(n).padStart(2, '0')
  if (value.includes('Z') || value.includes('+')) {
    const d = new Date(value)
    if (!Number.isNaN(d.getTime())) return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  }
  const normalized = value.replace('T', ' ')
  return (normalized.split(' ')[1] || normalized).slice(0, 8)
}
// 用后端持久化的 process_logs 预填日志面板，避免进入页面前 SSE 消息丢失
const seedLogs = (records?: DocumentProcessLog[] | null) => {
  if (!records?.length) return
  logs.value = records.map((record) => {
    const inferred = record.stage ? { stage: record.stage, text: record.message } : inferStageFromMessage(record.message)
    return {
      time: logTimeOf(record.time),
      fullTime: record.time,
      docId: record.document_uid,
      message: inferred.text || record.message,
      stage: inferred.stage || null,
      level: record.level || (record.message.startsWith('处理失败') ? 'error' : 'info')
    }
  })
}
const pushLog = (event: DocumentProgressEvent) => {
  // 去重：SSE 推送的消息可能已存在于持久化日志（进入页面瞬间的重叠）
  const last = logs.value[logs.value.length - 1]
  if (last && last.docId === event.document_uid && last.message === event.message) return
  // 时间优先使用后端事件时间戳 timestamp
  logs.value.push({
    time: logTimeOf(event.timestamp),
    fullTime: event.timestamp || '',
    docId: event.document_uid,
    message: event.message,
    stage: event.stage || event.status || null,
    level: event.level || (event.status === 'failed' ? 'error' : 'info')
  })
  void nextTick(() => {
    if (logBodyEl.value) logBodyEl.value.scrollTop = logBodyEl.value.scrollHeight
  })
}

// 实时进度：最近一条事件带来的阶段与百分比
const liveStage = ref<string | null>(null)
const liveProgress = ref<number | null>(null)
const liveStageLabel = computed(() => (liveStage.value ? stageLabelOf(liveStage.value) : ''))

/**
 * 历史日志兼容：旧版日志没有 stage 字段，只留了 "[解析]/[入库]" 这类文字前缀。
 * 按前缀反推阶段，让存量文档的日志也能正确分组；新版后端日志直接带 stage。
 */
function inferStageFromMessage(message: string): { stage: string; text: string } {
  const match = message.match(/^\s*\[([^\]]{1,8})\]\s*/)
  const tag = match?.[1] || ''
  const text = match ? message.slice(match[0].length) : message
  const stageMap: Record<string, string> = {
    Worker: 'pending', 缓存: 'pending', 解析: 'parsing', 图片: 'parsing',
    多模态: 'parsing', 切分: 'chunking', 入库: 'chunking', 向量化: 'embedding',
    检索: 'embedding', 重排序: 'embedding', 完成: 'indexed', 错误: 'failed'
  }
  return { stage: stageMap[tag] || '', text }
}

/** 把后端 stage 翻成可读文案（复用流水线的阶段名） */
function stageLabelOf(stage: string): string {
  if (stage === 'failed') return t('doc.stageFailedName')
  const key = pipeTitles[stage]
  return key ? t(key) : stage
}

/** 相邻同阶段的日志合成一组，长文档几百行也能一眼看清阶段边界 */
const logGroups = computed(() => {
  const groups: { key: string; stage: string; label: string; tone: string; items: LogLine[] }[] = []
  logs.value.forEach((log, index) => {
    const stage = log.stage || 'other'
    const last = groups[groups.length - 1]
    if (last && last.stage === stage) {
      last.items.push(log)
      return
    }
    groups.push({
      key: `${stage}-${index}`,
      stage,
      label: stage === 'other' ? t('doc.logStageOther') : stageLabelOf(stage),
      tone: stage === 'failed' ? 'danger' : stage === 'indexed' ? 'success' : stage === 'other' ? 'muted' : 'primary',
      items: [log]
    })
  })
  return groups
})

const lastLogTime = computed(() => logs.value[logs.value.length - 1]?.fullTime || logs.value[logs.value.length - 1]?.time || '')

const copyLogs = async () => {
  const text = logs.value
    .map((log) => `[${log.time}] ${log.stage ? stageLabelOf(log.stage) + ' | ' : ''}${log.message}`)
    .join('\n')
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(t('doc.logCopied'))
  } catch {
    ElMessage.warning(t('doc.logCopyFailed'))
  }
}

/** 建立 / 复用 SSE 进度连接（仅在文档处理中时建立） */
let sseDocId: string | null = null
/** 当前 SSE 句柄：离开页面或切换文档时必须 abort，否则残留连接会占满浏览器并发配额 */
let sseHandle: DocumentProgressHandle | null = null

/** 主动断开进度连接（幂等） */
const stopProgress = () => {
  const handle = sseHandle
  sseHandle = null
  sseDocId = null
  handle?.abort()
}

const connectProgress = () => {
  const d = doc.value
  if (!d || !isProcessing.value) {
    stopProgress()
    return
  }
  // 同一文档已连着的连接直接复用
  if (sseDocId === d.uid && sseHandle) return
  stopProgress()
  sseDocId = d.uid

  const handle = watchDocumentProgress(d.uid, (event) => {
    if (!doc.value || event.document_uid !== doc.value.uid) return
    pushLog(event)
    if (event.stage || event.status) liveStage.value = event.stage || event.status || null
    if (event.progress != null) liveProgress.value = event.progress
    applyStageRecords(event.stage_records)
    const patch: Partial<DocumentDto> = {}
    if (event.status) patch.status = event.status
    if (event.chunk_count != null) patch.chunk_count = event.chunk_count
    if (event.vectorized_count != null) patch.vectorized_count = event.vectorized_count
    doc.value = { ...doc.value, ...patch }
    if (event.status === 'indexed') {
      void loadChunks()
      ElMessage.success(t('doc.indexedDone'))
      // 解析阶段后端可能已把 access_url 改写为 Markdown 预览地址（docx），
      // 页面在上传时就打开的话本地还留着旧的 docx 直链，必须重新拉取一次，
      // 否则预览会一直停留在 Word 转 HTML 的渲染分支
      void getDocument(doc.value.uid)
        .then((fresh) => {
          doc.value = fresh.data
          loadPreview()
        })
        .catch(() => { /* 刷新失败时保持现状 */ })
    }
    if (event.status === 'failed' && doc.value) doc.value = { ...doc.value, error_message: event.message }
  })
  sseHandle = handle

  handle.done
    .then(async () => {
      // 已被主动中止 / 已被新连接替换时不再处理
      if (sseHandle !== handle) return
      sseHandle = null
      sseDocId = null
      // 流结束后若文档仍处于处理中（如终态事件被错过），主动拉取一次最新状态兜底
      if (doc.value && isProcessing.value) {
        try {
          const res = await getDocument(doc.value.uid)
          doc.value = res.data
          // 兜底刷新：状态已落定时 access_url 可能已被后端改写（docx → md），重载预览
          loadPreview()
        } catch { /* 刷新失败时保持现状 */ }
      }
    })
    .catch((error) => {
      console.warn('文档 SSE 已断开', error)
      if (sseHandle !== handle) return
      sseHandle = null
      sseDocId = null
    })
}

onBeforeUnmount(() => {
  stopProgress()
  mdController?.abort()
  mdController = null
})

// 后端响应可能缺少 chunk_count / vectorized_count，优先取接口值，回退到已加载的分块数量
const chunkCountLabel = computed(() => doc.value?.chunk_count ?? chunks.value.length)
const vectorizedCountLabel = computed(() => doc.value?.vectorized_count ?? chunks.value.filter((c) => c.has_embedding).length)

const loadChunks = async () => {
  if (!doc.value) return
  chunksLoading.value = true
  try {
    const { data } = await listDocumentChunks(doc.value.uid)
    chunks.value = [...data].sort((a, b) => a.chunk_index - b.chunk_index)
  } catch {
    chunks.value = []
  } finally {
    chunksLoading.value = false
  }
}

/** 预览文件下载的中止句柄：切换文档/离开页面时立即释放连接 */
let mdController: AbortController | null = null

/**
 * 文档类 Markdown 的展示增强：MinerU 转出的 md 会丢失 Word 原文的层级
 * （"第一章 总则"、"第X条" 在 Word 里是标题/加粗，转 md 后全是纯文本，
 * 整页看起来像一张扫描图）。这里在渲染前把常见公文结构还原出来，
 * 只影响预览显示，不改动 RAG 检索用的原始内容。
 */
const enhanceDocumentMarkdown = (text: string) =>
  text
    // "第一章 总则" 独立成行的 → 转成三级标题
    .replace(/^(第[一二三四五六七八九十百千零两\d]+章\s*\S.*)$/gm, '### $1')
    // 只有章号的裸标题（"第一章"）也补上层级
    .replace(/^(第[一二三四五六七八九十百千零两\d]+章)$/gm, '### $1')
    // "第X条" / "第X节" 开头的段落 → 恢复引导词加粗
    .replace(/^(第[一二三四五六七八九十百千零两\d]+[条节])(\s|　)/gm, '**$1**$2')

/** 公文体例识别：出现"第X条"即按公文版式处理（首行缩进） */
const GONGWEN_RE = /第[一二三四五六七八九十百千零两\d]+条/

/* ===== 标题导航（TOC）：从渲染后的 HTML 提取 h1~h3，支持点击跳转与滚动高亮 ===== */
interface TocItem { id: string; text: string; level: number }
const paperScrollRef = ref<HTMLElement | null>(null)
const tocItems = ref<TocItem[]>([])
const activeTocId = ref('')
/** 标题太少（不足 3 个）时目录没有导航价值，直接隐藏 */
const showToc = computed(() => tocItems.value.length >= 3)

const buildToc = async () => {
  await nextTick()
  const paper = paperScrollRef.value?.querySelector('.doc-markdown')
  const heads = paper ? Array.from(paper.querySelectorAll('h1, h2, h3')) : []
  const raw: TocItem[] = []
  heads.forEach((h, i) => {
    const text = (h.textContent || '').trim().slice(0, 40)
    if (!text) return
    raw.push({ id: `doc-h-${i}`, text, level: Number(h.tagName.slice(1)) })
  })
  // MinerU 常把 Word 自带的目录页也转成章节标题，导航会出现整段重复；
  // 同名标题只保留最后一次出现（正文里的真章节），跳转才不会落在目录页上
  const lastIndex = new Map<string, number>()
  raw.forEach((it, i) => lastIndex.set(it.text, i))
  const items = raw.filter((it, i) => lastIndex.get(it.text) === i)
  items.forEach((it) => heads[Number(it.id.slice(6))]?.setAttribute('id', it.id))
  tocItems.value = items
  activeTocId.value = items[0]?.id || ''
}

/** 滚动跟随：取视口顶部以上最近的标题作为当前项 */
const onPaperScroll = () => {
  const container = paperScrollRef.value
  if (!container || !tocItems.value.length) return
  const base = container.getBoundingClientRect().top
  let current = tocItems.value[0]?.id || ''
  for (const item of tocItems.value) {
    const el = container.querySelector(`#${CSS.escape(item.id)}`)
    if (!el) continue
    if (el.getBoundingClientRect().top - base <= 120) current = item.id
    else break
  }
  activeTocId.value = current
}

const jumpToHeading = (id: string) => {
  const container = paperScrollRef.value
  const el = container?.querySelector(`#${CSS.escape(id)}`)
  if (!container || !el) return
  activeTocId.value = id
  // 只滚动预览容器自身：scrollIntoView 会连带滚动外层页面，把整卡滚出视口
  const top = el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
  container.scrollTo({ top, behavior: 'smooth' })
}

// 预览 HTML 更新（新文档加载 / md 解析完成 / docx 转换完成）后重建目录
watch([mdHtml, docxHtml], () => { void buildToc() })


const loadMarkdown = async () => {
  if (previewKind.value !== 'md' || !fileUrl.value) return
  mdLoading.value = true
  mdError.value = ''
  // access_url 可能是 MinIO 直链，网络不通时 fetch 会长时间挂起，加 8s 超时兜底
  mdController?.abort()
  const controller = new AbortController()
  mdController = controller
  const timer = window.setTimeout(() => controller.abort(), 8000)
  try {
    const response = await fetch(fileUrl.value, { signal: controller.signal })
    if (!response.ok) throw new Error(t('doc.loadFileFail', { code: response.status }))
    const raw = await response.text()
    isOfficialDoc.value = GONGWEN_RE.test(raw)
    // 超长文档（> 50 万字符）一次性 DOM 化会明显卡顿，给出轻量提示但仍渲染
    if (raw.length > 500_000) ElMessage.warning(t('doc.tooLarge'))
    mdHtml.value = renderMarkdown(enhanceDocumentMarkdown(raw))
  } catch (error) {
    if (controller.signal.aborted) return
    mdError.value = error instanceof Error ? t('doc.mdLoadFailReason', { reason: error.message }) : t('doc.mdLoadFail')
  } finally {
    window.clearTimeout(timer)
    if (mdController === controller) {
      mdController = null
      mdLoading.value = false
    }
  }
}

/** Word 预览：后端用 mammoth 转好 HTML（图片已内联），前端直接渲染 */
const loadDocx = async () => {
  if (previewKind.value !== 'docx' || !doc.value) return
  docxLoading.value = true
  docxError.value = ''
  try {
    const { data } = await getDocumentPreview(doc.value.uid)
    if (data.kind === 'html') {
      docxHtml.value = data.html
    } else if (data.kind === 'none') {
      docxError.value = data.reason || t('doc.unsupported', { type: typeLabel.value })
    } else {
      docxError.value = t('doc.previewEmpty')
    }
  } catch (error) {
    const detail = (error as { response?: { data?: { msg?: string; detail?: string } } })?.response?.data
    docxError.value = detail?.msg || detail?.detail || t('doc.mdLoadFail')
  } finally {
    docxLoading.value = false
  }
}

/** 按文件类型分派预览加载器（PDF 交给浏览器原生渲染，无需请求） */
const loadPreview = () => {
  if (previewKind.value === 'md') void loadMarkdown()
  else if (previewKind.value === 'docx') void loadDocx()
}

const load = async () => {
  loadError.value = ''
  doc.value = null
  kb.value = null
  chunks.value = []
  stageTimes.value = {}
  logs.value = []
  mdHtml.value = ''
  isOfficialDoc.value = false
  docxHtml.value = ''
  liveStage.value = null
  liveProgress.value = null
  // 切换文档前先断开旧连接，避免旧文档的 SSE 继续占用并发连接
  stopProgress()
  try {
    const { data } = await getDocument(String(route.params.docId || ''))
    doc.value = data
    // 阶段与日志直接来自文档接口响应，先渲染，不依赖后续任何慢请求
    applyStageRecords(data.stage_records)
    seedLogs(data.process_logs)
    if (isProcessing.value) {
      // 上传后跳转进来时，处理中的文档默认展示"处理记录"并建立 SSE 实时进度连接
      activeTab.value = 'process'
      connectProgress()
    }
    const kbResponse = await getKnowledgeBase(data.knowledge_base_uid || '')
    kb.value = kbResponse.data
    // chunk_count 可能不下发，直接尝试加载分块（无分块时接口返回空数组）
    void loadChunks()
    // 预览可能因对象存储跨域/转换耗时变慢，非阻塞加载，不拖慢主信息渲染
    loadPreview()
  } catch (error) {
    // 无权限 / 不存在等错误：优先展示后端返回的具体原因（拦截器也会提示一次）
    const detail = (error as { response?: { data?: { msg?: string; detail?: string } } })?.response?.data
    loadError.value = detail?.msg || detail?.detail || (error instanceof Error ? t('doc.loadFailRetry') : t('doc.loadFailMissing'))
  }
}

watch(() => route.params.docId, () => {
  if (route.name === 'KnowledgeDocument') void load()
})
void load()

const goPreview = () => {
  activeTab.value = 'preview'
  loadPreview()
}

const onDownload = () => {
  // 下载源文件：docx 的 access_url 已指向解析后的 md，这里优先用源文件直链
  const target = doc.value?.source_url || fileUrl.value
  if (!target) {
    ElMessage.warning(t('doc.noDownloadable'))
    return
  }
  const anchor = document.createElement('a')
  anchor.href = target
  anchor.download = doc.value?.title || 'document'
  anchor.target = '_blank'
  anchor.rel = 'noopener'
  anchor.click()
  ElMessage.success(t('doc.downloadStarted'))
}

const onReprocess = async () => {
  if (!doc.value) return
  const { data } = await reprocessDocument(doc.value.uid)
  doc.value = data
  stageTimes.value = {}
  logs.value = []
  liveStage.value = null
  liveProgress.value = null
  // 重新处理要拿到全新的进度流：先断开可能仍在的旧连接
  stopProgress()
  activeTab.value = 'process'
  ElMessage.success(t('doc.reprocessSubmitted'))
  connectProgress()
}

const onDelete = () => {
  if (!doc.value) return
  delDialogVisible.value = true
}

const onDeleted = (kbUid: string) => {
  ElMessage.success(t('doc.deleted'))
  router.push(kbUid ? `/kb-manage/${kbUid}` : '/kb-manage')
}

const handleMore = (cmd: string) => {
  if (cmd === 'reprocess') void onReprocess()
  if (cmd === 'delete') void onDelete()
}

// 语言切换时刷新已渲染的阶段标题
watch(locale, () => {
  stageTimes.value = { ...stageTimes.value }
})
</script>

<style scoped>
.doc-page { display: flex; flex-direction: column; gap: 14px; min-height: calc(100vh - 128px); }
.card {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 12px;
  padding: 16px 20px;
}
.crumb {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--af-text-3);
  font-size: 13px;
}
.crumb .link { cursor: pointer; color: var(--af-text-2); }
.crumb .link:hover { color: var(--af-primary); }
.crumb .current { color: var(--af-text); font-weight: 600; }

/* ===== 文档头卡 ===== */
.doc-head { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.head-left { display: flex; gap: 14px; min-width: 0; }
.file-icon {
  width: 52px; height: 52px; border-radius: 12px;
  color: #fff; font-size: 12px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.file-icon.pdf { background: linear-gradient(135deg, #ff5c33, #e03131); }
.file-icon.md { background: linear-gradient(135deg, #12b76a, #059669); }
.file-icon.other { background: #4e5969; }
.head-info { min-width: 0; }
.title-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.title-row h2 { font-size: 19px; color: var(--af-text); }
.status-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 11px; border-radius: 999px; font-size: 12px; font-weight: 500;
}
.status-pill.sp-success { color: var(--af-success); background: var(--af-success-soft); }
.status-pill.sp-danger { color: var(--af-danger); background: var(--af-danger-soft); }
.status-pill.sp-warning { color: var(--af-primary); background: var(--af-primary-soft); }
.pulse-dot {
  width: 6px; height: 6px; border-radius: 50%; background: currentColor;
  animation: doc-pulse 1.2s ease-in-out infinite;
}
@keyframes doc-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }
.doc-id {
  font-size: 11px; color: var(--af-text-3);
  background: var(--af-card-soft, rgba(255, 255, 255, 0.06));
  border: 1px solid var(--af-border-soft);
  border-radius: 6px; padding: 2px 8px; font-family: Consolas, monospace;
}
.head-desc { margin: 6px 0 8px; color: var(--af-text-3); font-size: 13px; }
.meta-tags { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--af-text-3); flex-wrap: wrap; }
.meta-kb { display: inline-flex; align-items: center; gap: 4px; color: var(--af-info); }
.dot-sep { width: 3px; height: 3px; border-radius: 50%; background: var(--af-border); display: inline-block; }
.head-actions { display: flex; gap: 8px; height: fit-content; align-items: center; }
.act-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px; border-radius: 10px;
  background: var(--af-card-soft, rgba(255, 255, 255, 0.05));
  border: 1px solid var(--af-border-soft);
  color: var(--af-text); font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all 0.15s;
}
.act-btn:hover { background: var(--af-hover); }
.act-btn.icon-only { padding: 8px 10px; color: var(--af-text-2); }

.doc-body { display: flex; gap: 14px; align-items: stretch; flex: 1; }
.main-col { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.side-col { width: 300px; display: flex; flex-direction: column; gap: 14px; flex-shrink: 0; }
.tabs-card { flex: 1 1 auto; display: flex; flex-direction: column; min-height: 0; }
.tabs-card :deep(.el-tabs) { flex: 1 1 auto; display: flex; flex-direction: column; }
.tabs-card :deep(.el-tabs__content) { flex: 1 1 auto; min-height: 0; }
.tabs-card :deep(#pane-process) { height: 100%; }

/* ===== 预览 ===== */
/* 让预览窗口撑满卡片高度，与右侧栏底部平齐；
   min-height:0 + overflow:hidden 让 .doc-paper-scroll 成为真正的滚动容器
   （否则长文档会撑破卡片、滚动落到外层页面，目录吸顶与滚动高亮都会失效） */
.tabs-card :deep(#pane-preview) { height: 100%; min-height: 0; overflow: hidden; }
.pdf-viewer { height: 100%; display: flex; flex-direction: column; background: rgba(255, 255, 255, 0.04); border-radius: 10px; padding: 8px; }
.pdf-frame { flex: 1; min-height: 560px; width: 100%; border-radius: 8px; display: block; background: #fff; }
/* 预览内容容器：高度按视口约束，长文档在容器内部滚动
   （顶部偏移约 302px：面包屑 + 文档头 + Tab 头，再留 28px 底部间距）；
   只有让 .doc-paper-scroll 真正成为滚动容器，目录吸顶与滚动高亮才生效 */
.doc-viewer { height: calc(100vh - 330px); min-height: 480px; display: flex; flex-direction: column; }
.doc-viewer > .doc-paper-scroll { flex: 1 1 auto; min-height: 0; }
.md-tip { width: 100%; padding: 12px; }
/* Word 转出来的 HTML 结构更扁平，补一点段落间距，读起来更像原文 */
.doc-markdown.docx-plain > p { margin: 0 0 10px; }


/* ===== 分块 ===== */
.chunk-item {
  border: 1px solid var(--af-border-soft); border-radius: 10px; padding: 12px 14px; margin-bottom: 10px;
  background: var(--af-card-soft, rgba(255, 255, 255, 0.03));
}
.chunk-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-weight: 600; }
.chunk-item p { font-size: 13px; color: var(--af-text-2); line-height: 1.7; }

/* ===== 处理记录：流水线 ===== */
.process-panel { display: flex; flex-direction: column; height: 100%; min-height: 420px; }
.pipeline {
  background: var(--af-card-soft, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--af-border-soft);
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
}
.pipeline-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.pipeline-title { display: flex; align-items: center; gap: 8px; font-weight: 600; color: var(--af-text); font-size: 14px; }
.pt-icon { color: var(--af-primary); font-size: 17px; }
.pipeline-live { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--af-text-3); }
.pipeline-steps {
  position: relative;
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 10px;
}
.pipe-track {
  position: absolute; top: 20px; left: 8%; right: 8%; height: 2px;
  background: var(--af-border-soft); z-index: 0;
}
.pipe-fill { height: 100%; background: var(--af-success); transition: width 0.7s ease; }
.pipe-step { position: relative; z-index: 1; display: flex; flex-direction: column; gap: 8px; background: var(--af-card); border: 1px solid var(--af-border-soft); border-radius: 10px; padding: 10px 12px; }
.pipe-step.current { border-color: rgba(255, 92, 51, 0.5); box-shadow: 0 0 14px rgba(255, 92, 51, 0.18); }
.pipe-step.failed { border-color: rgba(245, 63, 63, 0.5); }
.pipe-step.waiting { opacity: 0.6; }
.pipe-icon {
  width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 16px;
  background: rgba(255, 255, 255, 0.06); color: var(--af-text-3);
}
.pipe-step.done .pipe-icon { background: var(--af-success-soft); color: var(--af-success); }
.pipe-step.current .pipe-icon { background: var(--af-primary-soft); color: var(--af-primary); }
.pipe-step.failed .pipe-icon { background: var(--af-danger-soft); color: var(--af-danger); }
.pipe-num { font-size: 12px; font-weight: 700; }
.pipe-name { font-size: 12.5px; font-weight: 600; color: var(--af-text); }
.pipe-step.current .pipe-name { color: var(--af-primary); }
.pipe-state { font-size: 11px; color: var(--af-text-3); margin-top: 2px; }
.pipe-step.done .pipe-state { color: var(--af-success); }
.pipe-step.current .pipe-state { color: var(--af-primary); }
.pipe-step.failed .pipe-state { color: var(--af-danger); }
.error-tip { margin-bottom: 14px; }

/* ===== 日志：按阶段分组的运行记录 ===== */
.log-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-radius: 12px; overflow: hidden;
  border: 1px solid var(--af-border-soft);
  background: #0d0e11;
}
.log-head {
  flex-shrink: 0;
  display: flex; align-items: center; gap: 10px;
  padding: 9px 14px; background: #141519; border-bottom: 1px solid var(--af-border-soft);
}
.mac-dots { display: inline-flex; gap: 5px; }
.mac-dots i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.mac-dots i:nth-child(1) { background: #ff5f57; }
.mac-dots i:nth-child(2) { background: #febc2e; }
.mac-dots i:nth-child(3) { background: #28c840; }
.log-title { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; font-size: 13px; color: var(--af-text); }
.log-live {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; color: var(--af-text-3);
  border: 1px solid var(--af-border-soft); border-radius: 999px; padding: 2px 10px;
  white-space: nowrap;
}
.log-live.on { color: var(--af-primary); border-color: rgba(255, 92, 51, 0.35); background: var(--af-primary-soft); }
.log-live-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--af-text-3); display: inline-block; }
.log-live.on .log-live-dot { background: var(--af-primary); animation: logPulse 1.4s ease-in-out infinite; }
@keyframes logPulse {
  0%, 100% { opacity: 0.35; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.1); }
}
.log-count {
  font-size: 11px; color: var(--af-info);
  background: rgba(77, 142, 255, 0.12);
  border-radius: 999px; padding: 2px 10px;
}
.log-btn {
  margin-left: auto;
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--af-text-3);
  background: transparent; border: none; cursor: pointer;
  padding: 4px 8px; border-radius: 6px; transition: all 0.15s;
}
.log-btn:hover:not(:disabled) { color: var(--af-danger); background: var(--af-hover); }
.log-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.log-progress { height: 2px; background: #141519; flex-shrink: 0; }
.log-progress span {
  display: block; height: 100%;
  background: linear-gradient(90deg, var(--af-primary), #ffa06b);
  transition: width 0.4s ease;
}
.log-body {
  flex: 1;
  min-height: 0;
  background: #0d0e11; overflow: auto;
  padding: 12px 14px; font-family: 'JetBrains Mono', Consolas, monospace;
}
.log-group { margin-bottom: 12px; }
.log-group:last-child { margin-bottom: 0; }
.lg-head { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.lg-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.lg-primary { background: var(--af-primary); }
.lg-success { background: var(--af-success); }
.lg-danger { background: var(--af-danger); }
.lg-muted { background: #4b5563; }
.lg-name { font-size: 11.5px; font-weight: 700; letter-spacing: 0.3px; color: var(--af-text-2); white-space: nowrap; }
.lg-count { font-size: 10px; color: var(--af-text-3); background: rgba(255, 255, 255, 0.06); border-radius: 999px; padding: 0 7px; }
.lg-head::after { content: ''; flex: 1; height: 1px; background: var(--af-border-soft); }
.log-line {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 12px; line-height: 1.85; color: #c3c9d4;
  padding: 1px 0 1px 4px; border-left: 2px solid transparent;
  word-break: break-word;
}
.log-line:hover { background: rgba(255, 255, 255, 0.03); }
.log-time { color: #5c6472; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.log-dot { width: 4px; height: 4px; border-radius: 50%; background: #4edea3; flex-shrink: 0; margin-top: 8px; }
.log-msg { flex: 1; min-width: 0; }
.lv-success .log-msg { color: #4edea3; }
.lv-warn .log-msg { color: #f5c451; }
.lv-warn .log-dot { background: #f5c451; }
.lv-error { border-left-color: rgba(255, 92, 51, 0.55); background: rgba(255, 92, 51, 0.06); }
.lv-error .log-msg { color: #ff8b86; }
.lv-error .log-dot { background: #ff8b86; }
.log-empty { font-size: 12px; color: #6b7280; text-align: center; padding: 48px 0; }
.log-foot {
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap;
  padding: 8px 14px; background: #141519; border-top: 1px solid var(--af-border-soft);
  font-size: 11px; color: var(--af-text-3);
}
.log-foot-meta { display: flex; gap: 16px; flex-wrap: wrap; }
.log-foot b { color: var(--af-text-2); font-weight: 600; }
.log-copy {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: var(--af-primary);
  background: transparent; border: none; cursor: pointer;
  padding: 4px 8px; border-radius: 6px;
}
.log-copy:hover { background: var(--af-primary-soft); }

/* ===== 右侧栏 ===== */
.side-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-weight: 600; }
.side-title { font-weight: 600; margin-bottom: 12px; }

/* 文档状态时间线 */
.status-timeline { position: relative; padding-left: 26px; display: flex; flex-direction: column; gap: 18px; }
.status-timeline::before {
  content: '';
  position: absolute; left: 8px; top: 10px; bottom: 10px; width: 2px;
  background: var(--af-border-soft);
}
.tl-item { position: relative; }
.tl-item.dim { opacity: 0.55; }
.tl-dot {
  position: absolute; left: -26px; top: 2px;
  width: 18px; height: 18px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px;
  background: var(--af-card); border: 2px solid var(--af-border); color: transparent;
}
.tl-dot.done { background: var(--af-success); border-color: var(--af-success); color: #fff; }
.tl-dot.current { background: var(--af-primary-soft); border-color: var(--af-primary); color: var(--af-primary); }
.tl-dot.failed { background: var(--af-danger-soft); border-color: var(--af-danger); color: var(--af-danger); }
.tl-title { font-size: 13px; font-weight: 600; color: var(--af-text); }
.tl-time { font-size: 11px; color: var(--af-text-3); margin-top: 2px; }

.info-list { display: flex; flex-direction: column; }
.info-list li {
  display: flex; justify-content: space-between; gap: 12px; font-size: 13px;
  padding: 7px 0; border-bottom: 1px solid var(--af-border-soft);
}
.info-list li:last-child { border-bottom: none; }
.info-list span { color: var(--af-text-3); flex-shrink: 0; }
.info-list b { font-weight: 500; color: var(--af-text); text-align: right; word-break: break-all; }

.kb-link {
  display: flex; align-items: center; gap: 12px; cursor: pointer;
  background: var(--af-card-soft, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--af-border-soft);
  border-radius: 10px; padding: 12px; transition: all 0.15s;
}
.kb-link:hover { border-color: rgba(255, 92, 51, 0.4); }
.kb-mini {
  width: 40px; height: 40px; border-radius: 10px; background: rgba(77, 142, 255, 0.15); color: #4d8eff;
  display: flex; align-items: center; justify-content: center; font-size: 19px; flex-shrink: 0;
}
.kb-link-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.kb-link-name { font-weight: 600; font-size: 13px; color: var(--af-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kb-link-sub { font-size: 11px; color: var(--af-text-3); }
.kb-link-arrow { color: var(--af-text-3); }
.side-actions { display: flex; flex-direction: column; gap: 8px; }
.side-actions .el-button { width: 100%; margin-left: 0; }
.readonly-badge {
  padding: 6px 10px; border-radius: 8px;
  border: 1px solid var(--af-border-soft);
  color: var(--af-text-3); font-size: 11px;
  white-space: nowrap;
}

/* ===== 响应式 ===== */
@media (max-width: 1100px) {
  .doc-body { flex-direction: column; }
  .side-col { width: 100%; display: grid; grid-template-columns: repeat(2, 1fr); align-items: start; }
}
@media (max-width: 768px) {
  .pipeline-steps { grid-template-columns: 1fr; }
  .pipe-track { display: none; }
  .side-col { grid-template-columns: 1fr; }
  .doc-head { flex-direction: column; }
  .head-actions { width: 100%; }
  .head-actions .act-btn { flex: 1; justify-content: center; }
  .log-foot-meta { gap: 10px; }
}
@media (max-width: 480px) {
  .pdf-frame { height: 480px; }
}
</style>
