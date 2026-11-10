<template>
  <div class="employee-dashboard">
    <!-- ===== 欢迎区 + AI 输入 ===== -->
    <section class="hero-card">
      <div class="hero-head">
        <span class="hero-badge"><span class="dot" /> AgentFlow v2.4 {{ $t('employee.online') }}</span>
      </div>
      <h1 class="hero-title">{{ $t('employee.hello') }}，{{ nickname }} <span class="wave">👋</span></h1>
      <p class="hero-sub">{{ $t('employee.heroSub') }}</p>

      <div class="ai-input-box">
        <el-icon class="sparkle"><MagicStick /></el-icon>
        <input
          v-model="aiQuery"
          type="text"
          :placeholder="$t('employee.aiPlaceholder')"
          @keyup.enter="sendFromInput"
        />
        <button class="send-btn" :aria-label="$t('employee.send')" @click="sendFromInput">
          <el-icon><Top /></el-icon>
        </button>
      </div>

      <div class="quick-row">
        <span class="quick-label">⚡ {{ $t('employee.quickCmds') }}</span>
        <button class="quick-btn" @click="goChat(t('employee.qExpenseMsg'))"><el-icon><DocumentAdd /></el-icon> {{ $t('employee.qExpense') }}</button>
        <button class="quick-btn" @click="goChat(t('employee.qPolicyMsg'))"><el-icon><Search /></el-icon> {{ $t('employee.qPolicy') }}</button>
        <button class="quick-btn" @click="goChat()"><el-icon><ChatDotRound /></el-icon> {{ $t('employee.qChat') }}</button>
      </div>
    </section>

    <!-- ===== 统计卡片（真实统计：我的报销 / 处理中 / 已完成 / AI 会话数） ===== -->
    <section class="stats-grid">
      <div class="stat-card" v-for="stat in statCards" :key="stat.label" @click="router.push(stat.path)">
        <div class="stat-top">
          <span class="stat-label">{{ stat.label }}</span>
          <span class="stat-icon" :class="stat.tone"><el-icon><component :is="stat.icon" /></el-icon></span>
        </div>
        <div class="stat-value">{{ stat.value }}</div>
        <div class="stat-bottom">
          <span class="stat-sub">{{ stat.sub }}</span>
          <span class="stat-link">{{ $t('employee.viewDetail') }} <el-icon><ArrowRight /></el-icon></span>
        </div>
      </div>
    </section>

    <!-- ===== 主区两栏 ===== -->
    <section class="content-grid">
      <div class="main-col">
        <!-- 最近的报销申请（真实数据：我的报销单最近 5 笔） -->
        <div class="af-card panel">
          <div class="panel-head">
            <div class="panel-title"><span class="bar" /> {{ $t('employee.recentExpenses') }} <span class="panel-tag">{{ $t('employee.last30') }}</span></div>
            <span class="panel-more" @click="router.push('/my-claims')">{{ $t('employee.viewAll') }} <el-icon><ArrowRight /></el-icon></span>
          </div>
          <div class="apply-list" v-loading="claimsLoading">
            <div v-if="recentExpenses.length === 0 && !claimsLoading" class="empty-hint">{{ $t('employee.expensesEmpty') }}</div>
            <div v-for="item in recentExpenses" :key="item.claimNo" class="apply-item" @click="router.push('/my-claims')">
              <span class="apply-icon"><el-icon><component :is="item.icon" /></el-icon></span>
              <div class="apply-info">
                <div class="apply-name">{{ item.title }}</div>
                <div class="apply-meta">{{ item.time }} · {{ $t('employee.orderNo') }}#{{ item.claimNo }}</div>
              </div>
              <div class="apply-right">
                <span class="apply-amount">¥{{ item.amount }}</span>
                <span class="apply-status" :class="item.statusClass">{{ item.status }}</span>
              </div>
              <el-icon class="apply-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </div>

        <!-- 最近对话记录（真实数据：我的 AI 会话最近 5 条） -->
        <div class="af-card panel">
          <div class="panel-head">
            <div class="panel-title"><span class="bar" /> {{ $t('employee.recentChats') }} <span class="panel-tag">{{ $t('employee.aiSession') }}</span></div>
            <span class="panel-more" @click="goChat()">{{ $t('employee.viewAll') }} <el-icon><ArrowRight /></el-icon></span>
          </div>
          <div class="apply-list" v-loading="chatsLoading">
            <div v-if="recentChats.length === 0 && !chatsLoading" class="empty-hint">{{ $t('employee.chatsEmpty') }}</div>
            <div v-for="item in recentChats" :key="item.uid" class="apply-item" @click="goChat()">
              <span class="apply-icon chat"><el-icon><component :is="item.icon" /></el-icon></span>
              <div class="apply-info">
                <div class="apply-name">{{ item.title }}</div>
                <div class="apply-meta">{{ item.time }}</div>
              </div>
              <div class="apply-right">
                <span class="chat-tag t-blue">{{ $t('employee.tagRecent') }}</span>
              </div>
              <el-icon class="apply-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </div>

        <!-- 底部横幅 -->
        <div class="af-card engine-banner">
          <span class="engine-icon"><el-icon><DataLine /></el-icon></span>
          <div class="engine-text">
            <b>{{ $t('employee.engineTitle') }}</b>
            <i>{{ $t('employee.engineDesc') }}</i>
          </div>
          <span class="engine-state"><el-icon><Refresh /></el-icon> {{ $t('employee.engineOnline') }}</span>
        </div>
      </div>

      <!-- 右侧栏 -->
      <div class="side-col">
        <!-- 我的待办（真实数据：由我的报销单状态分布派生） -->
        <div class="af-card panel">
          <div class="panel-head">
            <div class="panel-title"><span class="bar" /> {{ $t('employee.myTodos') }} <span class="panel-tag hot">{{ $t('employee.todoTotal', { n: todoTotal }) }}</span></div>
          </div>
          <div class="todo-list">
            <div v-if="todos.length === 0" class="empty-hint">{{ $t('employee.todosEmpty') }}</div>
            <div v-for="(todo, index) in todos" :key="index" class="todo-item">
              <span class="todo-dot" :class="todo.color" />
              <div class="todo-text">{{ todo.text }}</div>
              <span class="todo-count" :class="todo.color">{{ todo.count }}</span>
            </div>
          </div>
        </div>

        <!-- AI 助手 -->
        <div class="af-card ai-helper">
          <div class="ai-head">
            <span class="ai-icon"><el-icon><Service /></el-icon></span>
            <div>
              <div class="ai-name">{{ $t('employee.aiHelper') }}</div>
              <div class="ai-state"><span class="dot green" /> {{ $t('employee.aiStandby') }}</div>
            </div>
          </div>
          <p class="ai-desc">{{ $t('employee.aiDesc') }}</p>
          <p class="ai-desc2">{{ $t('employee.aiDesc2') }}</p>
          <div class="ai-tip"><el-icon><InfoFilled /></el-icon> {{ $t('employee.aiTip') }}</div>
          <button class="ai-btn" @click="goChat()"><el-icon><ChatDotRound /></el-icon> {{ $t('employee.startChat') }}</button>
        </div>

        <!-- 财务制度版本 -->
        <div class="af-card version-card">
          <span class="version-icon"><el-icon><Document /></el-icon></span>
          <span class="version-text">{{ $t('employee.finVersion') }}：2025-05-02</span>
          <span class="version-link">{{ $t('employee.changelog') }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'
import { getClaimStatsApi, listMyClaimsApi, type ClaimStats, type ExpenseClaimItem } from '@/api/expense'
import { getConversationsApi, type ConversationResponse } from '@/api/chat'
import {
  ArrowRight, ChatDotRound, DocumentAdd, Search, Files, Timer,
  CircleCheck, Document, Service, MagicStick, Top, InfoFilled, DataLine, Refresh
} from '@element-plus/icons-vue'

const router = useRouter()
const userStore = useUserStore()
const { t } = useI18n()
const aiQuery = ref('')
const nickname = computed(() => userStore.userInfo?.nickname || userStore.userInfo?.username || t('employee.friend'))

/* 跳转 AI 对话：带 message 时通过路由 query 传给对话页自动发送 */
const goChat = (message?: string) => {
  const text = message?.trim()
  if (text) {
    router.push({ path: '/ai-chat', query: { autoSend: text } })
  } else {
    router.push('/ai-chat')
  }
}

/** 工作台输入框：点击发送 / 回车 => 进入 AI 对话页并发送该内容 */
const sendFromInput = () => {
  const text = aiQuery.value.trim()
  if (!text) return
  aiQuery.value = ''
  goChat(text)
}

/* ---------- 真实数据加载 ---------- */
const claimStats = ref<ClaimStats | null>(null)
const recentClaims = ref<ExpenseClaimItem[]>([])
const conversations = ref<ConversationResponse[]>([])
const claimsLoading = ref(true)
const chatsLoading = ref(true)

const loadDashboard = async () => {
  claimsLoading.value = true
  chatsLoading.value = true
  try {
    // 三个接口相互独立，并行请求；单个失败不阻塞其它区块
    const [statsRes, claimsRes] = await Promise.allSettled([
      getClaimStatsApi(),
      listMyClaimsApi({ page: 1, page_size: 5 })
    ])
    if (statsRes.status === 'fulfilled') claimStats.value = statsRes.value.data
    if (claimsRes.status === 'fulfilled') recentClaims.value = claimsRes.value.data.items
  } finally {
    claimsLoading.value = false
  }
  try {
    const convRes = await getConversationsApi()
    conversations.value = convRes.data.items ?? []
  } finally {
    chatsLoading.value = false
  }
}
onMounted(loadDashboard)

const formatTime = (value: string | null) =>
  value ? value.replace('T', ' ').slice(0, 16) : '-'

/* ---------- 统计卡（真实统计） ---------- */
const statCards = computed(() => {
  const s = claimStats.value
  return [
    { label: t('employee.statMyExpenses'), value: s ? s.total : '-', sub: s ? t('employee.statMyExpensesSub', { n: s.month_count }) : t('employee.statMyExpensesSub', { n: 0 }), tone: 'orange', icon: Files, path: '/my-claims' },
    { label: t('employee.statProcessing'), value: s ? s.in_progress : '-', sub: t('employee.statProcessingSub'), tone: 'blue', icon: Timer, path: '/my-claims' },
    { label: t('employee.statDone'), value: s ? s.completed : '-', sub: t('employee.statDoneSub'), tone: 'green', icon: CircleCheck, path: '/my-claims' },
    { label: t('employee.statChats'), value: conversations.value.length || (chatsLoading.value ? '-' : 0), sub: t('employee.statChatsSub'), tone: 'purple', icon: ChatDotRound, path: '/ai-chat' }
  ]
})

/* ---------- 最近的报销申请（真实列表，状态沿用 claims.status.* 文案） ---------- */
const claimStatusClass = (s: string) => {
  const map: Record<string, string> = {
    draft: 's-info', needs_info: 's-warn', pending_approval: 's-warn',
    processing: 's-info', approved: 's-ok', rejected: 's-fail',
    completed: 's-ok', failed: 's-fail'
  }
  return map[s] ?? 's-info'
}

const recentExpenses = computed(() =>
  recentClaims.value.map((item) => ({
    title: item.title,
    time: formatTime(item.submitted_at || item.created_at),
    claimNo: item.claim_no,
    amount: Number(item.total_amount).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
    status: t(`claims.status.${item.status}`),
    statusClass: claimStatusClass(item.status),
    icon: Document
  }))
)

/* ---------- 最近对话记录（真实会话列表） ---------- */
const recentChats = computed(() =>
  conversations.value.slice(0, 5).map((item) => ({
    uid: item.uid,
    title: item.title,
    time: `${t('employee.lastActive')} ${formatTime(item.updated_at || item.created_at)}`,
    icon: ChatDotRound
  }))
)

/* ---------- 我的待办（由报销单状态分布派生，无假数据） ---------- */
const todos = computed(() => {
  const counts = claimStats.value?.status_counts ?? {}
  const result: { text: string; count: number; color: string }[] = []
  const push = (text: string, count: number | undefined, color: string) => {
    if (count) result.push({ text, count, color })
  }
  push(t('employee.todoApproving'), claimStats.value?.in_progress, 'c-green')
  push(t('employee.todoSupplement'), counts.needs_info, 'c-blue')
  push(t('employee.todoRejected'), counts.rejected, 'c-red')
  push(t('employee.todoMonth'), claimStats.value?.month_count, 'c-purple')
  return result
})
const todoTotal = computed(() => todos.value.reduce((sum, item) => sum + item.count, 0))
</script>

<style scoped>
.employee-dashboard { display: flex; flex-direction: column; gap: 16px; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--af-primary); }
.dot.green { background: var(--af-success); }

