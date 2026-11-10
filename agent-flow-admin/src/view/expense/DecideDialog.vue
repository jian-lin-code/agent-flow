<template>
  <el-dialog
    :model-value="modelValue"
    width="540px"
    align-center
    :show-header="false"
    :show-close="false"
    class="decide-dialog"
    modal-class="decide-modal"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @closed="reset"
  >
    <!-- 顶部状态光晕饰条 -->
    <div class="dc-topbar" :class="isReject ? 'is-reject' : 'is-approve'"></div>

    <!-- 弹窗 Header -->
    <div class="dc-header">
      <div class="dc-header-main">
        <!-- 动态状态胶囊图标 -->
        <div class="dc-icon" :class="isReject ? 'i-reject' : 'i-approve'">
          <el-icon :size="22"><CircleClose v-if="isReject" /><CircleCheck v-else /></el-icon>
        </div>
        <div>
          <div class="dc-title-row">
            <h3>{{ isReject ? t('claims.admin.rejectTitle') : t('claims.admin.approveTitle') }}</h3>
            <span class="dc-badge" :class="isReject ? 'b-reject' : 'b-approve'">
              {{ isReject ? t('claims.admin.badgeReject') : t('claims.admin.badgePass') }}
            </span>
          </div>
          <p class="dc-sub">{{ isReject ? t('claims.admin.rejectSub') : t('claims.admin.approveSub') }}</p>
        </div>
      </div>
      <!-- 关闭按钮 -->
      <button class="dc-close" @click="close">
        <el-icon :size="16"><Close /></el-icon>
      </button>
    </div>

    <!-- 弹窗 Body -->
    <div class="dc-body">
      <!-- 核心单据业务摘要卡片 -->
      <div class="dc-card">
        <div class="dc-card-glow"></div>
        <div class="dc-card-head">
          <div class="dc-no">
            <el-icon :size="16"><Tickets /></el-icon>
            <span>{{ claim?.claim_no }}</span>
            <button class="dc-copy" :title="t('claims.admin.copyHint')" @click="copyNo">
              <el-icon :size="14"><DocumentCopy /></el-icon>
            </button>
          </div>
          <span class="dc-time"><i></i>{{ formatTime(claim?.submitted_at) }}</span>
        </div>

        <!-- 关键数据三列栅格 -->
        <div class="dc-grid">
          <div>
            <div class="dc-label">{{ t('claims.admin.categoryLabel') }}</div>
            <div class="dc-value">
              <span class="dot"></span>
              <span class="dc-truncate">{{ categoriesText }}</span>
            </div>
          </div>
          <div>
            <div class="dc-label">{{ t('claims.admin.applicantLabel') }}</div>
            <div class="dc-value">
              <span class="avatar">{{ avatarChar }}</span>
              {{ applicantName }}
            </div>
          </div>
          <div>
            <div class="dc-label">{{ t('claims.admin.amountLabel') }}</div>
            <div class="dc-amount"><span>¥</span>{{ amountText }}</div>
          </div>
        </div>

        <!-- 嵌入 AI 预审合规指示条 -->
        <div class="dc-ai">
          <div class="dc-ai-left">
            <span class="ai-pill" :class="aiClass">
              <el-icon :size="12"><MagicStick /></el-icon>
              {{ aiLabel }}
            </span>
            <span class="ai-summary" v-if="aiSummary" :title="aiSummary">{{ aiSummary }}</span>
          </div>
          <span class="dc-count">{{ t('claims.admin.detailCount', { n: claim?.item_count ?? 0 }) }}</span>
        </div>
      </div>

      <!-- 审批意见区 -->
      <div>
        <div class="dc-opinion-head">
          <label>
            {{ t('claims.admin.opinionLabel') }}
            <em>({{ t('claims.admin.opinionOptional') }})</em>
          </label>
          <span class="dc-charcount">{{ comment.length }} / 200</span>
        </div>

        <!-- 快捷常用标签 -->
        <div class="dc-tags">
          <button v-for="tag in quickTags" :key="tag" type="button" @click="setOpinion(tag)">
            + {{ tag }}
          </button>
        </div>

        <textarea
          v-model="comment"
          maxlength="200"
          rows="3"
          class="dc-textarea"
          :placeholder="t('claims.admin.opinionPlaceholder')"
        ></textarea>
      </div>
    </div>

    <!-- 弹窗 Footer 动作条 -->
    <div class="dc-footer">
      <!-- 次要操作：切换决策入口 -->
      <button type="button" class="dc-switch" :class="isReject ? 'sw-approve' : 'sw-reject'" @click="toggleDecision">
        <el-icon :size="15"><CircleCheck v-if="isReject" /><CircleClose v-else /></el-icon>
        {{ isReject ? t('claims.admin.switchApprove') : t('claims.admin.switchReject') }}
      </button>

      <!-- 主要操作动作组 -->
      <div class="dc-footer-main">
        <button type="button" class="dc-cancel" @click="close">{{ t('common.cancel') }}</button>
        <button type="button" class="dc-confirm" :disabled="confirmDisabled" @click="confirm">
          {{ isReject ? t('claims.admin.confirmReject') : t('claims.admin.confirmApprove') }}
        </button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { copyWithToast } from '@/utils/clipboard'
