<template>
  <el-dialog
    :model-value="modelValue"
    width="570px"
    align-center
    :show-header="false"
    :show-close="false"
    class="dk-dialog"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @closed="reset"
  >
    <!-- 顶部危险氛围亮线 -->
    <div class="dk-topbar"></div>

    <!-- Header -->
    <div class="dk-header">
      <div class="dk-header-main">
        <div class="dk-badge">
          <el-icon :size="24"><Delete /></el-icon>
          <span class="dk-badge-dot"></span>
        </div>
        <div class="dk-header-text">
          <div class="dk-title-row">
            <h3>{{ $t('kb.kdTitle') }}</h3>
            <span class="dk-chip">{{ $t('kb.kdChip') }}</span>
          </div>
          <p class="dk-sub">{{ $t('kb.kdDesc') }}</p>
        </div>
      </div>
      <button class="dk-close" @click="close">
        <el-icon :size="16"><Close /></el-icon>
      </button>
    </div>

    <!-- Body -->
    <div class="dk-body">
      <!-- 知识库信息卡片（全部真实数据） -->
      <div class="dk-kb-card">
        <!-- 名称与徽章 -->
        <div class="dk-kb-top">
          <div class="dk-kb-name-row">
            <div class="dk-kb-icon">
              <el-icon :size="15"><Collection /></el-icon>
            </div>
            <span class="dk-kb-name" :title="kb?.name">{{ kb?.name }}</span>
            <span class="dk-vis" :class="kb?.visibility === 'shared' ? 'shared' : 'private'">
              {{ kb?.visibility === 'shared' ? $t('kb.typeShared') : $t('kb.typePrivate') }}
            </span>
          </div>
          <div class="dk-health">
            <span class="dk-health-dot"></span>
            <span>{{ $t('kb.kdNormal') }}</span>
          </div>
        </div>

        <!-- UID 与元信息 -->
        <div class="dk-meta">
          <div class="dk-uid">
            <span class="dk-uid-label">ID:</span>
            <span class="dk-uid-value">{{ kb?.uid }}</span>
            <button class="dk-copy" :title="$t('kb.kdCopy')" @click="copyUid">
              <el-icon :size="13"><component :is="copied ? Check : CopyDocument" /></el-icon>
            </button>
          </div>
          <div class="dk-meta-right">
            <span>{{ $t('kb.kdCreator') }}: <b>{{ kb?.creator || '-' }}</b></span>
            <span>{{ formatDate(kb?.createdAt) }}</span>
          </div>
        </div>

        <!-- 描述 -->
        <p v-if="kb?.description" class="dk-desc">{{ kb.description }}</p>

        <!-- 统计遥测 -->
        <div class="dk-stats">
          <div class="dk-stat">
            <span class="dk-stat-label">{{ $t('kb.kdStatDocs') }}</span>
            <span class="dk-stat-value">{{ stats?.document_count ?? '-' }} <i>{{ $t('kb.kdUnitDocs') }}</i></span>
          </div>
          <div class="dk-stat">
            <span class="dk-stat-label">{{ $t('kb.kdStatChunks') }}</span>
            <span class="dk-stat-value">{{ stats?.chunk_count ?? '-' }} <i>{{ $t('kb.kdUnitChunks') }}</i></span>
          </div>
          <div class="dk-stat">
            <span class="dk-stat-label">{{ $t('kb.kdStatCalls') }}</span>
            <span class="dk-stat-value">{{ statCalls }} <i>{{ $t('kb.kdUnitCalls') }}</i></span>
          </div>
          <div class="dk-stat">
            <span class="dk-stat-label">{{ $t('kb.kdStatSize') }}</span>
            <span class="dk-stat-value">{{ statSize }} <i>{{ statSizeUnit }}</i></span>
          </div>
        </div>
      </div>

      <!-- 销毁影响与数据处理声明 -->
      <div class="dk-risk">
        <div class="dk-risk-head">
          <el-icon :size="16"><Warning /></el-icon>
          <span>{{ $t('kb.kdRiskTitle') }}</span>
        </div>
        <div class="dk-risk-list">
          <div class="dk-risk-item">
            <span class="dk-risk-dot"></span>
            <span><b>{{ $t('kb.kdRiskData') }}</b>{{ riskDataBody }}</span>
          </div>
          <div class="dk-risk-item">
            <span class="dk-risk-dot"></span>
            <span><b>{{ $t('kb.kdRiskRetrieval') }}</b>{{ riskRetrievalBody }}</span>
          </div>
          <div class="dk-risk-item">
            <span class="dk-risk-dot"></span>
            <span><b>{{ $t('kb.kdRiskPerm') }}</b>{{ $t('kb.kdRiskPermBody') }}</span>
          </div>
        </div>
      </div>

      <!-- 名称验证 -->
      <div class="dk-verify">
        <label class="dk-verify-label" for="dk-confirm-name">{{ $t('kb.kdVerifyLabel') }}</label>
        <div class="dk-verify-hint">
          <span>{{ $t('kb.kdVerifyTarget') }}</span>
          <code class="dk-target" @click="fillName">{{ kb?.name }}</code>
          <span class="dk-verify-tip">{{ $t('kb.kdVerifyClick') }}</span>
        </div>
        <div class="dk-input-wrap">
          <input
            id="dk-confirm-name"
            v-model="confirmName"
            class="dk-input"
            type="text"
            :placeholder="$t('kb.kdVerifyPlaceholder', { name: kb?.name || '' })"
            autocomplete="off"
            spellcheck="false"
          />
          <el-icon class="dk-input-icon" :class="{ ok: nameMatched }" :size="17">
            <component :is="nameMatched ? CircleCheck : CircleClose" />
          </el-icon>
        </div>
        <!-- 二次确认复选框 -->
        <label class="dk-confirm">
          <input v-model="checked" type="checkbox" />
          <span class="dk-checkbox">
            <el-icon :size="11"><Check /></el-icon>
          </span>
          <span class="dk-confirm-text">{{ $t('kb.kdCheckbox') }}</span>
        </label>
      </div>
    </div>

    <!-- Footer -->
    <div class="dk-footer">
      <button class="dk-btn" type="button" @click="close">{{ $t('common.cancel') }}</button>
      <button
        class="dk-danger"
        type="button"
        :class="{ armed: canSubmit, loading: state === 'loading', done: state === 'done' }"
        :disabled="!canSubmit || state !== 'idle'"
        @click="submit"
      >
        <el-icon v-if="state === 'loading'" :size="15" class="spin"><Loading /></el-icon>
        <el-icon v-else-if="state === 'done'" :size="15"><Check /></el-icon>
        <el-icon v-else :size="15"><Delete /></el-icon>
        <span>
          {{ state === 'loading' ? $t('kb.kdSubmitting') : state === 'done' ? $t('kb.kdDone') : $t('kb.kdSubmit') }}
        </span>
      </button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Check, CircleCheck, CircleClose, Close, Collection, CopyDocument,
  Delete, Loading, Warning
} from '@element-plus/icons-vue'
import { deleteKnowledgeBase, getKnowledgeBaseStats, type KnowledgeBaseStats } from '@/api/knowledge'

