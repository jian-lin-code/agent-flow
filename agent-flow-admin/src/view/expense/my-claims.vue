<template>
  <div class="my-claims-page">
    <!-- ===== 页头 ===== -->
    <section class="page-hero">
      <div class="hero-left">
        <div class="hero-title-row">
          <h1>{{ $t('claims.employee.title') }}</h1>
          <!-- 与「待我审批」一致：展示当前用户的申请总数 -->
          <span class="hero-tag" v-if="stats">{{ $t('claims.admin.tag', { n: stats.total }) }}</span>
        </div>
        <p class="hero-sub">{{ $t('claims.employee.sub') }}</p>
      </div>
      <ClaimViewSwitch v-if="isAdmin" class="hero-switch" :left-count="approvalsTotal" :right-count="stats?.total ?? null" />
      <button class="hero-cta" @click="router.push('/ai-chat')">
        <el-icon><ChatDotRound /></el-icon> {{ $t('claims.employee.goChat') }}
      </button>
    </section>

    <!-- ===== 统计卡片 ===== -->
    <section v-loading="statsLoading" class="stats-grid">
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">{{ $t('claims.employee.statInProgress') }}</span>
          <span class="stat-icon blue"><el-icon><Timer /></el-icon></span>
        </div>
        <div class="stat-value">{{ stats?.in_progress ?? '-' }}</div>
        <div class="stat-sub">{{ $t('claims.employee.statInProgressSub') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">{{ $t('claims.employee.statCompleted') }}</span>
          <span class="stat-icon green"><el-icon><CircleCheck /></el-icon></span>
        </div>
        <div class="stat-value">{{ stats?.completed ?? '-' }}</div>
        <div class="stat-sub">{{ $t('claims.employee.statCompletedSub') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">{{ $t('claims.employee.statAbnormal') }}</span>
          <span class="stat-icon red"><el-icon><WarningFilled /></el-icon></span>
        </div>
        <div class="stat-value">{{ stats?.abnormal ?? '-' }}</div>
        <div class="stat-sub">{{ $t('claims.employee.statAbnormalSub') }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">{{ $t('claims.employee.statMonth') }}</span>
          <span class="stat-icon orange"><el-icon><Wallet /></el-icon></span>
        </div>
        <div class="stat-value stat-value-money" v-if="stats">
          ¥{{ formatAmount(stats.month_amount) }}
          <span class="money-count">{{ $t('claims.employee.monthCount', { n: stats.month_count }) }}</span>
        </div>
        <div class="stat-value" v-else>-</div>
        <div class="stat-sub">{{ $t('claims.employee.statMonthSub') }}</div>
      </div>
    </section>

    <!-- ===== 列表面板 ===== -->
    <section class="af-card list-panel">
      <!-- 状态 Tab（带数量徽标） -->
      <div class="status-tabs">
        <span
          v-for="tab in statusTabs"
          :key="tab.value"
          class="status-tab"
          :class="{ active: filterStatus === tab.value }"
          @click="switchTab(tab.value)"
        >
          {{ tab.label }}
          <b>{{ statusCounts[tab.value] ?? 0 }}</b>
        </span>
        <div class="tab-right">
          <el-button size="small" circle :loading="listLoading" @click="loadAll">
            <el-icon v-if="!listLoading"><Refresh /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 搜索筛选栏（关键词防抖实时查询） -->
      <div class="filter-bar">
        <el-input
          v-model="keywordInput"
          class="filter-input"
          :placeholder="$t('claims.employee.searchPlaceholder')"
          clearable
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          range-separator="至"
          :start-placeholder="$t('claims.employee.dateStart')"
          :end-placeholder="$t('claims.employee.dateEnd')"
          value-format="YYYY-MM-DD"
          :clearable="true"
          class="filter-date"
          @change="doSearch"
        />
        <div class="bar-actions">
          <el-button circle :icon="RefreshLeft" :title="$t('claims.employee.reset')" @click="resetFilter" />
          <el-button :loading="exporting" :icon="Download" @click="exportCsv">{{ $t('claims.employee.exportCsv') }}</el-button>
        </div>
      </div>

      <!-- 表格（带横向滑动滑块提示） -->
      <TableSwipe>
        <el-table
          :data="claims"
          v-loading="listLoading"
          style="width: 100%"
          class="claims-table"
          @row-click="openDrawer"
        >
        <el-table-column :label="$t('claims.col.claimNo')" min-width="190">
          <template #default="{ row }">
            <div class="claim-no-cell">
              <span class="claim-no">{{ row.claim_no }}</span>
              <span
                class="copy-btn"
                :title="$t('claims.admin.copyHint')"
                @click.stop="copyClaimNo(row.claim_no)"
              ><el-icon><DocumentCopy /></el-icon></span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="$t('claims.col.title')" min-width="140">
          <template #default="{ row }">
            <span class="title-cats" :class="{ 'cats-empty': !row.categories?.length }">
              {{ row.categories?.length ? row.categories.join(' / ') : '-' }}
            </span>
          </template>
        </el-table-column>
        <!-- 描述列：展示费用明细中的描述 -->
        <el-table-column :label="$t('claims.col.description')" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="desc-text" :class="{ 'cats-empty': !row.descriptions?.length }">
              {{ row.descriptions?.length ? row.descriptions.join(' / ') : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('claims.col.amount')" min-width="120" align="right">
          <template #default="{ row }">
            <span class="amount-text">¥{{ formatAmount(row.total_amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('claims.col.submittedAt')" min-width="150">
          <template #default="{ row }">
            <span class="time-text">{{ formatTime(row.submitted_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('claims.col.status')" min-width="100" align="center">
          <template #default="{ row }">
            <span class="status-pill" :class="statusClass(row.status)">{{ statusLabel(row.status) }}</span>
          </template>
        </el-table-column>
        <!-- AI 预审列：点击打开右侧抽屉 -->
        <el-table-column :label="$t('claims.col.aiReview')" min-width="160" align="center">
          <template #default="{ row }">
            <div class="ai-cell" @click.stop="openDrawer(row)">
              <template v-if="row.pre_review">
                <span v-if="isReviewDone(row.pre_review)" class="result-pill" :class="resultClass(row.pre_review.result)">
                  {{ resultLabel(row.pre_review.result) }}
                </span>
                <span v-else class="result-pill r-pending">
                  <el-icon class="spin"><Loading /></el-icon>
                  {{ row.pre_review.status === 'running' ? $t('claims.review.running') : $t('claims.review.pending') }}
                </span>
                <span class="ai-detail-link">{{ $t('claims.col.aiDetail') }} <el-icon><ArrowRight /></el-icon></span>
              </template>
              <span v-else class="ai-none" @click.stop="openDrawer(row)">{{ $t('claims.review.none') }}</span>
            </div>
          </template>
        </el-table-column>
        <!-- 操作列已移除：AI 预审列（点击）与整行点击均可打开详情抽屉 -->
        <template #empty>
          <el-empty :description="$t('claims.empty')" :image-size="88" />
        </template>
      </el-table>
      </TableSwipe>

      <!-- 分页（移动端吸底常驻） -->
      <div class="table-pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total ?? 0"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          background
          @current-change="loadClaims"
          @size-change="loadClaims"
        />
      </div>
    </section>

    <!-- AI 预审抽屉 -->
    <PreReviewDrawer
      v-model="drawerVisible"
      :claim-id="activeClaimId"
      :claim-no="activeClaimNo"
      mode="employee"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowRight, ChatDotRound, CircleCheck, DocumentCopy, Download, Loading,
  Refresh, RefreshLeft, Search, Timer, WarningFilled, Wallet
} from '@element-plus/icons-vue'
import PreReviewDrawer from './PreReviewDrawer.vue'
import TableSwipe from '@/components/TableSwipe.vue'
import ClaimViewSwitch from './ClaimViewSwitch.vue'
import { useUserStore } from '@/stores/user'
import { copyWithToast } from '@/utils/clipboard'
import {
  exportClaimsCsv,
  getClaimStatsApi,
  listMyClaimsApi,
  type ClaimStats,
  type ExpenseClaimItem,
  type PreReviewInfo
} from '@/api/expense'

const router = useRouter()
const { t } = useI18n()
const userStore = useUserStore()
/** 仅管理员展示「待我审批 / 我的申请」切换（员工无待审批入口） */
const isAdmin = computed(() => userStore.userInfo?.role === 'admin')

const stats = ref<ClaimStats | null>(null)
const statsLoading = ref(false)
/** 「待我审批」侧徽标数量（切换组件左侧，仅 admin 挂载切换器时拉取） */
const approvalsTotal = ref<number | null>(null)
const claims = ref<ExpenseClaimItem[]>([])
const listLoading = ref(false)
const total = ref<number | null>(null)
const filterStatus = ref('')
const keywordInput = ref('')
const keyword = ref('')
const dateRange = ref<[string, string] | null>(null)
const exporting = ref(false)
const page = ref(1)
const pageSize = ref(10)

const drawerVisible = ref(false)
const activeClaimId = ref<number | null>(null)
const activeClaimNo = ref<string | null>(null)

const statusTabs = computed(() => [
  { value: '', label: t('claims.tab.all') },
  { value: 'pending_approval', label: t('claims.tab.pendingApproval') },
  { value: 'needs_info', label: t('claims.tab.needsInfo') },
  { value: 'processing', label: t('claims.tab.processing') },
  { value: 'approved', label: t('claims.tab.approved') },
  { value: 'rejected', label: t('claims.tab.rejected') },
  { value: 'completed', label: t('claims.tab.completed') },
  { value: 'failed', label: t('claims.tab.failed') }
])

/** 每个状态 Tab 的数量徽标（来自统计接口的原始分布） */
const statusCounts = computed<Record<string, number>>(() => {
  const counts: Record<string, number> = { '': stats.value?.total ?? 0 }
  for (const [status, count] of Object.entries(stats.value?.status_counts ?? {})) {
    counts[status] = count
  }
  return counts
})

/** 组装当前筛选条件（列表与导出共用） */
const currentFilter = () => ({
  status: filterStatus.value || undefined,
  keyword: keyword.value || undefined,
  date_from: dateRange.value?.[0] || undefined,
  date_to: dateRange.value?.[1] || undefined
})

const loadStats = async () => {
  statsLoading.value = true
  try {
    // 固定按「本人提交的申请」统计：admin 默认口径是待审批全局统计，与本页不匹配
    const res = await getClaimStatsApi('mine')
    stats.value = res.data
  } finally {
    statsLoading.value = false
  }
}

const loadClaims = async () => {
  listLoading.value = true
  try {
    const res = await listMyClaimsApi({
      ...currentFilter(),
      page: page.value,
      page_size: pageSize.value
    })
    claims.value = res.data.items
    total.value = res.data.total
  } finally {
    listLoading.value = false
  }
}

const switchTab = (value: string) => {
  filterStatus.value = value
  page.value = 1
  loadClaims()
}

const doSearch = () => {
  keyword.value = keywordInput.value.trim()
  page.value = 1
  loadClaims()
}

// 关键词防抖实时查询（400ms 停止输入后自动触发；清空时立即查询）
let searchTimer: number | undefined
watch(keywordInput, (val) => {
  window.clearTimeout(searchTimer)
  if (!val) {
    doSearch()
    return
  }
  searchTimer = window.setTimeout(doSearch, 400)
})

const resetFilter = () => {
  keywordInput.value = ''
  keyword.value = ''
  dateRange.value = null
  filterStatus.value = ''
  page.value = 1
  loadClaims()
}

const exportCsv = async () => {
  exporting.value = true
  try {
    await exportClaimsCsv(
      listMyClaimsApi,
      currentFilter(),
      [
        t('claims.col.claimNo'), t('claims.col.title'), t('claims.col.description'),
        t('claims.col.amount'), t('claims.col.submittedAt'), t('claims.col.status'), t('claims.col.aiReview')
      ],
      (item) => [
        item.claim_no,
        item.categories?.length ? item.categories.join(' / ') : (item.title || '-'),
        item.descriptions?.length ? item.descriptions.join(' / ') : '-',
        item.total_amount,
        formatTime(item.submitted_at),
        statusLabel(item.status),
        item.pre_review?.result ? resultLabel(item.pre_review.result) : '-'
      ],
      `expense-claims-${new Date().toISOString().slice(0, 10)}.csv`
    )
  } finally {
    exporting.value = false
  }
}

const loadAll = () => {
  loadStats()
  loadClaims()
}

const openDrawer = (row: ExpenseClaimItem) => {
  activeClaimId.value = row.id
  activeClaimNo.value = row.claim_no
  drawerVisible.value = true
}

/** 单号悬浮复制（clipboard API 不可用时降级 execCommand，并始终给出提示） */
const copyClaimNo = async (no: string) => {
  await copyWithToast(no, t('claims.admin.copied'), t('claims.admin.copyFailed'))
}

onMounted(() => {
  loadAll()
  // 「待我审批」侧徽标数量（仅 admin 显示切换器；失败不影响页面，只是徽标不显示）
  if (isAdmin.value) {
    getClaimStatsApi()
      .then((res) => { approvalsTotal.value = res.data.total })
      .catch(() => {})
  }
})

// 离开页面时清掉防抖定时器，避免切页后仍在后台发请求
onBeforeUnmount(() => window.clearTimeout(searchTimer))

// ===== 展示辅助 =====
const formatAmount = (v: string) =>
  Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const formatTime = (v: string | null) =>
  v ? new Date(v).toLocaleString('zh-CN', { hour12: false }).replaceAll('/', '-') : '-'

const statusLabel = (s: string) => t(`claims.status.${s}`)
const statusClass = (s: string) => {
  const map: Record<string, string> = {
    draft: 's-info', needs_info: 's-warn', pending_approval: 's-neutral',
    processing: 's-info', approved: 's-ok', rejected: 's-fail',
    completed: 's-ok', failed: 's-fail'
  }
  return map[s] ?? 's-info'
}
const isReviewDone = (r: PreReviewInfo) => r.status === 'completed' || r.status === 'failed'
const resultLabel = (r: string | null) => (r ? t(`claims.result.${r}`) : '-')
const resultClass = (r: string | null) =>
  r === 'pass' ? 'r-pass' : r === 'fail' ? 'r-fail' : 'r-manual'
</script>

<style scoped>
.my-claims-page { display: flex; flex-direction: column; gap: 16px; }

/* ===== 页头 ===== */
.page-hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.hero-title-row { display: flex; align-items: center; gap: 12px; }
.hero-title-row h1 { color: var(--af-text); font-size: 24px; font-weight: 700; letter-spacing: -0.3px; }
.hero-tag { color: var(--af-primary); font-size: 12px; background: rgba(255, 92, 51, 0.15); border: 1px solid rgba(255, 92, 51, 0.25); border-radius: 6px; padding: 3px 10px; font-weight: 500; }
.hero-sub { color: var(--af-text-3); font-size: 13px; margin-top: 8px; }
/* 视图切换在 hero 中垂直居中，窄屏时整行铺满 */
.hero-switch { align-self: center; }
.hero-cta {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--af-primary-gradient);
  color: #fff; font-size: 13px; font-weight: 600;
  border: none; border-radius: 10px;
  padding: 11px 20px;
  cursor: pointer;
  min-height: 44px;
}
.hero-cta:hover { opacity: 0.9; }

/* ===== 统计卡片（设计稿：高 112px、右上角小圆图标、等宽大数字） ===== */
.stats-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.stat-card {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 16px;
  padding: 16px;
  display: flex; flex-direction: column; justify-content: space-between;
  gap: 6px;
  min-height: 112px;
  transition: border-color 0.2s;
}
.stat-card:hover { border-color: rgba(255, 255, 255, 0.18); }
.stat-top { display: flex; justify-content: space-between; align-items: center; }
.stat-label { color: var(--af-text-2); font-size: 13px; font-weight: 500; }
.stat-icon {
  width: 24px; height: 24px; border-radius: 9999px;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px;
  border: 1px solid transparent;
}
.stat-icon.blue { background: rgba(77, 141, 255, 0.1); color: var(--af-info); border-color: rgba(77, 141, 255, 0.2); }
.stat-icon.green { background: rgba(46, 204, 113, 0.1); color: var(--af-success); border-color: rgba(46, 204, 113, 0.2); }
.stat-icon.red { background: rgba(255, 77, 79, 0.1); color: var(--af-danger); border-color: rgba(255, 77, 79, 0.2); }
.stat-icon.orange { background: rgba(255, 92, 51, 0.1); color: var(--af-primary); border-color: rgba(255, 92, 51, 0.2); }
.stat-value {
  color: var(--af-text); font-size: 28px; font-weight: 700;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  letter-spacing: -0.5px;
  font-variant-numeric: tabular-nums;
}
.stat-value-money { font-size: 20px; display: flex; align-items: baseline; gap: 6px; flex-wrap: wrap; }
.money-count { color: var(--af-text-3); font-size: 11px; font-weight: 400; font-family: 'JetBrains Mono', ui-monospace, monospace; }
.stat-sub { color: var(--af-text-3); font-size: 11px; }

/* ===== 列表面板：卡片内分带（Tab 带 / 筛选带 / 表格 / 分页带），与设计稿一致 ===== */
.list-panel { padding: 0; overflow: hidden; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25); }

/* Tab 带 */
.status-tabs {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  border-bottom: 1px solid var(--af-border-soft);
  padding: 12px 20px;
}
.status-tab {
  color: var(--af-text-2); font-size: 12px; font-weight: 500;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  display: inline-flex; align-items: center; gap: 6px;
  transition: all 0.15s;
}
.status-tab b {
  color: var(--af-text-3); font-size: 11px; font-weight: 500;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
}
.status-tab:hover { color: var(--af-text); background: var(--af-hover); }
/* 激活 Tab：实底主色 + 白字 + 轻投影（设计稿样式） */
.status-tab.active {
  color: #fff;
  background: var(--af-primary);
  box-shadow: 0 2px 8px rgba(255, 92, 51, 0.25);
}
.status-tab.active b { color: rgba(255, 255, 255, 0.9); }
.tab-right { margin-left: auto; }

/* ===== 筛选带：稍深底色 + 上下分割线 ===== */
.filter-bar {
  display: flex; align-items: center; gap: 12px;
  flex-wrap: wrap;
  padding: 14px 20px;
  border-bottom: 1px solid var(--af-border-soft);
  background: rgba(11, 12, 14, 0.4);
}
.filter-input { flex: 0 1 320px; min-width: 220px; }
.filter-date { width: 250px; }
.bar-actions { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.bar-actions .el-button + .el-button { margin-left: 0; }

/* ===== 表格单元格 ===== */
.claims-table { --el-table-row-hover-bg-color: rgba(31, 32, 36, 0.6); }
.claim-no-cell { display: flex; align-items: center; gap: 6px; }
.claim-no {
  color: var(--af-info);
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px; font-weight: 500;
  letter-spacing: -0.2px;
}
/* 单号悬浮复制按钮：默认隐藏，悬浮行时出现 */
.copy-btn {
  opacity: 0; transition: opacity 0.15s;
  color: var(--af-text-3); cursor: pointer;
  display: inline-flex; font-size: 13px;
}
.claims-table :deep(.el-table__row:hover) .copy-btn { opacity: 1; }
.copy-btn:hover { color: #fff; }
.title-cats { color: var(--af-text); font-size: 12.5px; }
.cats-empty { color: var(--af-text-3); }
.desc-text { color: var(--af-text-2); font-size: 12.5px; }
/* 金额：等宽数字右对齐（财务铁律） */
.amount-text {
  color: var(--af-text); font-size: 13px; font-weight: 500;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}
.time-text {
  color: var(--af-text-2); font-size: 12px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-variant-numeric: tabular-nums;
}

/* 状态标签：描边胶囊（待审批为中性灰，与设计稿一致） */
.status-pill {
  font-size: 11px; border-radius: 6px; padding: 3px 10px;
  white-space: nowrap; border: 1px solid transparent;
  display: inline-block;
}
.s-neutral { color: var(--af-text-2); background: rgba(255, 255, 255, 0.04); border-color: rgba(255, 255, 255, 0.14); }
.s-ok { color: var(--af-success); background: var(--af-success-soft); border-color: rgba(46, 204, 113, 0.3); }
.s-warn { color: var(--af-warning); background: var(--af-warning-soft); border-color: rgba(245, 166, 35, 0.3); }
.s-info { color: var(--af-info); background: var(--af-info-soft); border-color: rgba(77, 141, 255, 0.3); }
.s-fail { color: var(--af-danger); background: var(--af-danger-soft); border-color: rgba(255, 77, 79, 0.3); }

/* AI 预审单元格 */
.ai-cell { display: inline-flex; align-items: center; justify-content: center; gap: 8px; cursor: pointer; min-width: 0; flex-wrap: wrap; }
.ai-cell:hover .ai-detail-link { color: var(--af-primary); }
.result-pill { font-size: 11px; font-weight: 500; border-radius: 6px; padding: 3px 10px; display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; border: 1px solid transparent; }
.r-pass { color: var(--af-success); background: var(--af-success-soft); border-color: rgba(46, 204, 113, 0.3); }
.r-fail { color: var(--af-danger); background: var(--af-danger-soft); border-color: rgba(255, 77, 79, 0.3); }
.r-manual { color: var(--af-warning); background: var(--af-warning-soft); border-color: rgba(245, 166, 35, 0.3); }
.r-pending { color: var(--af-info); background: var(--af-info-soft); border-color: rgba(77, 141, 255, 0.3); }
.spin { animation: spin 1.2s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.ai-detail-link { display: inline-flex; align-items: center; gap: 2px; color: var(--af-text-3); font-size: 11px; }
.ai-none { color: var(--af-text-3); font-size: 11px; }

/* ===== 分页带：稍深底色 + 上分割线 ===== */
.table-pagination {
  display: flex; justify-content: flex-end;
  padding: 14px 20px;
  border-top: 1px solid var(--af-border-soft);
  background: rgba(11, 12, 14, 0.4);
}

/* ===== 响应式 ===== */
@media (max-width: 1100px) {
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 768px) {
  .hero-title-row h1 { font-size: 21px; }
  .hero-cta { width: 100%; justify-content: center; }
  .hero-switch { width: 100%; justify-content: center; }
  /* 统计卡田字型排列，与「待我审批」页一致 */
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  /* 分页收窄：隐藏每页条数与总数，居中显示，避免撑破容器。
     不再做 sticky 吸底：吸底时悬浮条会盖住表格最后一行，
     滚动到底的露出已由 MainLayout 的 ::after 底部占位块保证。 */
  .table-pagination {
    justify-content: center;
    background: var(--af-card, #141414);
  }
  .table-pagination :deep(.el-pagination__total),
  .table-pagination :deep(.el-pagination__sizes) { display: none; }
  /* 横向滚动条常显，提示用户表格可以左右滑动 */
  .claims-table :deep(.el-scrollbar__bar.is-horizontal) {
    opacity: 1;
    height: 6px;
  }
  .claims-table :deep(.el-scrollbar__bar.is-horizontal .el-scrollbar__thumb) { opacity: 0.6; }
  /* 筛选栏移动端堆叠 */
  .filter-input, .filter-date { width: 100%; }
  .filter-date { max-width: none; flex: 1 1 100%; }
  .bar-actions { flex: 1; margin-left: 0; }
  .bar-actions .el-button { flex: 1; }
}
</style>
