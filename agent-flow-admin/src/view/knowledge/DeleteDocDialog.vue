<template>
  <el-dialog
    :model-value="modelValue"
    width="520px"
    align-center
    :show-header="false"
    :show-close="false"
    class="dd-dialog"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @closed="reset"
  >
    <!-- 顶部危险氛围亮线 -->
    <div class="dd-topbar"></div>

    <!-- Header -->
    <div class="dd-header">
      <div class="dd-header-main">
        <div class="dd-badge">
          <el-icon :size="24"><Delete /></el-icon>
          <span class="dd-badge-dot"></span>
        </div>
        <div class="dd-header-text">
          <div class="dd-title-row">
            <h3>{{ $t('doc.delTitle') }}</h3>
            <span class="dd-chip">{{ $t('doc.delIrreversible') }}</span>
          </div>
          <p class="dd-sub">{{ $t('doc.delDesc') }}</p>
        </div>
      </div>
      <button class="dd-close" @click="close">
        <el-icon :size="16"><Close /></el-icon>
      </button>
    </div>

    <!-- Body -->
    <div class="dd-body">
      <!-- 待删除对象卡片（全部真实数据） -->
      <div class="dd-doc-card">
        <div class="dd-doc-main">
          <div class="dd-file-badge" :class="iconClass">
            <el-icon :size="22"><Document /></el-icon>
          </div>
          <div class="dd-doc-info">
            <span class="dd-doc-name" :title="doc?.title">{{ doc?.title }}</span>
            <div class="dd-doc-meta">
              <span>{{ typeLabel }} · {{ sizeLabel }}</span>
              <span>{{ formatDate(doc?.created_at) }}</span>
              <span v-if="doc?.created_by">{{ doc.created_by }}</span>
            </div>
          </div>
        </div>
        <!-- 当前处理阶段胶囊：仅处理中显示，不展示虚构百分比 -->
        <div v-if="isProcessing" class="dd-stage">
          <div class="dd-stage-left">
            <span class="dd-stage-dot"></span>
            <span>{{ $t('doc.delStageRunning') }}</span>
          </div>
          <span class="dd-stage-name">{{ statusText }}</span>
        </div>
      </div>

      <!-- 级联影响（按真实数据渲染，没有的条目直接不展示） -->
      <div class="dd-risk">
        <div class="dd-risk-head">
          <el-icon :size="16"><Warning /></el-icon>
          <span>{{ $t('doc.delRiskTitle') }}</span>
        </div>
        <ul>
          <li v-if="isProcessing">
            <el-icon :size="13"><RemoveFilled /></el-icon>
            <span>{{ $t('doc.delRiskTask') }}</span>
          </li>
          <li v-if="chunkCount > 0">
            <el-icon :size="13"><RemoveFilled /></el-icon>
            <span>{{ $t('doc.delRiskChunks', { n: chunkCount }) }}</span>
          </li>
          <li v-else class="dim">
            <el-icon :size="13"><RemoveFilled /></el-icon>
            <span>{{ $t('doc.delRiskNoChunks') }}</span>
          </li>
          <li>
            <el-icon :size="13"><RemoveFilled /></el-icon>
            <span>{{ $t('doc.delRiskRetrieval') }}</span>
          </li>
        </ul>
      </div>

      <!-- 二次确认复选框 -->
      <label class="dd-confirm">
        <input v-model="checked" type="checkbox" />
        <span class="dd-checkbox">
          <el-icon :size="11"><Check /></el-icon>
        </span>
        <span class="dd-confirm-text">{{ $t('doc.delCheckbox') }}</span>
      </label>
    </div>

    <!-- Footer -->
    <div class="dd-footer">
      <button class="dd-btn" type="button" @click="close">{{ $t('common.cancel') }}</button>
      <button
        class="dd-danger"
        type="button"
        :class="{ armed: checked, loading: state === 'loading', done: state === 'done' }"
        :disabled="!checked || state !== 'idle'"
        @click="submit"
      >
        <el-icon v-if="state === 'loading'" :size="15" class="spin"><Loading /></el-icon>
        <el-icon v-else-if="state === 'done'" :size="15"><Check /></el-icon>
        <el-icon v-else :size="15"><Delete /></el-icon>
        <span>
          {{ state === 'loading' ? $t('doc.delSubmitting') : state === 'done' ? $t('doc.delDone') : $t('doc.delSubmit') }}
        </span>
      </button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Check, Close, Delete, Document, Loading, RemoveFilled, Warning
} from '@element-plus/icons-vue'
import { deleteDocument, type DocumentDto } from '@/api/knowledge'