/** 只依赖列表视图已有的字段（列表数据是本地映射后的视图模型，不含数据库审计字段） */
export interface DeleteKbTarget {
  uid: string
  name: string
  description: string
  creator: string
  createdAt: string
  visibility: 'shared' | 'private'
  permission: 'read' | 'manage' | null
}

const props = defineProps<{
  modelValue: boolean
  kb: DeleteKbTarget | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  /** 删除成功后触发，用于刷新列表 */
  deleted: []
}>()

const { t } = useI18n()

const stats = ref<KnowledgeBaseStats | null>(null)
const statsLoading = ref(false)
const confirmName = ref('')
const checked = ref(false)
const copied = ref(false)
const state = ref<'idle' | 'loading' | 'done'>('idle')

const close = () => emit('update:modelValue', false)

/** 打开时拉取真实统计数据 */
watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible || !props.kb) return
    stats.value = null
    statsLoading.value = true
    try {
      const { data } = await getKnowledgeBaseStats(props.kb.uid)
      stats.value = data
    } catch {
      // 统计加载失败时按空数据处理，不阻塞删除流程
      stats.value = null
    } finally {
      statsLoading.value = false
    }
  }
)

const nameMatched = computed(() => !!props.kb && confirmName.value.trim() === props.kb.name)
const canSubmit = computed(() => nameMatched.value && checked.value)

const statCalls = computed(() => {
  const n = stats.value?.retrieval_count
  return n == null ? '-' : n.toLocaleString()
})