import { CircleCheck, CircleClose, Close, DocumentCopy, Tickets, MagicStick } from '@element-plus/icons-vue'
import type { ExpenseClaimItem } from '@/api/expense'

const props = defineProps<{
  modelValue: boolean
  /** 打开时的初始决策 */
  decision: 'approved' | 'rejected'
  claim: ExpenseClaimItem | null
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'confirm', decision: 'approved' | 'rejected', comment: string | null): void
}>()

const { t } = useI18n()

// 内部模式：footer 左侧按钮可随时切换通过/驳回
const mode = ref<'approved' | 'rejected'>('approved')
const comment = ref('')

watch(
  () => props.modelValue,
  (v) => {
    if (v) mode.value = props.decision
  }
)

const isReject = computed(() => mode.value === 'rejected')

const quickTags = computed(() =>
  isReject.value
    ? [t('claims.admin.tagReject1'), t('claims.admin.tagReject2'), t('claims.admin.tagReject3')]
    : [t('claims.admin.tagApprove1'), t('claims.admin.tagApprove2'), t('claims.admin.tagApprove3')]
)

const categoriesText = computed(() => {
  const c = props.claim
  if (!c) return '-'
  return c.categories?.length ? c.categories.join(' / ') : c.title || '-'
})

const applicantName = computed(() => {
  const a = props.claim?.applicant
  return a?.nickname || a?.username || '-'
})

const avatarChar = computed(() => applicantName.value.slice(0, 1))

const amountText = computed(() => {
  const v = props.claim?.total_amount
  return v ? Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '-'
})

const formatTime = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString('zh-CN', { hour12: false }).replaceAll('/', '-') : '-'

// AI 预审指示条
const aiLabel = computed(() => {
  const r = props.claim?.pre_review
  if (!r || r.status !== 'completed' || !r.result) return t('claims.admin.aiNone')
  return r.result === 'pass' ? t('claims.admin.aiPassed') : r.result === 'fail' ? t('claims.admin.aiFailed') : t('claims.admin.aiManual')
})
const aiClass = computed(() => {
  const r = props.claim?.pre_review
  if (!r || r.status !== 'completed' || !r.result) return 'ai-none'
  return r.result === 'pass' ? 'ai-pass' : r.result === 'fail' ? 'ai-fail' : 'ai-manual'
})
const aiSummary = computed(() => props.claim?.pre_review?.summary || '')

const copyNo = async () => {
  const no = props.claim?.claim_no
  if (!no) return
  await copyWithToast(no, t('claims.admin.copied'), t('claims.admin.copyFailed'))
}

const toggleDecision = () => {
  mode.value = isReject.value ? 'approved' : 'rejected'
}

const setOpinion = (text: string) => {
  comment.value = text
}

const confirmDisabled = computed(() => isReject.value && !comment.value.trim())

const confirm = () => {
  if (confirmDisabled.value || props.loading) return
  emit('confirm', mode.value, comment.value.trim() || null)
}

const close = () => emit('update:modelValue', false)

const reset = () => {
  comment.value = ''
  mode.value = props.decision
}
</script>

<!-- el-dialog 默认 teleport 到 body，需用全局样式 -->
<style>
/* ===== 遮罩：深色 + 毛玻璃 ===== */
.decide-modal {
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(8px);
}