const props = defineProps<{
  modelValue: boolean
  doc: DocumentDto | null
  /** 当前真实分块数量（父组件已加载的分块列表优先） */
  chunkCount: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  /** 删除成功后触发，参数为所属知识库 uid（用于跳转） */
  deleted: [kbUid: string]
}>()

const { t } = useI18n()

const checked = ref(false)
const state = ref<'idle' | 'loading' | 'done'>('idle')

const close = () => emit('update:modelValue', false)

const extOf = (title?: string) => (title && title.includes('.') ? title.split('.').pop()!.toLowerCase() : '')
const ext = computed(() => extOf(props.doc?.title))
const typeLabel = computed(() => {
  if (ext.value === 'pdf') return 'PDF'
  if (ext.value === 'md') return 'MD'
  return ext.value ? ext.value.toUpperCase() : 'Document'
})
const iconClass = computed(() => (ext.value === 'pdf' ? 'pdf' : ext.value === 'md' ? 'md' : 'other'))

const sizeLabel = computed(() => {
  const size = props.doc?.file_size
  if (size == null) return '-'
  return size < 1024 * 1024 ? `${Math.max(1, Math.round(size / 1024))} KB` : `${(size / 1024 / 1024).toFixed(1)} MB`
})

const formatDate = (value?: string | null) => {
  if (!value) return '-'
  if (!value.includes('T') && !value.endsWith('Z') && !value.includes('+')) {
    return value.replace('T', ' ').slice(0, 16)
  }
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value.replace('T', ' ').slice(0, 16)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const isProcessing = computed(() =>
  !!props.doc && ['pending', 'processing', 'parsing', 'chunking', 'embedding'].includes(props.doc.status)
)

const statusText = computed(() => {
  const status = props.doc?.status || 'pending'
  const key = `doc.st_${status}`
  const label = t(key)
  return label === key ? t('doc.st_pending') : label
})

const reset = () => {
  checked.value = false
  state.value = 'idle'
}

const submit = async () => {
  const d = props.doc
  if (!d || !checked.value || state.value !== 'idle') return
  state.value = 'loading'
  try {
    await deleteDocument(d.uid)
    state.value = 'done'
    setTimeout(() => {
      emit('deleted', d.knowledge_base_uid || '')
      // 无论父组件是否处理 deleted 事件，弹窗都要收起，避免停留在"已删除"状态
      close()
    }, 500)
  } catch {
    // 失败提示由请求拦截器统一处理，复位等待重试
    state.value = 'idle'
  }
}
</script>

<style>
/* ===== 弹窗外壳（全局，供 teleport 使用） ===== */
.dd-dialog {
  background: #16171b;
  border: 1px solid #2a2b33;
  border-radius: 16px;
  overflow: hidden;
  box-shadow:
    0 24px 48px -12px rgba(0, 0, 0, 0.85),
    0 0 0 1px rgba(255, 255, 255, 0.07);
}
.dd-dialog .el-dialog__header { display: none; }
.dd-dialog .el-dialog__body { padding: 0; }
</style>

<style scoped>
.dd-topbar {
  height: 3px;
  background: linear-gradient(90deg, transparent, var(--af-primary), transparent);
  opacity: 0.9;
}

/* ===== Header ===== */
.dd-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 12px;
}
.dd-header-main { display: flex; align-items: flex-start; gap: 13px; min-width: 0; }
.dd-badge {
  position: relative;
  width: 44px; height: 44px; flex-shrink: 0;
  border-radius: 12px;
  background: rgba(255, 92, 51, 0.14);
  color: var(--af-primary);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 20px -3px rgba(255, 92, 51, 0.4);
}
.dd-badge-dot {
  position: absolute; top: -4px; right: -4px;
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--af-primary);
  animation: dd-ping 1.4s ease-out infinite;
}
@keyframes dd-ping {
  0% { transform: scale(1); opacity: 0.9; }
  80%, 100% { transform: scale(2.2); opacity: 0; }
}
.dd-header-text { min-width: 0; }
.dd-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dd-title-row h3 { margin: 0; color: var(--af-text); font-size: 17px; font-weight: 700; }
.dd-chip {
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 999px;
  color: var(--af-primary);
  background: rgba(255, 92, 51, 0.14);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  white-space: nowrap;
}
.dd-sub { margin: 5px 0 0; color: var(--af-text-3); font-size: 12px; line-height: 1.65; }
.dd-close {
  width: 30px; height: 30px; flex-shrink: 0;
  border: none; border-radius: 9px;
  background: var(--af-hover);
  color: var(--af-text-3);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.dd-close:hover { color: var(--af-text); background: #2f3038; }

/* ===== Body ===== */
.dd-body {
  padding: 4px 20px 6px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 待删除对象卡片 */
.dd-doc-card {
  background: #101114;
  border: 1px solid #26272e;
  border-radius: 11px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dd-doc-main { display: flex; align-items: flex-start; gap: 11px; min-width: 0; }
.dd-file-badge {
  width: 40px; height: 40px; flex-shrink: 0;
  border-radius: 10px;
  background: #26272e;
  color: var(--af-primary);
  display: flex; align-items: center; justify-content: center;
}
.dd-file-badge.md { color: var(--af-success); }
.dd-file-badge.other { color: var(--af-info); }
.dd-doc-info { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.dd-doc-name {
  color: var(--af-text);
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dd-doc-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  color: var(--af-text-3);
  font-size: 11px;
}
.dd-stage {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  background: #1c1d23;
  border-radius: 8px;
  padding: 6px 11px;
}
.dd-stage-left {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--af-text);
  font-size: 11px;
}
.dd-stage-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--af-primary);
  animation: dd-blink 1.4s ease-in-out infinite;
}
@keyframes dd-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}
.dd-stage-name { color: var(--af-primary); font-size: 11px; }

/* 级联影响 */
.dd-risk {
  background: #1c1d23;
  border-radius: 11px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dd-risk-head {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--af-primary);
  font-size: 12px;
  font-weight: 600;
}
.dd-risk ul {
  margin: 0;
  padding: 0 0 0 2px;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.dd-risk li {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  color: var(--af-text-2);
  font-size: 11px;
  line-height: 1.65;
}
.dd-risk li .el-icon { margin-top: 3px; color: var(--af-text-3); flex-shrink: 0; }
.dd-risk li.dim { color: var(--af-text-3); }
.dd-risk b { color: var(--af-text); }

/* 二次确认复选框 */
.dd-confirm {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 9px 11px;
  border-radius: 9px;
  background: rgba(38, 39, 46, 0.5);
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.dd-confirm:hover { background: #26272e; }
.dd-confirm input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.dd-checkbox {
  margin-top: 1px;
  width: 15px; height: 15px; flex-shrink: 0;
  border-radius: 4px;
  border: 1px solid #34353d;
  background: #101114;
  color: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.dd-confirm input:checked + .dd-checkbox {
  background: var(--af-primary);
  border-color: var(--af-primary);
  color: #3d0600;
}
.dd-confirm-text {
  color: var(--af-text-2);
  font-size: 12px;
  line-height: 1.6;
}
.dd-confirm:hover .dd-confirm-text { color: var(--af-text); }

/* ===== Footer ===== */
.dd-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 13px 20px;
  border-top: 1px solid #26272e;
}
.dd-btn {
  border: none;
  border-radius: 9px;
  background: var(--af-hover);
  color: var(--af-text);
  font-size: 12px;
  font-weight: 500;
  padding: 9px 16px;
  cursor: pointer;
  transition: background 0.15s;
}
.dd-btn:hover { background: #2f3038; }
.dd-danger {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: none;
  border-radius: 9px;
  background: #26272e;
  color: var(--af-text-3);
  font-size: 12px;
  font-weight: 600;
  padding: 9px 18px;
  cursor: not-allowed;
  opacity: 0.55;
  transition: all 0.2s;
}
.dd-danger.armed {
  background: var(--af-primary-gradient);
  color: #3d0600;
  opacity: 1;
  cursor: pointer;
  box-shadow: 0 0 22px -4px rgba(255, 92, 51, 0.55);
}
.dd-danger.armed:hover:not(:disabled) { filter: brightness(1.12); }
.dd-danger.armed:active:not(:disabled) { transform: scale(0.96); }
.dd-danger.done {
  background: var(--af-success);
  color: #062b18;
  opacity: 1;
  box-shadow: 0 0 20px -2px rgba(46, 204, 113, 0.45);
}
.spin { animation: dd-rotate 0.9s linear infinite; }
@keyframes dd-rotate {
  to { transform: rotate(360deg); }
}
</style>