const statSize = computed(() => {
  const bytes = stats.value?.storage_bytes ?? 0
  if (bytes <= 0) return '0'
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))}` : (bytes / 1024 / 1024).toFixed(1)
})
const statSizeUnit = computed(() => {
  const bytes = stats.value?.storage_bytes ?? 0
  if (bytes <= 0) return 'B'
  return bytes < 1024 * 1024 ? 'KB' : 'MB'
})

const riskDataBody = computed(() => {
  const docs = stats.value?.document_count ?? 0
  const chunks = stats.value?.chunk_count ?? 0
  if (docs === 0) return t('kb.kdRiskNoData')
  return t('kb.kdRiskDataBody', { docs, chunks })
})

const riskRetrievalBody = computed(() => {
  const calls = stats.value?.retrieval_count ?? 0
  return t('kb.kdRiskRetrievalBody', { calls })
})

const formatDate = (value?: string | null) => {
  if (!value) return '-'
  return value.replace('T', ' ').slice(0, 16)
}

const fillName = () => {
  if (props.kb) confirmName.value = props.kb.name
}

const copyUid = async () => {
  if (!props.kb) return
  try {
    await navigator.clipboard.writeText(props.kb.uid)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    // 剪贴板不可用时静默忽略
  }
}

const reset = () => {
  confirmName.value = ''
  checked.value = false
  stats.value = null
  copied.value = false
  state.value = 'idle'
}

const submit = async () => {
  const kb = props.kb
  if (!kb || !canSubmit.value || state.value !== 'idle') return
  state.value = 'loading'
  try {
    await deleteKnowledgeBase(kb.uid)
    state.value = 'done'
    setTimeout(() => {
      emit('deleted')
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
.dk-dialog {
  background: #16171b;
  border: 1px solid #2a2b33;
  border-radius: 16px;
  overflow: hidden;
  box-shadow:
    0 24px 64px -12px rgba(0, 0, 0, 0.85),
    0 0 0 1px rgba(255, 255, 255, 0.07);
}
.dk-dialog .el-dialog__header { display: none; }
.dk-dialog .el-dialog__body { padding: 0; }
</style>

<style scoped>
.dk-topbar {
  height: 3px;
  background: linear-gradient(90deg, rgba(255, 107, 107, 0.45), var(--af-primary), rgba(255, 107, 107, 0.3));
  opacity: 0.9;
}

/* ===== Header ===== */
.dk-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 12px;
}
.dk-header-main { display: flex; align-items: flex-start; gap: 13px; min-width: 0; }
.dk-badge {
  position: relative;
  width: 44px; height: 44px; flex-shrink: 0;
  border-radius: 12px;
  background: rgba(255, 92, 51, 0.14);
  color: var(--af-primary);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 20px -3px rgba(255, 92, 51, 0.4);
}
.dk-badge-dot {
  position: absolute; top: -4px; right: -4px;
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--af-primary);
  animation: dk-ping 1.4s ease-out infinite;
}
@keyframes dk-ping {
  0% { transform: scale(1); opacity: 0.9; }
  80%, 100% { transform: scale(2.2); opacity: 0; }
}
.dk-header-text { min-width: 0; }
.dk-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dk-title-row h3 { margin: 0; color: var(--af-text); font-size: 17px; font-weight: 700; }
.dk-chip {
  font-size: 10px;
  padding: 1px 8px;
  border-radius: 999px;
  color: var(--af-primary);
  background: rgba(255, 92, 51, 0.14);
  letter-spacing: 0.06em;
  white-space: nowrap;
}
.dk-sub { margin: 5px 0 0; color: var(--af-text-3); font-size: 12px; line-height: 1.65; }
.dk-close {
  width: 30px; height: 30px; flex-shrink: 0;
  border: none; border-radius: 9px;
  background: var(--af-hover);
  color: var(--af-text-3);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.dk-close:hover { color: var(--af-text); background: #2f3038; }

/* ===== Body ===== */
.dk-body {
  padding: 4px 20px 6px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 知识库卡片 */
.dk-kb-card {
  background: #1f2026;
  border: 1px solid #26272e;
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.dk-kb-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.dk-kb-name-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.dk-kb-icon {
  width: 24px; height: 24px; flex-shrink: 0;
  border-radius: 6px;
  background: #26272e;
  color: var(--af-primary);
  display: flex; align-items: center; justify-content: center;
}
.dk-kb-name {
  color: var(--af-text);
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dk-vis {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 4px;
  white-space: nowrap;
}
.dk-vis.shared { color: var(--af-info); background: #26272e; }
.dk-vis.private { color: var(--af-text-2); background: #26272e; }
.dk-health {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px;
  color: var(--af-text);
  background: #26272e;
  border-radius: 5px;
  padding: 2px 9px;
}
.dk-health-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--af-success);
}
.dk-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  background: #17181d;
  border-radius: 8px;
  padding: 6px 11px;
  color: var(--af-text-3);
  font-size: 11px;
}
.dk-uid { display: flex; align-items: center; gap: 5px; min-width: 0; }
.dk-uid-label { color: var(--af-text-3); }
.dk-uid-value {
  color: var(--af-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  user-select: all;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dk-copy {
  border: none; background: transparent;
  color: var(--af-text-3);
  cursor: pointer;
  padding: 2px;
  display: flex; align-items: center;
}
.dk-copy:hover { color: var(--af-primary); }
.dk-meta-right { display: flex; align-items: center; gap: 12px; white-space: nowrap; }
.dk-meta-right b { color: var(--af-text); font-weight: 500; }
.dk-desc {
  margin: 0;
  color: var(--af-text-2);
  font-size: 12px;
  line-height: 1.6;
}

/* 统计网格 */
.dk-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  padding-top: 2px;
}
.dk-stat {
  background: #17181d;
  border-radius: 8px;
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}
.dk-stat-label { color: var(--af-text-3); font-size: 10px; }
.dk-stat-value {
  margin-top: 3px;
  color: var(--af-text);
  font-size: 13px;
  font-weight: 600;
}
.dk-stat-value i {
  font-style: normal;
  font-weight: 400;
  font-size: 9px;
  color: var(--af-text-3);
}

/* 销毁影响 */
.dk-risk {
  background: #1c1d23;
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 9px;
}
.dk-risk-head {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--af-primary);
  font-size: 12px;
  font-weight: 600;
}
.dk-risk-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.dk-risk-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  color: var(--af-text-2);
  font-size: 11px;
  line-height: 1.65;
}
.dk-risk-item b { color: var(--af-text); font-weight: 600; }
.dk-risk-dot {
  margin-top: 7px;
  width: 5px; height: 5px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--af-primary);
}

/* 名称验证 */
.dk-verify {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 2px;
}
.dk-verify-label {
  color: var(--af-text);
  font-size: 12px;
  font-weight: 500;
}
.dk-verify-hint {
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--af-text-3);
  font-size: 11px;
}
.dk-target {
  padding: 2px 8px;
  border-radius: 5px;
  background: #26272e;
  color: var(--af-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  font-weight: 600;
  user-select: all;
  cursor: pointer;
}
.dk-target:hover { filter: brightness(1.2); }
.dk-verify-tip { color: var(--af-text-3); opacity: 0.75; }
.dk-input-wrap { position: relative; display: flex; align-items: center; }
.dk-input {
  width: 100%;
  box-sizing: border-box;
  background: #101114;
  border: 1px solid #2a2b33;
  border-radius: 11px;
  color: var(--af-text);
  font-size: 13px;
  padding: 10px 40px 10px 14px;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.dk-input::placeholder { color: var(--af-text-3); opacity: 0.55; }
.dk-input:focus {
  border-color: var(--af-primary);
  box-shadow: 0 0 0 1px rgba(255, 92, 51, 0.3);
}
.dk-input-icon {
  position: absolute;
  right: 12px;
  color: var(--af-text-3);
  opacity: 0.45;
}
.dk-input-icon.ok { color: var(--af-success); opacity: 1; }

/* 二次确认复选框 */
.dk-confirm {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 8px 11px;
  border-radius: 9px;
  background: rgba(38, 39, 46, 0.5);
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.dk-confirm:hover { background: #26272e; }
.dk-confirm input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.dk-checkbox {
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
.dk-confirm input:checked + .dk-checkbox {
  background: var(--af-primary);
  border-color: var(--af-primary);
  color: #3d0600;
}
.dk-confirm-text {
  color: var(--af-text-2);
  font-size: 12px;
  line-height: 1.6;
}
.dk-confirm:hover .dk-confirm-text { color: var(--af-text); }

/* ===== Footer ===== */
.dk-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 13px 20px;
  border-top: 1px solid #26272e;
}
.dk-btn {
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
.dk-btn:hover { background: #2f3038; }
.dk-danger {
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
.dk-danger.armed {
  background: var(--af-primary-gradient);
  color: #3d0600;
  opacity: 1;
  cursor: pointer;
  box-shadow: 0 0 22px -4px rgba(255, 92, 51, 0.55);
}
.dk-danger.armed:hover:not(:disabled) { filter: brightness(1.12); }
.dk-danger.armed:active:not(:disabled) { transform: scale(0.96); }
.dk-danger.done {
  background: var(--af-success);
  color: #062b18;
  opacity: 1;
  box-shadow: 0 0 20px -2px rgba(46, 204, 113, 0.45);
}
.spin { animation: dk-rotate 0.9s linear infinite; }
@keyframes dk-rotate {
  to { transform: rotate(360deg); }
}

@media (max-width: 640px) {
  .dk-stats { grid-template-columns: repeat(2, 1fr); }
}
</style>
