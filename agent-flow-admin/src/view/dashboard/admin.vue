<template>
  <div class="admin-dashboard">
    <!-- ===== 页头 ===== -->
    <section class="ops-hero">
      <div class="ops-head-left">
        <div class="ops-badges">
          <span class="ops-badge orange">{{ $t('admin.opsBadge') }}</span>
          <span class="ops-badge" :class="clusterHealthy ? 'green' : 'red'">
            <span class="dot" :class="clusterHealthy ? 'green' : 'red'" />
            {{ clusterHealthy ? $t('admin.clusterHealthy') : $t('admin.clusterDegraded') }}
          </span>
        </div>
        <div class="ops-title-row">
          <h1>{{ $t('admin.pageTitle') }}</h1>
          <span class="ops-sub">{{ $t('admin.pageSub') }}</span>
        </div>
      </div>
      <div class="ops-head-right">
        <div class="ops-metric">
          <span>{{ $t('admin.cpuLoad') }}</span><b>{{ health ? health.cpu_percent + '%' : '—' }}</b>
        </div>
        <div class="ops-metric">
          <span>{{ $t('admin.memLoad') }}</span>
          <b>{{ health ? health.memory_used_gb + ' / ' + health.memory_total_gb + 'G' : '—' }}</b>
        </div>
        <div class="ops-metric">
          <span>{{ $t('admin.avgResponse') }}</span>
          <b>{{ health && health.avg_response_ms != null ? formatDuration(health.avg_response_ms) : '—' }}</b>
        </div>
        <button class="refresh-btn" :disabled="loading" @click="loadAll">
          <el-icon><Refresh /></el-icon> {{ loading ? $t('admin.loading') : $t('admin.refreshBoard') }}
        </button>
      </div>
    </section>

    <!-- ===== 统计卡片 ===== -->
    <section class="stats-grid">
      <div class="stat-card" v-for="stat in statCards" :key="stat.label">
        <div class="stat-top">
          <span class="stat-label">{{ stat.label }}</span>
          <span class="stat-icon" :class="stat.tone"><el-icon><component :is="stat.icon" /></el-icon></span>
        </div>
        <div class="stat-value-row">
          <span class="stat-value">{{ stat.value }}</span>
          <span v-if="stat.trend" class="stat-trend" :class="stat.trendClass">{{ stat.trend }}</span>
        </div>
        <div class="stat-foot">
          <span>{{ stat.sub }}</span>
          <span class="stat-extra">{{ stat.extra }}</span>
        </div>
      </div>
    </section>

    <!-- ===== 中部三卡 ===== -->
    <section class="middle-grid">
      <!-- 流程运行情况 -->
      <div class="af-card panel">
        <div class="panel-head">
          <div class="panel-title"><el-icon class="pt-icon"><DataAnalysis /></el-icon> {{ $t('admin.flowStatus') }}</div>
        </div>
        <div class="donut-wrap">
          <svg viewBox="0 0 36 36" class="donut">
            <circle class="donut-bg" cx="18" cy="18" r="15.9155" />
            <circle class="seg success" :stroke-dasharray="`${donut.success} 100`" cx="18" cy="18" r="15.9155" />
            <circle class="seg warning" :stroke-dasharray="`${donut.running} 100`" :stroke-dashoffset="-donut.success" cx="18" cy="18" r="15.9155" />
            <circle class="seg danger" :stroke-dasharray="`${donut.abnormal} 100`" :stroke-dashoffset="-(donut.success + donut.running)" cx="18" cy="18" r="15.9155" />
          </svg>
          <div class="donut-center">
            <b>{{ $t('admin.successRate') }}</b>
            <strong>{{ taskStats.success_rate }}%</strong>
            <span>{{ $t('admin.selfHeal') }}</span>
          </div>
        </div>
        <div class="donut-legend">
          <div class="legend-item"><span class="ldot success" /> {{ $t('admin.legendSuccess') }} <b>{{ taskStats.completed }}</b> <i>{{ donut.success }}%</i></div>
          <div class="legend-item"><span class="ldot warning" /> {{ $t('admin.legendRunning') }} <b>{{ taskStats.running }}</b> <i>{{ donut.running }}%</i></div>
          <div class="legend-item"><span class="ldot danger" /> {{ $t('admin.legendFailed') }} <b>{{ taskStats.abnormal }}</b> <i>{{ donut.abnormal }}%</i></div>
        </div>
      </div>

      <!-- 服务运行状态（替代原 Agent 运行状态） -->
      <div class="af-card panel">
        <div class="panel-head">
          <div class="panel-title"><el-icon class="pt-icon"><Cpu /></el-icon> {{ $t('admin.serviceStatus') }}</div>
          <span class="panel-more" @click="loadAll">{{ $t('admin.refreshBoard') }} <el-icon><Refresh /></el-icon></span>
        </div>
        <div class="agent-list">
          <div
            v-for="service in services"
            :key="service.key"
            class="agent-item"
            :class="{ danger: service.status === 'offline' }"
          >
            <span class="agent-icon"><el-icon><component :is="service.icon" /></el-icon></span>
            <div class="agent-info">
              <div class="agent-name">{{ service.name }}</div>
              <div class="agent-meta">{{ service.detail }}</div>
            </div>
            <div class="agent-right">
              <span class="agent-load" :class="'ld-' + service.tone">{{ service.statusText }}</span>
              <span class="agent-time">{{ service.timeText }}</span>
            </div>
          </div>
          <div v-if="services.length === 0" class="empty-hint">{{ $t('admin.loading') }}</div>
        </div>
      </div>

      <!-- 待审批事项 -->
      <div class="af-card panel">
        <div class="panel-head">
          <div class="panel-title">
            <el-icon class="pt-icon"><Tickets /></el-icon> {{ $t('admin.pendingApprovals') }}
            <span class="count-badge">{{ approvalSummary.pending_count }}</span>
          </div>
          <span class="panel-more" @click="router.push('/pending-approvals')">{{ $t('admin.viewMore') }} <el-icon><ArrowRight /></el-icon></span>
        </div>
        <div class="approve-list">
          <div v-for="todo in approvalSummary.items" :key="todo.claim_no" class="approve-item">
            <div class="approve-main">
              <div class="approve-title">{{ todo.title }} <span class="approve-tag">{{ todo.category || $t('admin.tagDefault') }}</span></div>
              <div class="approve-meta">{{ $t('admin.from') }}{{ todo.applicant }} · {{ todo.claim_no }}</div>
              <div class="approve-meta">{{ formatTime(todo.submitted_at) }}</div>
            </div>
            <div class="approve-right">
              <span class="approve-amount">¥ {{ formatAmount(todo.amount) }}</span>
              <span class="approve-actions"><b class="go" @click="router.push('/pending-approvals')">{{ $t('admin.goApprove') }}</b></span>
            </div>
          </div>
          <div v-if="approvalSummary.items.length === 0" class="empty-hint">{{ $t('admin.emptyApprovals') }}</div>
        </div>
        <div v-if="approvalSummary.pending_count > approvalSummary.items.length" class="panel-foot">
          {{ $t('admin.pendingTotal', { n: approvalSummary.pending_count }) }}
          <span class="panel-link" @click="router.push('/pending-approvals')">{{ $t('admin.viewAllPending') }}</span>
        </div>
      </div>
    </section>

    <!-- ===== 吞吐量 ===== -->
    <section class="af-card panel throughput">
      <div class="panel-head">
        <div class="panel-title"><el-icon class="pt-icon"><TrendCharts /></el-icon> {{ $t('admin.throughputTitle') }}</div>
        <div class="range-tabs">
          <span
            v-for="option in rangeOptions"
            :key="option.value"
            class="range-tab"
            :class="{ active: trendRange === option.value }"
            @click="switchRange(option.value)"
          >{{ option.label }}</span>
        </div>
      </div>
      <p class="throughput-sub">{{ $t('admin.throughputSub') }}</p>
      <div class="chart-box">
        <svg viewBox="0 0 600 120" preserveAspectRatio="none" class="throughput-chart">
          <defs>
            <linearGradient id="tp-grad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#ff5c33" stop-opacity="0.35" />
              <stop offset="100%" stop-color="#ff5c33" stop-opacity="0" />
            </linearGradient>
          </defs>
          <path v-if="chart.area" class="line" :d="chart.area" fill="url(#tp-grad)" />
          <path v-if="chart.line" class="line" :d="chart.line" fill="none" stroke="#ff5c33" stroke-width="2" />
          <circle v-if="chart.last" :cx="chart.last.x" :cy="chart.last.y" r="4" fill="#ff5c33" />
        </svg>
        <div v-if="trendSummary.total === 0" class="chart-empty">{{ $t('admin.chartEmpty') }}</div>
        <div class="chart-axis">
          <span v-for="(label, index) in chart.axisLabels" :key="index" :class="{ now: index === chart.axisLabels.length - 1 }">{{ label }}</span>
        </div>
      </div>
      <div class="chart-summary">
        <span>{{ $t('admin.chartTotal', { n: trendSummary.total }) }}</span>
        <span>{{ $t('admin.chartSuccess', { n: trendSummary.success }) }}</span>
        <span>{{ $t('admin.chartFailed', { n: trendSummary.failed }) }}</span>
      </div>
    </section>

    <!-- ===== 底部：快捷通道 + 运行记录 ===== -->
    <section class="bottom-grid">
      <div class="af-card panel quick-panel">
        <div class="panel-head">
          <div class="panel-title"><el-icon class="pt-icon"><Opportunity /></el-icon> {{ $t('admin.quickPanel') }}</div>
        </div>
        <div class="quick-grid">
          <div class="quick-card" v-for="q in quickActions" :key="q.label" @click="router.push(q.path)">
            <div class="q-icon" :class="q.tone"><el-icon><component :is="q.icon" /></el-icon></div>
            <div class="q-label">{{ q.label }}</div>
            <div class="q-desc">{{ q.desc }}</div>
          </div>
        </div>
      </div>

      <div class="af-card panel records-panel">
        <div class="panel-head">
          <div class="panel-title"><el-icon class="pt-icon"><List /></el-icon> {{ $t('admin.recordsTitle') }}</div>
          <span class="panel-more" @click="loadAll">{{ $t('admin.refreshBoard') }} <el-icon><Refresh /></el-icon></span>
        </div>
        <TableSwipe>
          <el-table :data="summary?.records ?? []" style="width: 100%" size="small" class="dark-table" v-loading="loading">
            <el-table-column prop="name" :label="$t('admin.colName')" min-width="150" show-overflow-tooltip />
            <el-table-column prop="executor" :label="$t('admin.colExecutor')" min-width="110" />
            <el-table-column :label="$t('common.status')" width="110">
              <template #default="{ row }">
                <span class="status-pill" :class="statusMeta(row.status).cls">{{ statusMeta(row.status).label }}</span>
              </template>
            </el-table-column>
            <el-table-column :label="$t('admin.colStartTime')" width="150">
              <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
            </el-table-column>
            <el-table-column :label="$t('admin.colDuration')" width="100">
              <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
            </el-table-column>
            <template #empty>
              <div class="empty-hint">{{ $t('admin.emptyRecords') }}</div>
            </template>
          </el-table>
        </TableSwipe>
        <div class="table-foot">
          <span>{{ $t('admin.tableFoot', { shown: summary?.records.length ?? 0, total: summary?.records_total ?? 0 }) }}</span>
          <span class="foot-time">{{ summary ? $t('admin.updatedAt', { time: formatTime(summary.generated_at) }) : '' }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import TableSwipe from '@/components/TableSwipe.vue'
import {
  ArrowRight, Check, Timer, Warning, Refresh, DataAnalysis, Cpu,
  Tickets, TrendCharts, Opportunity, List, Monitor, Notebook, Connection
} from '@element-plus/icons-vue'
import {
  getDashboardHealth, getDashboardSummary, getDashboardTrend,
  type DashboardHealth, type DashboardSummary, type DashboardTrend,
  type DashboardTrendRange, type DashboardWorkerStatus
} from '@/api/dashboard'

const { t } = useI18n()
const router = useRouter()

const summary = ref<DashboardSummary | null>(null)
const health = ref<DashboardHealth | null>(null)
const trend = ref<DashboardTrend | null>(null)
const trendRange = ref<DashboardTrendRange>('24h')
const loading = ref(false)

const rangeOptions = computed(() => [
  { value: '1h' as const, label: t('admin.range1h') },
  { value: '24h' as const, label: t('admin.range24h') },
  { value: '7d' as const, label: t('admin.range7d') }
])

const taskStats = computed(() => summary.value?.tasks ?? {
  total: 0, completed: 0, running: 0, abnormal: 0, success_rate: 0,
  total_delta: null, completed_delta: null, abnormal_delta: null,
  today_total: 0, avg_duration_ms: null
})

const approvalSummary = computed(() => summary.value?.approvals ?? {
  pending_count: 0, processing_count: 0, pending_amount: '0.00', items: []
})

const quick = computed(() => summary.value?.quick ?? {
  pending_approvals: 0, kb_count: 0, doc_total: 0, doc_processing: 0, doc_failed: 0,
  user_count: 0, failed_kb_uid: null, processing_kb_uid: null
})

/* ---------- 统计卡 ---------- */
const statCards = computed(() => {
  const s = taskStats.value
  return [
    {
      label: t('admin.statTotal'), value: s.total, trend: deltaText(s.total_delta),
      trendClass: s.total_delta != null && s.total_delta < 0 ? 'down' : 'up',
      sub: t('admin.statTotalSub', { n: s.today_total }), extra: t('admin.statTotalExtra'),
      tone: 'blue', icon: Monitor
    },
    {
      label: t('admin.statDone'), value: s.completed, trend: deltaText(s.completed_delta),
      trendClass: 'up',
      sub: t('admin.statDoneSub', { n: s.success_rate }), extra: t('admin.statDoneExtra'),
      tone: 'green', icon: Check
    },
    {
      label: t('admin.statRunning'), value: s.running, trend: null, trendClass: 'up',
      sub: t('admin.statRunningSub', { n: s.total ? Math.round(s.running / s.total * 1000) / 10 : 0 }),
      extra: t('admin.statRunningExtra'), tone: 'orange', icon: Timer
    },
    {
      label: t('admin.statFailed'), value: s.abnormal, trend: deltaText(s.abnormal_delta),
      trendClass: s.abnormal_delta != null && s.abnormal_delta > 0 ? 'down' : 'up',
      sub: t('admin.statFailedSub'), extra: t('admin.statFailedExtra'),
      tone: 'red', icon: Warning
    }
  ]
})

const deltaText = (delta: number | null) =>
  delta == null ? '' : `${delta > 0 ? '↑ +' : '↓ '}${delta}%`

/* ---------- 环图 ---------- */
const donut = computed(() => {
  const s = taskStats.value
  const total = s.total || 1
  const success = Math.round(s.completed / total * 1000) / 10
  const running = Math.round(s.running / total * 1000) / 10
  const abnormal = Math.round(s.abnormal / total * 1000) / 10
  return { success, running, abnormal }
})

/* ---------- 服务运行状态 ---------- */
const services = computed(() => {
  const h = health.value
  if (!h) return []
  const rows: Array<{
    key: string; name: string; detail: string; status: string;
    statusText: string; tone: string; timeText: string; icon: unknown
  }> = h.workers.map((worker: DashboardWorkerStatus) => ({
    key: worker.key,
    name: worker.name,
    detail: t('admin.svcQueue', { queued: worker.queued, capacity: worker.capacity }),
    status: worker.status,
    statusText: worker.status === 'online' ? t('admin.stOnline')
      : worker.status === 'busy' ? t('admin.stBusy') : t('admin.stOffline'),
    tone: worker.status === 'offline' ? 'danger' : worker.status === 'busy' ? 'info' : 'success',
    timeText: worker.last_active_at
      ? t('admin.svcLastActive', { time: formatTime(worker.last_active_at) })
      : t('admin.svcNoActivity'),
    icon: Cpu
  }))

  const componentText = h.components
    .map(item => `${item.name} ${item.latency_ms != null ? item.latency_ms + 'ms' : '—'}`)
    .join(' · ')
  const infraDown = h.components.some(item => item.status === 'down')
  rows.push({
    key: 'infra',
    name: t('admin.infraName'),
    detail: componentText,
    status: infraDown ? 'offline' : 'online',
    statusText: infraDown ? t('admin.stOffline') : t('admin.stOnline'),
    tone: infraDown ? 'danger' : 'success',
    timeText: h.checked_at ? t('admin.updatedAt', { time: formatTime(h.checked_at) }) : '',
    icon: Connection
  })
  return rows
})

const clusterHealthy = computed(() => {
  const h = health.value
  if (!h) return true
  return h.components.every(item => item.status === 'ok')
    && h.workers.every(worker => worker.status !== 'offline')
})

/* ---------- 趋势图 ---------- */
const trendSummary = computed(() => {
  const points = trend.value?.points ?? []
  return {
    total: points.reduce((acc, item) => acc + item.total, 0),
    success: points.reduce((acc, item) => acc + item.success, 0),
    failed: points.reduce((acc, item) => acc + item.failed, 0)
  }
})

const chart = computed(() => {
  const points = trend.value?.points ?? []
  if (points.length === 0) return { line: '', area: '', last: null, axisLabels: [] as string[] }

  const width = 600
  const height = 120
  const padding = 10
  const max = Math.max(...points.map(p => p.total), 1)
  const stepX = points.length > 1 ? width / (points.length - 1) : width
  const coordinates = points.map((point, index) => ({
    x: Math.round(index * stepX * 100) / 100,
    y: Math.round((height - padding - (point.total / max) * (height - padding * 2)) * 100) / 100
  }))
  const line = coordinates.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  const area = `${line} L${width},${height} L0,${height} Z`

  const labelIndexes = points.length > 2
    ? [0, Math.floor((points.length - 1) / 2), points.length - 1]
    : points.map((_, i) => i)

  return {
    line,
    area,
    last: coordinates[coordinates.length - 1],
    axisLabels: labelIndexes.map(i => points[i].label)
  }
})

const switchRange = async (value: DashboardTrendRange) => {
  if (trendRange.value === value) return
  trendRange.value = value
  await loadTrend()
}

/* ---------- 快捷入口 ---------- */
const quickActions = computed(() => [
  {
    label: t('admin.qApprovals'), desc: t('admin.qApprovalsDesc', { n: quick.value.pending_approvals }),
    tone: 'blue', icon: Tickets, path: '/pending-approvals'
  },
  {
    label: t('admin.qKb'), desc: t('admin.qKbDesc', { n: quick.value.kb_count, m: quick.value.doc_total }),
    tone: 'blue', icon: Notebook, path: '/kb-manage'
  },
  {
    label: t('admin.qDocs'), desc: t('admin.qDocsDesc', { n: quick.value.doc_processing }),
    tone: 'dark', icon: Monitor,
    // 直达解析中文档最多的知识库（带状态过滤），无则回落知识库列表
    path: quick.value.processing_kb_uid
      ? `/kb-manage/${quick.value.processing_kb_uid}?status=processing`
      : '/kb-manage'
  },
  {
    label: t('admin.qAlerts'), desc: t('admin.qAlertsDesc', { n: quick.value.doc_failed }),
    tone: 'red', icon: Warning,
    // 直达解析异常文档最多的知识库（带状态过滤），无则回落知识库列表
    path: quick.value.failed_kb_uid
      ? `/kb-manage/${quick.value.failed_kb_uid}?status=failed`
      : '/kb-manage'
  }
])

/* ---------- 格式化 ---------- */
const formatAmount = (amount: string) => {
  const value = Number(amount)
  return Number.isFinite(value)
    ? value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : amount
}

const formatDuration = (ms: number | null) => {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const minutes = Math.floor(ms / 60000)
  const seconds = Math.round((ms % 60000) / 1000)
  return `${minutes}m ${seconds}s`
}

const formatTime = (value: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const statusMeta = (status: string) => {
  const map: Record<string, { label: string; cls: string }> = {
    success: { label: t('admin.runSuccess'), cls: 's-ok' },
    failed: { label: t('admin.runFailed'), cls: 's-fail' },
    cancelled: { label: t('admin.runCancelled'), cls: 's-fail' },
    pending: { label: t('admin.runWaiting'), cls: 's-run' },
    running: { label: t('admin.runRunning'), cls: 's-run' }
  }
  return map[status] ?? { label: t('admin.runWaiting'), cls: 's-run' }
}

/* ---------- 数据加载 ---------- */
const loadTrend = async () => {
  try {
    trend.value = (await getDashboardTrend(trendRange.value)).data
  } catch (error) {
    console.error('加载执行趋势失败', error)
  }
}

const loadAll = async () => {
  if (loading.value) return
  loading.value = true
  try {
    const [summaryData, healthData] = await Promise.all([
      getDashboardSummary(),
      getDashboardHealth(),
      loadTrend()
    ])
    summary.value = summaryData.data
    health.value = healthData.data
  } catch (error) {
    console.error('加载工作台数据失败', error)
    ElMessage.error(t('admin.loadFailed'))
  } finally {
    loading.value = false
  }
}

let healthTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  loadAll()
  // 系统指标与队列心跳每 30 秒刷新一次，业务统计保持进页面时加载
  healthTimer = setInterval(async () => {
    try {
      health.value = (await getDashboardHealth()).data
    } catch (error) {
      console.error('刷新系统健康失败', error)
    }
  }, 30000)
})