/* ===== 弹窗容器：严格按设计稿 ===== */
.decide-dialog {
  background: #16171b;
  border: 1px solid #2a2b33;
  border-radius: 16px;
  overflow: hidden;
  box-shadow:
    0 24px 60px -12px rgba(0, 0, 0, 0.75),
    0 0 0 1px rgba(255, 255, 255, 0.07),
    0 0 40px -10px rgba(255, 87, 51, 0.15);
}
.decide-dialog .el-dialog__header { display: none; }
.decide-dialog .el-dialog__body { padding: 0; }

/* 顶部状态光晕饰条 */
.dc-topbar { height: 4px; width: 100%; }
.dc-topbar.is-approve { background: linear-gradient(90deg, rgba(16, 185, 129, 0.8), #ff5733 55%, rgba(255, 87, 51, 0.4)); }
.dc-topbar.is-reject { background: linear-gradient(90deg, rgba(244, 63, 94, 0.8), #ff5733 55%, rgba(255, 87, 51, 0.4)); }

/* ===== Header ===== */
.dc-header {
  padding: 22px 24px 16px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgba(42, 43, 51, 0.7);
}
.dc-header-main { display: flex; align-items: center; gap: 14px; }
.dc-icon {
  width: 40px; height: 40px;
  border-radius: 12px;
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.dc-icon.i-approve { background: rgba(16, 185, 129, 0.14); border: 1px solid rgba(16, 185, 129, 0.3); color: #34d399; }
.dc-icon.i-reject { background: rgba(244, 63, 94, 0.14); border: 1px solid rgba(244, 63, 94, 0.3); color: #fb7185; }

.dc-title-row { display: flex; align-items: center; gap: 8px; }
.dc-title-row h3 { color: #fff; font-size: 18px; font-weight: 700; letter-spacing: -0.3px; margin: 0; }
.dc-badge {
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 600;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  border: 1px solid transparent;
}
.dc-badge.b-approve { background: rgba(16, 185, 129, 0.1); color: #34d399; border-color: rgba(16, 185, 129, 0.25); }
.dc-badge.b-reject { background: rgba(244, 63, 94, 0.1); color: #fb7185; border-color: rgba(244, 63, 94, 0.25); }
.dc-sub { color: #94a3b8; font-size: 12px; margin: 4px 0 0; line-height: 1.5; }

.dc-close {
  width: 32px; height: 32px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
  flex-shrink: 0;
}
.dc-close:hover { color: #e2e8f0; background: #1f2026; border-color: #2a2b33; }

/* ===== Body ===== */
.dc-body { padding: 24px; display: flex; flex-direction: column; gap: 16px; }

/* 摘要卡片 */
.dc-card {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  background: rgba(31, 32, 38, 0.8);
  border: 1px solid #2a2b33;
  padding: 16px;
}
.dc-card-glow {
  position: absolute;
  right: 0; top: 0;
  width: 128px; height: 128px;
  background: rgba(255, 87, 51, 0.05);
  border-radius: 9999px;
  filter: blur(32px);
  pointer-events: none;
}
.dc-card-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(42, 43, 51, 0.6);
}
.dc-no { display: flex; align-items: center; gap: 8px; min-width: 0; }
.dc-no > .el-icon { color: #94a3b8; flex-shrink: 0; }
.dc-no span {
  color: #cbd5e1;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px; font-weight: 600;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dc-copy {
  background: none; border: none; padding: 0;
  color: #64748b; cursor: pointer;
  display: inline-flex;
  transition: color 0.15s;
  flex-shrink: 0;
}
.dc-copy:hover { color: #ff5733; }
.dc-time {
  display: inline-flex; align-items: center; gap: 6px;
  color: #94a3b8; font-size: 12px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.dc-time i { width: 6px; height: 6px; border-radius: 9999px; background: #64748b; }

/* 三列栅格 */
.dc-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.dc-label { color: #94a3b8; font-size: 11px; font-weight: 500; margin-bottom: 4px; }
.dc-value {
  color: #f1f5f9; font-size: 13px; font-weight: 600;
  display: flex; align-items: center; gap: 6px;
  min-width: 0;
}
.dc-truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dot { width: 6px; height: 6px; border-radius: 9999px; background: #ff5733; flex-shrink: 0; }
.avatar {
  width: 16px; height: 16px; border-radius: 9999px;
  background: rgba(255, 87, 51, 0.2);
  color: #ff5733;
  font-size: 9px; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.dc-amount {
  color: #ff5733;
  font-size: 16px; font-weight: 700;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
  display: flex; align-items: baseline; gap: 1px;
}
.dc-amount span { font-size: 12px; }

/* AI 预审指示条 */
.dc-ai {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid rgba(42, 43, 51, 0.5);
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.dc-ai-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
.ai-pill {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px; font-weight: 500;
  white-space: nowrap;
  border: 1px solid transparent;
  flex-shrink: 0;
}
.ai-pill.ai-pass { background: rgba(16, 185, 129, 0.1); color: #34d399; border-color: rgba(16, 185, 129, 0.2); }
.ai-pill.ai-fail { background: rgba(244, 63, 94, 0.1); color: #fb7185; border-color: rgba(244, 63, 94, 0.2); }
.ai-pill.ai-manual { background: rgba(245, 166, 35, 0.1); color: #fbbf24; border-color: rgba(245, 166, 35, 0.2); }
.ai-pill.ai-none { background: rgba(255, 255, 255, 0.04); color: #94a3b8; border-color: rgba(255, 255, 255, 0.14); }
.ai-summary {
  color: #94a3b8; font-size: 11px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  min-width: 0;
}
.dc-count { color: #64748b; font-size: 11px; font-family: 'JetBrains Mono', ui-monospace, monospace; flex-shrink: 0; }

/* 审批意见区 */
.dc-opinion-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.dc-opinion-head label { color: #cbd5e1; font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
.dc-opinion-head label em { color: #64748b; font-size: 11px; font-weight: 400; font-style: normal; }
.dc-charcount { color: #64748b; font-size: 11px; font-family: 'JetBrains Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }

.dc-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.dc-tags button {
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 8px;
  background: #1f2026;
  border: 1px solid #2a2b33;
  color: #cbd5e1;
  cursor: pointer;
  transition: all 0.15s;
}
.dc-tags button:hover { background: rgba(255, 87, 51, 0.12); color: #ff5733; border-color: rgba(255, 87, 51, 0.4); }

.dc-textarea {
  width: 100%;
  background: #111215;
  border: 1px solid #2a2b33;
  border-radius: 12px;
  padding: 12px 14px;
  color: #e2e8f0;
  font-size: 13px;
  font-family: inherit;
  line-height: 1.6;
  resize: none;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.2);
}
.dc-textarea::placeholder { color: #64748b; }
.dc-textarea:hover { border-color: #363842; }
.dc-textarea:focus { border-color: #ff5733; box-shadow: 0 0 0 1px rgba(255, 87, 51, 0.35); }

/* ===== Footer ===== */
.dc-footer {
  padding: 16px 24px 24px;
  background: #131418;
  border-top: 1px solid #2a2b33;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.dc-switch {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px;
  padding: 8px 12px;
  border-radius: 12px;
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
}
.dc-switch.sw-reject { color: #fb7185; border-color: rgba(244, 63, 94, 0.2); }
.dc-switch.sw-reject:hover { color: #fda4af; background: rgba(244, 63, 94, 0.1); border-color: rgba(244, 63, 94, 0.4); }
.dc-switch.sw-approve { color: #34d399; border-color: rgba(16, 185, 129, 0.2); }
.dc-switch.sw-approve:hover { color: #6ee7b7; background: rgba(16, 185, 129, 0.1); border-color: rgba(16, 185, 129, 0.4); }

.dc-footer-main { display: flex; align-items: center; gap: 12px; }
.dc-cancel {
  padding: 8px 16px;
  border-radius: 12px;
  font-size: 13px; font-weight: 500;
  background: #1f2026;
  border: 1px solid #2a2b33;
  color: #cbd5e1;
  cursor: pointer;
  transition: all 0.15s;
}
.dc-cancel:hover { background: #282a32; color: #fff; }
.dc-confirm {
  padding: 8px 20px;
  border-radius: 12px;
  font-size: 13px; font-weight: 600;
  background: #ff5733;
  border: none;
  color: #fff;
  cursor: pointer;
  box-shadow: 0 4px 20px -2px rgba(255, 87, 51, 0.45);
  transition: all 0.15s;
}
.dc-confirm:hover:not(:disabled) { background: #e04826; }
.dc-confirm:active:not(:disabled) { transform: scale(0.98); }
.dc-confirm:disabled { opacity: 0.45; cursor: not-allowed; box-shadow: none; }
</style>
