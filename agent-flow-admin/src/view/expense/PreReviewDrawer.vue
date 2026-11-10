<template>
  <el-drawer
    :model-value="modelValue"
    :title="title || $t('claims.drawer.title')"
    :size="drawerSize"
    class="pre-review-drawer"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @closed="handleClosed"
  >
    <div v-loading="loading" class="drawer-body">
      <template v-if="detail">
        <!-- ===== 报销单概要 ===== -->
        <div class="claim-summary">
          <div class="claim-no">{{ detail.claim_no }}</div>
          <div class="claim-title">{{ detail.title }}</div>
          <div class="claim-amount-row">
            <span class="claim-amount">¥{{ formatAmount(detail.total_amount) }}</span>
            <span class="status-pill" :class="statusClass(detail.status)">{{ statusLabel(detail.status) }}</span>
          </div>
          <div class="claim-meta">
            {{ detail.item_count }} {{ $t('claims.drawer.itemsUnit') }}
            <template v-if="detail.categories?.length"> · {{ detail.categories.join(' / ') }}</template>
          </div>
        </div>

        <!-- ===== AI 预审区 ===== -->
        <div class="review-section">
          <div class="review-head">
            <span class="review-title">
              <el-icon><MagicStick /></el-icon> {{ $t('claims.drawer.reviewTitle') }}
            </span>
            <!-- pending / running：显示刷新按钮，用户手动获取最新结果（聊天内详情无数字 id 时不展示） -->
            <el-button
              v-if="isReviewPending && claimId"
              size="small"
              type="primary"
              :loading="refreshing"
              @click="refreshReview"
            >
              <el-icon v-if="!refreshing"><Refresh /></el-icon>
              {{ $t('claims.drawer.refreshResult') }}
            </el-button>
          </div>

          <!-- 无预审记录 -->
          <div v-if="!review" class="review-empty">
            <el-empty :description="$t('claims.drawer.noReview')" :image-size="72" />
          </div>

          <!-- 排队 / 审查中 -->
          <div v-else-if="isReviewPending" class="review-running">
            <el-icon class="spin"><Loading /></el-icon>
            <p>{{ review.status === 'running' ? $t('claims.drawer.reviewRunning') : $t('claims.drawer.reviewQueued') }}</p>
            <span>{{ $t('claims.drawer.reviewRunningTip') }}</span>
          </div>

          <!-- 审查失败 -->
          <div v-else-if="review.status === 'failed'" class="review-failed">
            <el-alert type="error" :title="$t('claims.drawer.reviewFailed')" :closable="false" />
            <p class="error-text">{{ review.error_message }}</p>
            <div class="failed-actions">
              <!-- 有数字 id 才能重新投递初审任务（聊天内详情无 id） -->
              <el-button
                v-if="claimId"
                type="primary"
                size="small"
                :loading="retrying"
                @click="retryReview"
              >
                {{ $t('claims.drawer.retryReview') }}
              </el-button>
              <el-button size="small" :loading="refreshing" @click="refreshReview">
                <el-icon v-if="!refreshing"><Refresh /></el-icon> {{ $t('claims.drawer.retry') }}
              </el-button>
            </div>
          </div>

          <!-- 审查完成 -->
          <template v-else>
            <div class="result-row">
              <span class="result-pill" :class="resultClass(review.result)">{{ resultLabel(review.result) }}</span>
              <span v-if="review.risk_level" class="risk-pill" :class="'risk-' + review.risk_level">
                {{ $t('claims.drawer.risk') }} {{ riskLabel(review.risk_level) }}
              </span>
            </div>

            <div v-if="review.summary" class="review-summary">{{ review.summary }}</div>

            <div v-if="problems.length" class="problem-list">
              <div class="section-label">{{ $t('claims.drawer.problems') }}</div>
              <div v-for="(p, i) in problems" :key="i" class="problem-item">
                <el-icon><WarningFilled /></el-icon><span>{{ p }}</span>
              </div>
            </div>

            <div v-if="evidence" class="evidence-box">
              <div class="section-label">{{ $t('claims.drawer.evidence') }}</div>
              <p>{{ evidence }}</p>
            </div>

            <div v-if="extractedKeys.length" class="extracted-box">
              <div class="section-label">{{ $t('claims.drawer.extracted') }}</div>
              <div v-for="key in extractedKeys" :key="key" class="extracted-item">
                <span>{{ key }}</span><b>{{ String(extractedData[key]) }}</b>
              </div>
            </div>

            <div class="review-meta">
              <span v-if="review.model_name">{{ review.model_name }}</span>
              <span v-if="review.finished_at">{{ formatTime(review.finished_at) }}</span>
            </div>
          </template>
        </div>

        <!-- ===== 人工审核结果（申请人可见审批结论与审批人附言） ===== -->
        <div v-if="approvalRecord" class="approval-section">
          <div class="review-head">
            <span class="review-title">
              <el-icon><Stamp /></el-icon> {{ $t('claims.drawer.humanReview') }}
            </span>
            <span class="result-pill" :class="approvalRecord.status === 'approved' ? 'r-pass' : 'r-fail'">
              {{ approvalRecord.status === 'approved' ? $t('claims.drawer.approve') : $t('claims.drawer.reject') }}
            </span>
          </div>
          <div class="approval-meta">
            <span>{{ $t('claims.drawer.approverName') }}：{{ approverName }}</span>
            <span v-if="approvalRecord.decided_at">{{ formatTime(approvalRecord.decided_at) }}</span>
          </div>
          <div class="approval-comment">
            <span class="section-label">{{ $t('claims.drawer.approverComment') }}</span>
            <p :class="{ 'comment-empty': !approvalRecord.comment }">
              {{ approvalRecord.comment || $t('claims.drawer.noComment') }}
            </p>
          </div>
        </div>

        <!-- ===== 费用明细 ===== -->
        <div v-if="detail.items?.length" class="items-section">
          <div class="section-label">{{ $t('claims.drawer.expenseItems') }}</div>
          <div v-for="item in detail.items" :key="item.id" class="expense-item">
            <div class="item-main">
              <div class="item-category">{{ item.category }}</div>
              <div class="item-desc">{{ item.description || formatDate(item.expense_date) }}</div>
            </div>
            <span class="item-amount">¥{{ formatAmount(item.amount) }}</span>
          </div>
        </div>

        <!-- ===== 发票凭证（预签名 URL，约 30 分钟有效） ===== -->
        <div v-if="detail.attachments?.length" class="invoices-section">
          <div class="section-label">{{ $t('claims.drawer.invoices') }}</div>
          <div class="invoice-grid">
            <template v-for="att in detail.attachments" :key="att.id">
              <el-image
                v-if="att.preview_url && isImageAttachment(att)"
                class="invoice-thumb"
                :src="thumbSrc(att)"
                :preview-src-list="imageUrls"
                :initial-index="imageUrls.indexOf(att.preview_url)"
                preview-teleported
                hide-on-click-modal
                fit="cover"
                loading="lazy"
                @error="onThumbError(att)"
              />
              <div
                v-else-if="att.preview_url"
                class="invoice-file"
                :title="att.original_filename"
                @click="openAttachment(att)"
              >
                <el-icon :size="18"><Document /></el-icon>
                <span>{{ att.original_filename }}</span>
              </div>
              <div v-else class="invoice-file is-off" :title="att.original_filename">
                <el-icon :size="18"><Document /></el-icon>
                <span>{{ att.original_filename }}</span>
              </div>
            </template>
          </div>
        </div>

        <!-- ===== 管理员审批操作 ===== -->
        <div v-if="mode === 'admin' && detail.status === 'pending_approval'" class="decision-section">
          <div class="section-label">{{ $t('claims.drawer.decisionTitle') }}</div>
          <!-- AI 预审拦截：无需人工复审，操作置灰 -->
          <el-alert
            v-if="aiBlocked"
            type="warning"
            :title="$t('claims.admin.blockedTip')"
            :closable="false"
            class="blocked-alert"
          />
          <el-input
            v-model="comment"
            type="textarea"
            :rows="3"
            maxlength="2000"
            :disabled="aiBlocked"
            :placeholder="$t('claims.drawer.commentPlaceholder')"
          />
          <div class="decision-actions">
            <el-button
              :loading="deciding === 'rejected'"
              :disabled="aiBlocked"
              class="reject-btn"
              @click="decide('rejected')"
            >
              {{ $t('claims.drawer.reject') }}
            </el-button>
            <el-button
              type="primary"
              :loading="deciding === 'approved'"
              :disabled="aiBlocked"
              @click="decide('approved')"
            >
              {{ $t('claims.drawer.approve') }}
            </el-button>
          </div>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { MagicStick, Refresh, Loading, WarningFilled, Stamp, Document } from '@element-plus/icons-vue'