onBeforeUnmount(() => {
  if (healthTimer) clearInterval(healthTimer)
  healthTimer = null
})
</script>

<style scoped>
.admin-dashboard { display: flex; flex-direction: column; gap: 16px; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--af-success); }
.dot.green { background: var(--af-success); }
.dot.red { background: var(--af-danger); }

/* ===== 页头 ===== */
.ops-hero {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; flex-wrap: wrap;
}
.ops-badges { display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.ops-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 11px; border-radius: 7px; padding: 4px 11px;
}
.ops-badge.orange { color: var(--af-primary); background: var(--af-primary-soft); }
.ops-badge.green { color: var(--af-success); background: var(--af-success-soft); }
.ops-badge.red { color: var(--af-danger); background: var(--af-danger-soft); }

.ops-title-row { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.ops-title-row h1 { color: var(--af-text); font-size: 30px; font-weight: 800; }
.ops-sub { color: var(--af-text-3); font-size: 13px; }

.ops-head-right { display: flex; align-items: center; gap: 20px; flex-wrap: wrap; }
.ops-metric { display: flex; flex-direction: column; gap: 3px; }
.ops-metric span { color: var(--af-text-3); font-size: 10px; }
.ops-metric b { color: var(--af-text); font-size: 15px; }
.refresh-btn {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--af-primary-gradient);
  border: none; border-radius: 10px;
  color: #fff; font-size: 13px; font-weight: 600;
  padding: 11px 18px;
  cursor: pointer;
}
.refresh-btn:disabled { opacity: 0.7; cursor: default; }