/* ===== 欢迎区 ===== */
.hero-card {
  background:
    radial-gradient(ellipse 70% 120% at 85% 0%, rgba(245, 73, 31, 0.16), transparent 60%),
    var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius);
  padding: 24px 26px;
}
.hero-head { margin-bottom: 14px; }
.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  color: var(--af-text-2); font-size: 12px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: 20px;
  padding: 5px 14px;
}
.hero-title { color: var(--af-text); font-size: 28px; font-weight: 800; margin-bottom: 8px; }
.wave { font-size: 24px; }
.hero-sub { color: var(--af-text-2); font-size: 13px; margin-bottom: 20px; }

.ai-input-box {
  display: flex; align-items: center; gap: 10px;
  background: #101010;
  border: 1px solid var(--af-border);
  border-radius: 12px;
  padding: 8px 8px 8px 16px;
}
.ai-input-box:focus-within { border-color: rgba(255, 92, 51, 0.5); }
.sparkle { color: var(--af-primary); font-size: 17px; flex-shrink: 0; }
.ai-input-box input {
  flex: 1; min-width: 0;
  background: transparent; border: none; outline: none;
  color: var(--af-text); font-size: 13px;
}
.ai-input-box input::placeholder { color: var(--af-text-3); }
.send-btn {
  width: 40px; height: 40px; flex-shrink: 0;
  border-radius: 10px;
  background: var(--af-primary-gradient);
  color: #fff; font-size: 17px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer;
  min-height: 44px; min-width: 44px;
}