import {
  decideApprovalApi,
  getClaimDetailApi,
  getLatestPreReviewApi,
  isImageAttachment,
  retryPreReviewApi,
  type ClaimAttachment,
  type ExpenseClaimDetail,
  type PreReviewInfo
} from '@/api/expense'

const props = defineProps<{
  modelValue: boolean
  /** 详情/审批接口按 claim_no 查询 */
  claimNo: string | null
  /** AI 预审最新结果接口仍按数字 id 查询 */
  claimId: number | null
  mode?: 'employee' | 'admin'
  /** 自定义抽屉标题（聊天内打开时用「报销单详情」） */
  title?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'decided'): void
}>()

const { t } = useI18n()
const loading = ref(false)
const refreshing = ref(false)
const retrying = ref(false)
const detail = ref<ExpenseClaimDetail | null>(null)
const comment = ref('')
const deciding = ref<'approved' | 'rejected' | null>(null)

const review = computed<PreReviewInfo | null>(() => detail.value?.pre_review ?? null)

// ===== 抽屉宽度自适应：窄屏（手机）占满全屏，避免左侧被截断 =====
const narrowMql = window.matchMedia('(max-width: 640px)')
const isNarrowScreen = ref(narrowMql.matches)
const onNarrowChange = (e: MediaQueryListEvent) => { isNarrowScreen.value = e.matches }
onMounted(() => narrowMql.addEventListener('change', onNarrowChange))
onBeforeUnmount(() => narrowMql.removeEventListener('change', onNarrowChange))
const drawerSize = computed(() => (isNarrowScreen.value ? '100%' : '480px'))
const isReviewPending = computed(
  () => review.value?.status === 'pending' || review.value?.status === 'running'
)
const problems = computed(() => review.value?.result_data?.problems ?? [])
const evidence = computed(() => review.value?.result_data?.evidence ?? '')
const extractedData = computed(() => review.value?.result_data?.extracted_data ?? {})
const extractedKeys = computed(() => Object.keys(extractedData.value))