/* ===== 统计卡片 ===== */
.stats-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.stat-card {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius);
  padding: 18px;
  display: flex; flex-direction: column; gap: 10px;
}
.stat-top { display: flex; justify-content: space-between; align-items: center; }
.stat-label { color: var(--af-text-2); font-size: 13px; }
.stat-icon {
  width: 36px; height: 36px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 17px;
}
.stat-icon.blue { background: var(--af-info-soft); color: var(--af-info); }
.stat-icon.green { background: var(--af-success-soft); color: var(--af-success); }
.stat-icon.orange { background: var(--af-primary-soft); color: var(--af-primary); }
.stat-icon.red { background: var(--af-danger-soft); color: var(--af-danger); }
.stat-value-row { display: flex; align-items: center; gap: 10px; }
.stat-value { color: var(--af-text); font-size: 32px; font-weight: 800; }
.stat-trend { font-size: 11px; border-radius: 6px; padding: 2px 8px; }
.stat-trend.up { color: var(--af-success); background: var(--af-success-soft); }
.stat-trend.down { color: var(--af-danger); background: var(--af-danger-soft); }
.stat-foot { display: flex; justify-content: space-between; color: var(--af-text-3); font-size: 11px; }

/* ===== 面板通用 ===== */
.panel { padding: 18px 20px; display: flex; flex-direction: column; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.panel-title { display: flex; align-items: center; gap: 9px; color: var(--af-text); font-size: 15px; font-weight: 700; }
.pt-icon { color: var(--af-primary); font-size: 17px; }
.panel-more { display: inline-flex; align-items: center; gap: 3px; color: var(--af-text-3); font-size: 12px; cursor: pointer; }
.panel-more:hover { color: var(--af-primary); }
.count-badge {
  min-width: 18px; height: 18px; border-radius: 9px;
  background: var(--af-primary); color: #fff;
  font-size: 11px; display: inline-flex; align-items: center; justify-content: center;
  padding: 0 5px;
}
.empty-hint { color: var(--af-text-3); font-size: 12px; text-align: center; padding: 26px 0; }
.panel-foot {
  display: flex; align-items: center; justify-content: space-between;
  color: var(--af-text-3); font-size: 11px;
  border-top: 1px solid var(--af-border-soft);
  margin-top: 10px; padding-top: 10px;
}
.panel-link { color: var(--af-primary); cursor: pointer; }

/* minmax(0, 1fr)：允许网格项收缩到容器宽度，
   防止内部 el-table / 宽内容把轨道撑破视口（移动端截断的根因） */
.middle-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr) minmax(0, 1.2fr); gap: 14px; align-items: stretch; }