.quick-row { display: flex; align-items: center; gap: 10px; margin-top: 16px; flex-wrap: wrap; }
.quick-label { color: var(--af-text-3); font-size: 12px; }
.quick-btn {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--af-text-2);
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: 8px;
  padding: 7px 13px;
  font-size: 12px;
  cursor: pointer;
  min-height: 34px;
  transition: all 0.15s;
}
.quick-btn:hover { color: var(--af-primary); border-color: rgba(255, 92, 51, 0.4); }

/* ===== 统计卡片 ===== */
.stats-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.stat-card {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius);
  padding: 18px;
  display: flex; flex-direction: column; gap: 8px;
}
.stat-top { display: flex; justify-content: space-between; align-items: center; }
.stat-label { color: var(--af-text); font-size: 14px; font-weight: 600; }
.stat-icon {
  width: 38px; height: 38px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.stat-icon.orange { background: rgba(255, 92, 51, 0.14); color: #ff6a3d; }
.stat-icon.blue { background: var(--af-info-soft); color: var(--af-info); }
.stat-icon.green { background: var(--af-success-soft); color: var(--af-success); }
.stat-icon.purple { background: rgba(155, 110, 255, 0.14); color: #9b6eff; }
.stat-value { color: var(--af-text); font-size: 30px; font-weight: 800; }
.stat-bottom { display: flex; justify-content: space-between; align-items: center; }
.stat-sub { color: var(--af-text-3); font-size: 11px; }
.stat-link { display: inline-flex; align-items: center; gap: 3px; color: var(--af-text-2); font-size: 11px; cursor: pointer; }
.stat-link:hover { color: var(--af-primary); }

/* ===== 主区两栏 ===== */
.content-grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 16px; align-items: start; }
.main-col { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.side-col { display: flex; flex-direction: column; gap: 16px; }

.panel { padding: 18px 20px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.panel-title { display: flex; align-items: center; gap: 9px; color: var(--af-text); font-size: 15px; font-weight: 700; }
.bar { width: 3px; height: 15px; border-radius: 2px; background: var(--af-primary); }
.panel-tag {
  color: var(--af-text-3); font-size: 10px;
  background: var(--af-card-soft);
  border-radius: 5px; padding: 2px 8px;
}
.panel-tag.hot { color: var(--af-primary); background: var(--af-primary-soft); }
.panel-more { display: inline-flex; align-items: center; gap: 3px; color: var(--af-text-3); font-size: 12px; cursor: pointer; }
.panel-more:hover { color: var(--af-primary); }

.apply-list { display: flex; flex-direction: column; gap: 10px; }
.apply-item {
  display: flex; align-items: center; gap: 12px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 12px 14px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.apply-item:hover { border-color: rgba(255, 92, 51, 0.35); }
.apply-icon {
  width: 38px; height: 38px; flex-shrink: 0;
  border-radius: 10px;
  background: var(--af-hover);
  color: var(--af-text-2);
  display: flex; align-items: center; justify-content: center;
  font-size: 17px;
}
.apply-icon.chat { background: var(--af-info-soft); color: var(--af-info); }
.apply-info { flex: 1; min-width: 0; }
.apply-name { color: var(--af-text); font-size: 13px; font-weight: 600; margin-bottom: 3px; }
.apply-meta { color: var(--af-text-3); font-size: 11px; }
.apply-right { display: flex; flex-direction: column; align-items: flex-end; gap: 5px; flex-shrink: 0; }
.apply-amount { color: var(--af-text); font-size: 14px; font-weight: 700; }
.apply-status { font-size: 10px; border-radius: 5px; padding: 2px 8px; }
.s-warn { color: var(--af-warning); background: var(--af-warning-soft); }
.s-ok { color: var(--af-success); background: var(--af-success-soft); }
.s-info { color: var(--af-info); background: var(--af-info-soft); }
.s-fail { color: var(--af-danger); background: var(--af-danger-soft); }
.empty-hint { color: var(--af-text-3); font-size: 12px; text-align: center; padding: 18px 0; }
.chat-tag { font-size: 10px; border-radius: 5px; padding: 3px 8px; }
.t-blue { color: var(--af-info); background: var(--af-info-soft); }
.t-green { color: var(--af-success); background: var(--af-success-soft); }
.t-orange { color: var(--af-primary); background: var(--af-primary-soft); }
.apply-arrow { color: var(--af-text-3); font-size: 13px; flex-shrink: 0; }

/* 底部横幅 */
.engine-banner {
  display: flex; align-items: center; gap: 14px;
  padding: 16px 20px;
}
.engine-icon {
  width: 40px; height: 40px; flex-shrink: 0;
  border-radius: 10px;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  display: flex; align-items: center; justify-content: center;
  font-size: 19px;
}
.engine-text { flex: 1; min-width: 0; }
.engine-text b { display: block; color: var(--af-text); font-size: 13px; }
.engine-text i { display: block; color: var(--af-text-3); font-size: 11px; font-style: normal; margin-top: 3px; }
.engine-state { display: inline-flex; align-items: center; gap: 5px; color: var(--af-success); font-size: 11px; flex-shrink: 0; }

/* 我的待办 */
.todo-list { display: flex; flex-direction: column; gap: 12px; }
.todo-item {
  display: flex; align-items: center; gap: 10px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 12px 14px;
}
.todo-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.c-red { background: var(--af-danger); }
.c-red.todo-dot { background: var(--af-danger); }
.c-green { background: var(--af-success); }
.c-blue { background: var(--af-info); }
.c-purple { background: #9b6eff; }
.todo-dot.c-red { background: var(--af-danger); }
.todo-text { flex: 1; color: var(--af-text-2); font-size: 12px; }
.todo-count {
  width: 22px; height: 22px; flex-shrink: 0;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: #fff;
}

/* AI 助手卡片 */
.ai-helper { padding: 20px; }
.ai-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.ai-icon {
  width: 42px; height: 42px; border-radius: 12px;
  background: var(--af-primary-gradient);
  color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
}
.ai-name { color: var(--af-text); font-size: 15px; font-weight: 700; }
.ai-state { display: flex; align-items: center; gap: 5px; color: var(--af-text-3); font-size: 11px; margin-top: 2px; }
.ai-desc { color: var(--af-text-2); font-size: 12px; margin-bottom: 8px; }
.ai-desc2 { color: var(--af-text-3); font-size: 11px; line-height: 1.8; margin-bottom: 14px; }
.ai-tip {
  display: flex; gap: 6px;
  color: var(--af-text-3); font-size: 10px;
  background: var(--af-card-soft);
  border-radius: 8px;
  padding: 9px 10px;
  margin-bottom: 14px;
  line-height: 1.6;
}
.ai-tip .el-icon { flex-shrink: 0; margin-top: 1px; }
.ai-btn {
  width: 100%; height: 44px;
  border: none; border-radius: 10px;
  background: var(--af-primary-gradient);
  color: #fff; font-size: 14px; font-weight: 600;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  cursor: pointer;
}
.ai-btn:hover { opacity: 0.9; }

/* 版本卡片 */
.version-card { display: flex; align-items: center; gap: 10px; padding: 14px 16px; }
.version-icon { color: var(--af-text-3); font-size: 16px; }
.version-text { flex: 1; color: var(--af-text-3); font-size: 11px; }
.version-link { color: var(--af-text-2); font-size: 11px; cursor: pointer; }

/* ===== 响应式 ===== */
@media (max-width: 1100px) {
  .content-grid { grid-template-columns: minmax(0, 1fr); }
  .side-col { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); align-items: start; }
}
@media (max-width: 768px) {
  .stats-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .side-col { grid-template-columns: minmax(0, 1fr); }
  .hero-title { font-size: 22px; }
  .hero-card { padding: 18px; }
  .quick-row .quick-label { width: 100%; }
  .apply-right { align-items: flex-end; }
}
@media (max-width: 380px) {
  .stats-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