// AI 预审拦截（completed + fail）：不需要人工复审
const aiBlocked = computed(
  () => review.value?.status === 'completed' && review.value?.result === 'fail'
)

// ===== 人工审核结果 =====
const approvalRecord = computed(() => {
  const records = detail.value?.approvals ?? []
  return records.find((r) => r.status === 'approved' || r.status === 'rejected') ?? null
})
const approverName = computed(() => {
  const approver = approvalRecord.value?.approver
  return approver?.nickname || approver?.username || '-'
})

// ===== 发票凭证 =====
const imageUrls = computed(() =>
  (detail.value?.attachments ?? [])
    .filter((a) => a.preview_url && isImageAttachment(a))
    .map((a) => a.preview_url!)
)
const openAttachment = (a: ClaimAttachment) => {
  if (a.preview_url) window.open(a.preview_url, '_blank')
}

/** 缩略图优先用后端预生成的小图（原图常达数 MB），历史附件缺失时回退原图 */
const thumbFailed = ref<Set<string>>(new Set())
const thumbSrc = (a: ClaimAttachment) =>
  !a.thumb_url || thumbFailed.value.has(a.thumb_url) ? (a.preview_url ?? '') : a.thumb_url
const onThumbError = (a: ClaimAttachment) => {
  if (a.thumb_url && !thumbFailed.value.has(a.thumb_url)) thumbFailed.value.add(a.thumb_url)
}

const loadDetail = async () => {
  if (!props.claimNo) return
  loading.value = true
  try {
    const res = await getClaimDetailApi(props.claimNo)
    detail.value = res.data
  } finally {
    loading.value = false
  }
}

// 手动刷新最新预审结果（pending / running / failed 时可用）
const refreshReview = async () => {
  if (!props.claimId) return
  refreshing.value = true
  try {
    const res = await getLatestPreReviewApi(props.claimId)
    if (detail.value) {
      detail.value = { ...detail.value, pre_review: res.data.review }
    }
  } finally {
    refreshing.value = false
  }
}