/* ===== 环形图 ===== */
.donut-wrap { position: relative; width: 170px; margin: 6px auto 14px; }
.donut { width: 100%; transform: rotate(-90deg); }
.donut-bg { fill: none; stroke: #242424; stroke-width: 3.6; }
.seg { fill: none; stroke-width: 3.6; stroke-linecap: round; }
.seg.success { stroke: var(--af-success); }
.seg.warning { stroke: var(--af-warning); }
.seg.danger { stroke: var(--af-danger); }
.donut-center {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 3px;
}
.donut-center b { color: var(--af-text-3); font-size: 11px; font-weight: 500; }
.donut-center strong { color: var(--af-success); font-size: 26px; font-weight: 800; }
.donut-center span { color: var(--af-text-3); font-size: 10px; }

.donut-legend { display: flex; flex-direction: column; gap: 10px; }
.legend-item { display: flex; align-items: center; gap: 8px; color: var(--af-text-2); font-size: 12px; }
.ldot { width: 8px; height: 8px; border-radius: 50%; }
.ldot.success { background: var(--af-success); }
.ldot.warning { background: var(--af-warning); }
.ldot.danger { background: var(--af-danger); }
.legend-item b { margin-left: auto; color: var(--af-text); }
.legend-item i { width: 48px; text-align: right; color: var(--af-text-3); font-style: normal; }

/* ===== 服务状态列表 ===== */
.agent-list { display: flex; flex-direction: column; gap: 10px; }
.agent-item {
  display: flex; align-items: center; gap: 12px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 12px 14px;
}
.agent-item.danger { border-color: rgba(255, 77, 79, 0.4); background: rgba(255, 77, 79, 0.06); }
.agent-icon {
  width: 36px; height: 36px; flex-shrink: 0;
  border-radius: 10px;
  background: var(--af-hover);
  color: var(--af-text-2);
  display: flex; align-items: center; justify-content: center;
}
.agent-info { flex: 1; min-width: 0; }
.agent-name { color: var(--af-text); font-size: 13px; font-weight: 600; }
.agent-meta { color: var(--af-text-3); font-size: 11px; margin-top: 3px; }
.agent-meta b { color: var(--af-text-2); }
.agent-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; flex-shrink: 0; }
.agent-load { font-size: 11px; border-radius: 5px; padding: 2px 8px; }
.ld-success { color: var(--af-success); background: var(--af-success-soft); }
.ld-info { color: var(--af-text-3); background: var(--af-hover); }
.ld-danger { color: var(--af-danger); background: var(--af-danger-soft); }
.agent-time { color: var(--af-text-3); font-size: 10px; }

/* ===== 待审批 ===== */
.approve-list { display: flex; flex-direction: column; gap: 10px; }
.approve-item {
  display: flex; align-items: center; gap: 10px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 12px 14px;
}
.approve-main { flex: 1; min-width: 0; }
.approve-title { color: var(--af-text); font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.approve-tag { color: var(--af-info); font-size: 10px; background: var(--af-info-soft); border-radius: 5px; padding: 2px 7px; font-weight: 400; }
.approve-meta { color: var(--af-text-3); font-size: 11px; margin-top: 4px; }
.approve-right { display: flex; flex-direction: column; align-items: flex-end; gap: 7px; flex-shrink: 0; }
.approve-amount { color: var(--af-text); font-size: 14px; font-weight: 700; }
.approve-actions { display: flex; align-items: center; gap: 10px; font-size: 11px; }
.approve-actions .go { color: var(--af-primary); cursor: pointer; font-weight: 600; }

/* ===== 吞吐量 ===== */
.range-tabs { display: flex; gap: 4px; background: var(--af-card-soft); border-radius: 8px; padding: 3px; }
.range-tab { color: var(--af-text-3); font-size: 11px; padding: 4px 12px; border-radius: 6px; cursor: pointer; }
.range-tab.active { color: var(--af-text); background: var(--af-hover); }
.throughput-sub { color: var(--af-text-3); font-size: 11px; margin: -8px 0 12px; }
.chart-box { width: 100%; position: relative; }
.throughput-chart { width: 100%; height: 130px; display: block; }
.chart-empty {
  position: absolute; inset: 0 0 26px;
  display: flex; align-items: center; justify-content: center;
  color: var(--af-text-3); font-size: 12px;
}
.chart-axis {
  display: flex; justify-content: space-between;
  color: var(--af-text-3); font-size: 10px;
  border-top: 1px solid var(--af-border-soft);
  padding-top: 8px; flex-wrap: wrap; gap: 6px;
}
.chart-axis .now { color: var(--af-primary); }
.chart-summary { display: flex; gap: 18px; color: var(--af-text-3); font-size: 11px; margin-top: 10px; flex-wrap: wrap; }

/* ===== 底部 ===== */
/* stretch 让左右两个面板顶底边缘对齐（records 高度为准） */
.bottom-grid { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 14px; align-items: stretch; }
.quick-grid {
  flex: 1;
  display: grid; grid-template-columns: 1fr 1fr;
  /* 两行强制等高，并随面板高度撑开：与右侧运行记录面板底边对齐 */
  grid-auto-rows: 1fr;
  gap: 10px;
}
.quick-card {
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 14px;
  display: flex; flex-direction: column; gap: 7px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.quick-card:hover { border-color: rgba(255, 92, 51, 0.4); }
.q-icon {
  width: 34px; height: 34px; border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px;
}
.q-icon.blue { background: var(--af-info-soft); color: var(--af-info); }
.q-icon.dark { background: var(--af-hover); color: var(--af-text-2); }
.q-icon.red { background: var(--af-danger-soft); color: var(--af-danger); }
.q-label { color: var(--af-text); font-size: 12px; font-weight: 600; }
/* 固定两行高度，避免描述文案换行差异导致四张卡高度不一致 */
.q-desc {
  color: var(--af-text-3); font-size: 10px; line-height: 1.4;
  min-height: 28px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}

.status-pill { font-size: 11px; border-radius: 6px; padding: 3px 9px; }
.status-pill.s-ok { color: var(--af-success); background: var(--af-success-soft); }
.status-pill.s-fail { color: var(--af-danger); background: var(--af-danger-soft); }
.status-pill.s-run { color: var(--af-info); background: var(--af-info-soft); }
.table-link { color: var(--af-primary); font-size: 12px; cursor: pointer; }

.table-foot {
  display: flex; justify-content: space-between; align-items: center;
  color: var(--af-text-3); font-size: 11px;
  border-top: 1px solid var(--af-border-soft);
  padding-top: 12px; margin-top: 4px;
  flex-wrap: wrap; gap: 8px;
}
.foot-time { color: var(--af-text-3); }

/* ===== 响应式 ===== */
@media (max-width: 1100px) {
  .middle-grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .middle-grid .panel:first-child { grid-column: 1 / -1; }
  .bottom-grid { grid-template-columns: minmax(0, 1fr); }
  .ops-head-right { width: 100%; justify-content: flex-start; }
}
@media (max-width: 768px) {
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .middle-grid { grid-template-columns: minmax(0, 1fr); }
  .middle-grid .panel:first-child { grid-column: auto; }
  .ops-title-row h1 { font-size: 22px; }
  .refresh-btn { width: 100%; justify-content: center; }
  .ops-metric { flex-direction: row; align-items: center; gap: 8px; }
  .ops-head-right { gap: 14px; }
  /* 运行记录表格横向滚动条常显，提示可滑动 */
  .dark-table :deep(.el-scrollbar__bar.is-horizontal) {
    opacity: 1;
    height: 6px;
  }
  .dark-table :deep(.el-scrollbar__bar.is-horizontal .el-scrollbar__thumb) { opacity: 0.6; }
}
@media (max-width: 480px) {
  /* 小屏快捷通道改单列，卡片完整不拥挤 */
  .quick-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 380px) {
  .stats-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