// 初审失败后重新投递一次初审任务
const retryReview = async () => {
  if (!props.claimId) return
  retrying.value = true
  try {
    await retryPreReviewApi(props.claimId)
    ElMessage.success(t('claims.drawer.retrySubmitted'))
    await loadDetail()
  } finally {
    retrying.value = false
  }
}

const decide = async (decision: 'approved' | 'rejected') => {
  if (!props.claimNo || aiBlocked.value) return
  deciding.value = decision
  try {
    await decideApprovalApi(props.claimNo, { decision, comment: comment.value || null })
    ElMessage.success(t(decision === 'approved' ? 'claims.drawer.approveOk' : 'claims.drawer.rejectOk'))
    emit('decided')
    emit('update:modelValue', false)
  } finally {
    deciding.value = null
  }
}

const handleClosed = () => {
  detail.value = null
  comment.value = ''
}

watch(
  () => [props.modelValue, props.claimNo],
  ([visible]) => {
    if (visible && props.claimNo) loadDetail()
  }
)

// ===== 展示辅助 =====
const formatAmount = (v: string) => Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const formatTime = (v: string) => (v ? new Date(v).toLocaleString('zh-CN', { hour12: false }) : '')
const formatDate = (v: string | null) => (v ? new Date(v).toLocaleDateString('zh-CN') : '-')

const statusLabel = (s: string) => t(`claims.status.${s}`)
const statusClass = (s: string) => {
  const map: Record<string, string> = {
    draft: 's-info', needs_info: 's-warn', pending_approval: 's-warn',
    processing: 's-info', approved: 's-ok', rejected: 's-fail',
    completed: 's-ok', failed: 's-fail'
  }
  return map[s] ?? 's-info'
}
const resultLabel = (r: string | null) => (r ? t(`claims.result.${r}`) : '-')
const resultClass = (r: string | null) =>
  r === 'pass' ? 'r-pass' : r === 'fail' ? 'r-fail' : 'r-manual'
const riskLabel = (r: string) => t(`claims.risk.${r}`)
</script>

<style scoped>
.drawer-body { display: flex; flex-direction: column; gap: 16px; padding: 0 4px; }

/* ===== 报销单概要 ===== */
.claim-summary {
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 14px 16px;
}
.claim-no { color: var(--af-text-3); font-size: 11px; margin-bottom: 4px; }
.claim-title { color: var(--af-text); font-size: 15px; font-weight: 700; margin-bottom: 10px; }
.claim-amount-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.claim-amount { color: var(--af-primary); font-size: 22px; font-weight: 800; }
.claim-meta { color: var(--af-text-3); font-size: 11px; }

.status-pill { font-size: 11px; border-radius: 6px; padding: 3px 10px; }
.s-ok { color: var(--af-success); background: var(--af-success-soft); }
.s-warn { color: var(--af-warning); background: var(--af-warning-soft); }
.s-info { color: var(--af-info); background: var(--af-info-soft); }
.s-fail { color: var(--af-danger); background: var(--af-danger-soft); }

/* ===== AI 预审区 ===== */
.review-section {
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 14px 16px;
}
.review-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.review-title { display: inline-flex; align-items: center; gap: 6px; color: var(--af-text); font-size: 13px; font-weight: 700; }
.review-title .el-icon { color: var(--af-primary); }

.review-running { text-align: center; padding: 18px 0 10px; }
.review-running .spin { font-size: 26px; color: var(--af-primary); animation: spin 1.2s linear infinite; }
.review-running p { color: var(--af-text); font-size: 13px; margin: 10px 0 4px; }
.review-running span { color: var(--af-text-3); font-size: 11px; }
@keyframes spin { to { transform: rotate(360deg); } }

.review-failed { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
.failed-actions { display: flex; gap: 8px; }
.error-text { color: var(--af-text-3); font-size: 11px; line-height: 1.6; word-break: break-all; }

.result-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.result-pill { font-size: 12px; font-weight: 700; border-radius: 7px; padding: 4px 12px; }
.r-pass { color: var(--af-success); background: var(--af-success-soft); }
.r-fail { color: var(--af-danger); background: var(--af-danger-soft); }
.r-manual { color: var(--af-warning); background: var(--af-warning-soft); }
.risk-pill { font-size: 11px; border-radius: 6px; padding: 3px 10px; }
.risk-high { color: var(--af-danger); background: var(--af-danger-soft); }
.risk-medium { color: var(--af-warning); background: var(--af-warning-soft); }
.risk-low { color: var(--af-info); background: var(--af-info-soft); }
.risk-none { color: var(--af-text-3); background: var(--af-hover); }

.review-summary { color: var(--af-text-2); font-size: 12px; line-height: 1.7; margin-bottom: 10px; }

.section-label { color: var(--af-text-3); font-size: 11px; margin-bottom: 8px; }

.problem-list { margin-bottom: 10px; }
.problem-item {
  display: flex; align-items: flex-start; gap: 7px;
  color: var(--af-warning); font-size: 12px; line-height: 1.6;
  background: var(--af-warning-soft);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
}
.problem-item .el-icon { flex-shrink: 0; margin-top: 2px; }

.evidence-box { margin-bottom: 10px; }
.evidence-box p {
  color: var(--af-text-2); font-size: 12px; line-height: 1.7;
  background: var(--af-hover); border-radius: 8px; padding: 9px 11px;
}

.extracted-box { margin-bottom: 10px; }
.extracted-item {
  display: flex; justify-content: space-between; gap: 10px;
  color: var(--af-text-2); font-size: 12px;
  border-bottom: 1px dashed var(--af-border-soft);
  padding: 6px 2px;
}
.extracted-item b { color: var(--af-text); font-weight: 600; word-break: break-all; text-align: right; }

.review-meta { display: flex; justify-content: space-between; color: var(--af-text-3); font-size: 10px; margin-top: 6px; }

/* ===== 人工审核结果 ===== */
.approval-section {
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 14px 16px;
}
.approval-section .review-head { margin-bottom: 8px; }
.approval-meta {
  display: flex; justify-content: space-between; gap: 10px;
  color: var(--af-text-3); font-size: 11px; margin-bottom: 10px;
}
.approval-comment p {
  color: var(--af-text); font-size: 12px; line-height: 1.7;
  background: var(--af-hover); border-radius: 8px; padding: 9px 11px;
  white-space: pre-wrap; word-break: break-word;
}
.approval-comment p.comment-empty { color: var(--af-text-3); }

/* ===== 费用明细 ===== */
.items-section { padding: 0 2px; }
.expense-item {
  display: flex; align-items: center; gap: 10px;
  border-bottom: 1px solid var(--af-border-soft);
  padding: 9px 2px;
}
.expense-item:last-child { border-bottom: none; }
.item-main { flex: 1; min-width: 0; }
.item-category { color: var(--af-text); font-size: 12px; font-weight: 600; }
.item-desc { color: var(--af-text-3); font-size: 11px; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-amount { color: var(--af-text); font-size: 13px; font-weight: 700; flex-shrink: 0; }

/* ===== 发票凭证 ===== */
.invoice-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(72px, 1fr));
  gap: 8px;
}
.invoice-thumb {
  width: 100%;
  aspect-ratio: 1 / 1;
  border-radius: 8px;
  border: 1px solid var(--af-border-soft);
  cursor: zoom-in;
  background: var(--af-hover);
}
.invoice-file {
  aspect-ratio: auto;
  min-height: 56px;
  border-radius: 8px;
  border: 1px dashed var(--af-border-soft);
  background: var(--af-hover);
  color: var(--af-text-2);
  cursor: pointer;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 4px;
  padding: 8px 6px;
  transition: all 0.15s;
}
.invoice-file span {
  font-size: 10px;
  max-width: 100%;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.invoice-file:hover { color: var(--af-primary); border-color: rgba(255, 92, 51, 0.4); }
.invoice-file.is-off { cursor: default; opacity: 0.6; }
.invoice-file.is-off:hover { color: var(--af-text-2); border-color: var(--af-border-soft); }

/* ===== 审批操作 ===== */
.decision-section { padding: 0 2px 8px; }
.blocked-alert { margin-bottom: 10px; }
.decision-actions { display: flex; gap: 10px; margin-top: 12px; }
.decision-actions .el-button { flex: 1; }
.reject-btn {
  color: var(--af-danger);
  background: var(--af-danger-soft);
  border: 1px solid rgba(255, 77, 79, 0.35);
}
.reject-btn:hover { color: var(--af-danger); border-color: var(--af-danger); }
</style>
