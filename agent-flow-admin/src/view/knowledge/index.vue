<template>
  <div class="kb-page">
    <!-- ===== 页头 ===== -->
    <section class="kb-hero">
      <div class="hero-left">
        <div class="hero-title-row">
          <h1>{{ $t('nav.knowledge') }}</h1>
          <span class="hero-tag">{{ $t('kb.heroTag') }}</span>
        </div>
        <p class="hero-desc">{{ $t('kb.heroDesc') }}</p>
      </div>
      <div class="hero-actions">
        <div class="hero-search">
          <el-icon><Search /></el-icon>
          <input v-model="keyword" type="text" :placeholder="$t('kb.searchPlaceholder')" />
        </div>
        <button class="create-btn" @click="openCreate"><el-icon><Plus /></el-icon> {{ $t('kb.createKb') }}</button>
      </div>
    </section>

    <!-- ===== 统计卡片 ===== -->
    <section class="stats-grid">
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">{{ $t('kb.statKbTotal') }}</span>
          <span class="stat-icon blue"><el-icon><Collection /></el-icon></span>
        </div>
        <div class="stat-value-row"><span class="stat-value">{{ kbOverview.kbCount }}</span><span class="stat-trend">{{ overviewSubs.kb }}</span></div>
        <div class="stat-bar"><span class="bar-fill blue" /></div>
      </div>
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">{{ $t('kb.statDocsTotal') }}</span>
          <span class="stat-icon green"><el-icon><Document /></el-icon></span>
        </div>
        <div class="stat-value-row"><span class="stat-value">{{ kbOverview.totalDocs }}</span><span class="stat-trend">{{ overviewSubs.docs }}</span></div>
        <div class="stat-bar"><span class="bar-fill green" /></div>
      </div>
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">{{ $t('kb.statIndexed') }}</span>
          <span class="stat-icon purple"><el-icon><CircleCheck /></el-icon></span>
        </div>
        <div class="stat-value-row"><span class="stat-value">{{ kbOverview.indexed }}</span><span class="stat-trend">{{ overviewSubs.indexed }}</span></div>
        <div class="stat-bar"><span class="bar-fill purple" /></div>
      </div>
      <div class="stat-card">
        <div class="stat-top">
          <span class="stat-label">{{ $t('kb.statProcessing') }}</span>
          <span class="stat-icon orange"><el-icon><Loading /></el-icon></span>
        </div>
        <div class="stat-value-row"><span class="stat-value">{{ kbOverview.processing }}</span><span class="stat-trend">{{ overviewSubs.processing }}</span></div>
        <div class="stat-bar"><span class="bar-fill orange" /></div>
      </div>
    </section>

    <!-- ===== 主体两栏 ===== -->
    <section class="content-grid">
      <div class="main-col">
        <!-- 筛选 -->
        <div class="filter-row">
          <div class="filter-tabs">
            <span class="filter-tab active">{{ $t('kb.allTab', { n: filteredList.length }) }}</span>
          </div>
          <span class="filter-tools"><el-icon><Refresh /></el-icon><el-icon><Filter /></el-icon></span>
        </div>

        <!-- PC 表格 -->
        <div class="af-card table-card">
          <el-table :data="filteredList" class="dark-table" @row-click="(row: KnowledgeBaseView) => goDetail(row.uid)">
            <el-table-column :label="$t('kb.colName')" min-width="200">
              <template #default="{ row }">
                <div class="name-cell">
                  <div class="kb-icon"><el-icon><Reading /></el-icon></div>
                  <div class="name-info">
                    <div class="kb-name-row">
                      <div class="kb-name">{{ row.name }}</div>
                      <span class="kb-type-tag" :class="row.visibility">
                        {{ visibilityLabel(row) }}
                      </span>
                      <span v-if="row.permission === 'read'" class="kb-type-tag readonly">
                        {{ $t('kb.readOnly') }}
                      </span>
                    </div>
                    <div class="kb-id">ID: {{ row.uid }}</div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="description" :label="$t('kb.colDesc')" min-width="180" show-overflow-tooltip />
            <el-table-column :label="$t('kb.colDocCount')" width="110" align="center">
              <template #default="{ row }">
                <span class="doc-count">{{ kbDocStats(row.uid).total }} <i>{{ $t('kb.docsUnit') }}</i></span>
              </template>
            </el-table-column>
            <el-table-column prop="creator" :label="$t('kb.colCreator')" width="100" />
            <el-table-column prop="createdAt" :label="$t('kb.colCreatedAt')" width="150" />
            <el-table-column :label="$t('common.actions')" width="150" fixed="right">
              <template #default="{ row }">
                <!-- manage：进入管理 + 编辑/删除；read：只给查看入口 -->
                <span class="table-link" @click.stop="goDetail(row.uid)">
                  {{ canManage(row) ? $t('kb.enterManage') : $t('kb.viewOnly') }}
                </span>
                <el-dropdown
                  v-if="canManage(row)"
                  trigger="click"
                  @command="(cmd: string) => handleMore(cmd, row)"
                >
                  <span class="table-link more" @click.stop><el-icon><MoreFilled /></el-icon></span>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="permission">{{ $t('kb.permMenu') }}</el-dropdown-item>
                      <el-dropdown-item command="edit">{{ $t('common.edit') }}</el-dropdown-item>
                      <el-dropdown-item command="delete" divided>{{ $t('common.del') }}</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
                <span v-else class="perm-hint" :title="$t('kb.readOnlyHint')">
                  {{ $t('kb.readOnly') }}
                </span>
              </template>
            </el-table-column>
          </el-table>
          <div class="table-foot">{{ $t('kb.tableFoot', { total: filteredList.length, shown: filteredList.length }) }}</div>
        </div>

        <!-- 移动端卡片列表 -->
        <div class="mobile-list">
          <div class="af-card kb-card" v-for="row in filteredList" :key="row.uid" @click="goDetail(row.uid)">
            <div class="kb-card-head">
              <div class="kb-icon"><el-icon><Reading /></el-icon></div>
              <div class="name-info">
                <div class="kb-name-row">
                  <div class="kb-name">{{ row.name }}</div>
                  <span class="kb-type-tag" :class="row.visibility">{{ visibilityLabel(row) }}</span>
                </div>
                <div class="kb-id">ID: {{ row.uid }}</div>
              </div>
              <el-icon class="kb-arrow"><ArrowRight /></el-icon>
            </div>
            <p class="kb-desc">{{ row.description }}</p>
            <div class="kb-card-foot">
              <span><el-icon><Document /></el-icon> {{ $t('kb.docsCount', { n: kbDocStats(row.uid).total }) }}</span>
              <span><el-icon><User /></el-icon> {{ row.creator }}</span>
              <span class="kb-card-time">{{ row.updatedAt }}</span>
            </div>
            <div class="kb-card-ops">
              <span class="table-link" @click.stop="goDetail(row.uid)">
                {{ canManage(row) ? $t('kb.enterManage') : $t('kb.viewOnly') }}
              </span>
              <template v-if="canManage(row)">
                <span class="table-link" @click.stop="openPermission(row)">{{ $t('kb.permMenu') }}</span>
                <span class="table-link" @click.stop="openEdit(row)">{{ $t('common.edit') }}</span>
                <span class="table-link danger" @click.stop="handleMore('delete', row)">{{ $t('common.del') }}</span>
              </template>
              <span v-else class="perm-hint">{{ $t('kb.readOnlyHint') }}</span>
            </div>
          </div>
          <div v-if="filteredList.length === 0" class="mobile-empty">{{ $t('kb.mobileEmpty') }}</div>
        </div>

        <!-- 引擎横幅 -->
        <div class="af-card engine-banner">
          <div class="engine-left">
            <span class="engine-icon"><el-icon><Coin /></el-icon></span>
            <div class="engine-text">
              <b>{{ $t('kb.engineTitle') }}</b>
              <i>{{ $t('kb.engineDesc') }}</i>
            </div>
          </div>
          <span class="engine-setting">{{ $t('kb.engineConfig') }}</span>
        </div>
      </div>

      <!-- 右侧栏 -->
      <div class="side-col">
        <div class="af-card panel">
          <div class="panel-head">
            <div class="panel-title">{{ $t('kb.panelHealth') }}</div>
            <el-icon class="panel-more"><MoreFilled /></el-icon>
          </div>
          <div class="gauge-wrap">
            <svg viewBox="0 0 120 72" class="gauge">
              <path d="M 10 66 A 50 50 0 0 1 110 66" fill="none" stroke="#242424" stroke-width="9" stroke-linecap="round" />
              <path d="M 10 66 A 50 50 0 0 1 110 66" fill="none" stroke="url(#gaugeGrad)" stroke-width="9" stroke-linecap="round" :stroke-dasharray="`${gaugeDash} 200`" />
              <defs>
                <linearGradient id="gaugeGrad" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stop-color="#2ecc71" />
                  <stop offset="70%" stop-color="#2ecc71" />
                  <stop offset="100%" stop-color="#ff5c33" />
                </linearGradient>
              </defs>
            </svg>
            <div class="gauge-center"><b>{{ gaugePercent }}%</b><span>{{ $t('kb.gaugeLabel') }}</span></div>
          </div>
          <div class="gauge-legend">
            <div class="gl-item"><span class="dot green" /> {{ $t('kb.legendIndexed') }}</div>
            <div class="gl-item"><span class="dot" /> {{ $t('kb.legendWaiting') }}</div>
          </div>
          <div class="gauge-stats">
            <div class="gs-item"><b>{{ kbOverview.indexed }}</b><span>{{ $t('kb.gsIndexed') }}</span></div>
            <div class="gs-item"><b>{{ kbOverview.processing }}</b><span>{{ $t('kb.gsProcessing') }}</span></div>
          </div>
        </div>

        <div class="af-card panel">
          <div class="panel-head">
            <div class="panel-title">{{ $t('kb.panelFeeds') }}</div>
          </div>
          <div class="feed-list">
            <div class="feed-item" v-for="(feed, i) in feeds" :key="i">
              <span class="feed-icon" :class="feed.tone"><el-icon><component :is="feed.icon" /></el-icon></span>
              <div class="feed-info">
                <div class="feed-name">{{ feed.name }}</div>
                <div class="feed-meta">{{ feed.desc }}</div>
              </div>
            </div>
            <div v-if="feeds.length === 0" class="feed-empty">{{ $t('kb.feedsEmpty') }}</div>
          </div>
        </div>

        <div class="af-card agent-panel">
          <div class="agent-icon"><el-icon><ChatDotRound /></el-icon></div>
          <div class="agent-text">
            <b>{{ $t('kb.agentTitle') }}</b>
            <p>{{ $t('kb.agentDesc') }}</p>
          </div>
        </div>

      </div>
    </section>

    <!-- ===== 弹窗 ===== -->
    <el-dialog v-model="dialogVisible" :title="$t('kb.editKb')" width="480px" class="af-dialog">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item :label="$t('kb.labelName')" prop="name">
          <el-input v-model="form.name" :placeholder="$t('kb.phName')" maxlength="30" show-word-limit />
        </el-form-item>
        <el-form-item :label="$t('kb.labelDesc')" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" :placeholder="$t('kb.phDesc')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" @click="submitForm">{{ $t('common.confirm') }}</el-button>
      </template>
    </el-dialog>

    <PermissionDialog
      v-if="permissionKb"
      v-model="permissionVisible"
      :kb-uid="permissionKb.uid"
      :kb-name="permissionKb.name"
      :visibility="permissionKb.visibility"
    />

    <CreateKbDialog v-model="createVisible" @created="loadKnowledgeBases" />

    <DeleteKbDialog v-model="deleteVisible" :kb="deleteKb" @deleted="loadKnowledgeBases" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import {
  Search, Plus, Collection, Document, Loading, MoreFilled,
  ArrowRight, Reading, User, Refresh, Filter, Coin,
  CircleCheck, CircleClose, ChatDotRound
} from '@element-plus/icons-vue'
import {
  getKnowledgeOverview, listKnowledgeBases, updateKnowledgeBase,
  type KnowledgeBaseDto, type KnowledgeOverview
} from '@/api/knowledge'
import PermissionDialog from './PermissionDialog.vue'
import CreateKbDialog from './CreateKbDialog.vue'
import DeleteKbDialog from './DeleteKbDialog.vue'

interface KnowledgeBaseView {
  uid: string
  name: string
  description: string
  creator: string
  createdAt: string
  updatedAt: string
  status: 'normal'
  /** shared 企业共享 / private 私有 */
  visibility: 'shared' | 'private'
  /** 当前用户有效权限：read 只读 / manage 可管理 / null 无权限 */
  permission: 'read' | 'manage' | null
}

const router = useRouter()
const { t } = useI18n()
const keyword = ref('')
const dialogVisible = ref(false)
const editing = ref<KnowledgeBaseView | null>(null)
/** 成员授权弹窗 */
const permissionVisible = ref(false)
const permissionKb = ref<KnowledgeBaseView | null>(null)
/** 创建知识库弹窗（按设计稿还原的富表单） */
const createVisible = ref(false)
/** 删除知识库弹窗（按设计稿还原的高危确认） */
const deleteVisible = ref(false)
const deleteKb = ref<KnowledgeBaseView | null>(null)
const formRef = ref<FormInstance>()
const form = reactive({ name: '', description: '' })
const knowledgeBases = ref<KnowledgeBaseView[]>([])
const rules = computed<FormRules>(() => ({
  name: [{ required: true, message: t('kb.ruleName'), trigger: 'blur' }]
}))

/** 最近解析动态：来自总览接口的真实文档（含状态着色与所属知识库） */
const feeds = computed(() =>
  (overview.value?.recent_documents ?? []).map((doc) => {
    const tone = doc.status === 'indexed' ? 'green' : doc.status === 'failed' ? 'red' : 'blue'
    const icon = doc.status === 'indexed' ? CircleCheck : doc.status === 'failed' ? CircleClose : Loading
    return { name: doc.title, desc: `${doc.kb_name} · ${formatDate(doc.created_at)}`, tone, icon }
  })
)

const formatDate = (value: string) => value ? value.replace('T', ' ').slice(0, 16) : '-'
const toView = (item: KnowledgeBaseDto): KnowledgeBaseView => ({
  uid: item.uid,
  name: item.name,
  description: item.description || '-',
  creator: item.created_by || '-',
  createdAt: formatDate(item.created_at),
  updatedAt: formatDate(item.updated_at),
  status: 'normal',
  visibility: item.visibility === 'shared' ? 'shared' : 'private',
  permission: item.permission ?? null
})

/** 是否可管理：仅 manage 显示编辑/删除；read 只给查看入口 */
const canManage = (row: KnowledgeBaseView) => row.permission === 'manage'
const visibilityLabel = (row: KnowledgeBaseView) =>
  row.visibility === 'shared' ? t('kb.typeShared') : t('kb.typePrivate')

const loadKnowledgeBases = async () => {
  const [listRes, overviewRes] = await Promise.all([
    listKnowledgeBases(),
    getKnowledgeOverview().catch(() => null) // 总览失败不阻塞列表
  ])
  knowledgeBases.value = listRes.data.items.map(toView)
  if (overviewRes) overview.value = overviewRes.data
}

const filteredList = computed(() => {
  const q = keyword.value.trim()
  if (!q) return knowledgeBases.value
  return knowledgeBases.value.filter((item) => item.name.includes(q) || item.description.includes(q))
})

const overview = ref<KnowledgeOverview | null>(null)

const kbOverview = computed(() => ({
  kbCount: overview.value?.kb_count ?? knowledgeBases.value.length,
  totalDocs: overview.value?.total_docs ?? 0,
  indexed: overview.value?.indexed_docs ?? 0,
  processing: overview.value?.processing_docs ?? 0
}))

/** 列表"文档数量"列：按知识库 uid 查总览返回的计数 */
const docCountMap = computed(() => {
  const map = new Map<string, { total: number; indexed: number; processing: number }>()
  overview.value?.kb_doc_counts.forEach((item) => map.set(item.kb_uid, item))
  return map
})
const kbDocStats = (uid: string) => docCountMap.value.get(uid) ?? { total: 0, indexed: 0, processing: 0 }

// 索引完成率（仪表盘）：已索引 / 文档总数，弧长按半圆周长 157 换算
const gaugePercent = computed(() => {
  const { totalDocs, indexed } = kbOverview.value
  return totalDocs > 0 ? Math.round((indexed / totalDocs) * 100) : 0
})
const gaugeDash = computed(() => (157 * gaugePercent.value) / 100)

// 卡片副标题：全部用真实统计替代原来的假环比
const overviewSubs = computed(() => {
  const o = kbOverview.value
  const sharedCount = knowledgeBases.value.filter((item) => item.visibility === 'shared').length
  return {
    kb: t('kb.statKbSub', { n: sharedCount }),
    docs: t('kb.statDocsSub', { n: o.kbCount }),
    indexed: t('kb.statIndexedSub', { n: gaugePercent.value }),
    processing: o.processing > 0 ? t('kb.statProcessingBusy') : t('kb.statProcessingIdle')
  }
})

const goDetail = (uid: string) => router.push(`/kb-manage/${uid}`)

const openCreate = () => {
  createVisible.value = true
}

const openEdit = (row: KnowledgeBaseView) => {
  editing.value = row
  form.name = row.name
  form.description = row.description === '-' ? '' : row.description
  dialogVisible.value = true
}

/** 打开成员授权弹窗（仅 manage 可用） */
const openPermission = (row: KnowledgeBaseView) => {
  permissionKb.value = row
  permissionVisible.value = true
}

const submitForm = async () => {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  const payload = { name: form.name, description: form.description }
  await updateKnowledgeBase(editing.value!.uid, payload)
  ElMessage.success(t('kb.kbUpdated'))
  dialogVisible.value = false
  await loadKnowledgeBases()
}

const handleMore = (cmd: string, row: KnowledgeBaseView) => {
  if (cmd === 'permission') {
    openPermission(row)
    return
  }
  if (cmd === 'edit') {
    openEdit(row)
    return
  }
  if (cmd === 'delete') {
    deleteKb.value = row
    deleteVisible.value = true
  }
}

onMounted(loadKnowledgeBases)
</script>

<style scoped>
.kb-page { display: flex; flex-direction: column; gap: 16px; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--af-primary); }
.dot.green { background: var(--af-success); }

/* ===== 页头 ===== */
.kb-hero { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; flex-wrap: wrap; }
.hero-title-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.hero-title-row h1 { color: var(--af-text); font-size: 26px; font-weight: 800; }
.hero-tag { color: var(--af-text-3); font-size: 11px; border: 1px solid var(--af-border); border-radius: 6px; padding: 3px 9px; }
.hero-desc { color: var(--af-text-3); font-size: 12px; max-width: 480px; line-height: 1.8; }
.hero-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.hero-search {
  display: flex; align-items: center; gap: 8px;
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: 10px;
  padding: 9px 13px;
  width: 240px;
  color: var(--af-text-3);
}
.hero-search input { flex: 1; min-width: 0; background: transparent; border: none; outline: none; color: var(--af-text); font-size: 13px; }
.create-btn {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--af-primary-gradient);
  border: none; border-radius: 10px;
  color: #fff; font-size: 13px; font-weight: 600;
  padding: 11px 18px;
  cursor: pointer;
  min-height: 42px;
}

/* ===== 统计卡片 ===== */
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
.stat-card {
  background: var(--af-card);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius);
  padding: 16px 18px;
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
.stat-icon.purple { background: rgba(155, 110, 255, 0.14); color: #9b6eff; }
.stat-icon.orange { background: var(--af-primary-soft); color: var(--af-primary); }
.stat-value-row { display: flex; align-items: center; justify-content: space-between; }
.stat-value { color: var(--af-text); font-size: 28px; font-weight: 800; }
.stat-trend { color: var(--af-success); font-size: 11px; }
.stat-bar { height: 3px; border-radius: 2px; background: #242424; overflow: hidden; }
.bar-fill { display: block; height: 100%; border-radius: 2px; }
.bar-fill.blue { width: 60%; background: var(--af-info); }
.bar-fill.green { width: 75%; background: var(--af-success); }
.bar-fill.purple { width: 85%; background: #9b6eff; }
.bar-fill.orange { width: 30%; background: var(--af-primary); }

/* ===== 主体 ===== */
.content-grid { display: grid; grid-template-columns: 1fr 300px; gap: 16px; align-items: start; }
.main-col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.side-col { display: flex; flex-direction: column; gap: 14px; }

.filter-row { display: flex; justify-content: space-between; align-items: center; background: var(--af-card); border: 1px solid var(--af-border-soft); border-radius: var(--af-radius-sm); padding: 10px 16px; }
.filter-tabs { display: flex; gap: 8px; }
.filter-tab { color: var(--af-text-3); font-size: 12px; padding: 5px 12px; border-radius: 8px; cursor: pointer; }
.filter-tab.active { color: #fff; background: var(--af-primary); }
.filter-tools { display: flex; gap: 12px; color: var(--af-text-3); font-size: 14px; }

.table-card { padding: 6px 0 0; overflow: hidden; }
.dark-table { --el-table-row-hover-bg-color: #1f1f1f; cursor: pointer; }
.name-cell { display: flex; align-items: center; gap: 11px; }
.kb-icon {
  width: 38px; height: 38px; flex-shrink: 0;
  border-radius: 10px;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.name-info { min-width: 0; }
.kb-name-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.kb-name { color: var(--af-text); font-size: 13px; font-weight: 600; }
.kb-type-tag {
  font-size: 10px; line-height: 1.6; padding: 1px 7px; border-radius: 5px;
  border: 1px solid transparent; white-space: nowrap;
}
.kb-type-tag.shared { color: var(--af-info); background: var(--af-info-soft); border-color: rgba(77, 141, 255, 0.25); }
.kb-type-tag.private { color: var(--af-text-2); background: var(--af-hover); border-color: var(--af-border-soft); }
.kb-type-tag.readonly { color: var(--af-warning); background: var(--af-warning-soft); border-color: rgba(245, 166, 35, 0.25); }
.perm-hint { color: var(--af-text-3); font-size: 11px; }
.kb-name { color: var(--af-text); font-size: 13px; font-weight: 600; }
.kb-id { color: var(--af-text-3); font-size: 11px; margin-top: 2px; }
.doc-count { color: var(--af-text); font-size: 13px; font-weight: 700; }
.doc-count i { font-size: 10px; color: var(--af-text-3); font-style: normal; font-weight: 400; }
.table-link { color: var(--af-primary); font-size: 12px; cursor: pointer; margin-right: 10px; }
.table-link.more { margin-right: 0; color: var(--af-text-3); }
.table-link.danger { color: var(--af-danger); }
.table-foot { color: var(--af-text-3); font-size: 11px; padding: 12px 16px; border-top: 1px solid var(--af-border-soft); }

/* 移动端卡片列表 */
.mobile-list { display: none; flex-direction: column; gap: 12px; }
.kb-card { padding: 16px; cursor: pointer; }
.kb-card-head { display: flex; align-items: center; gap: 11px; }
.kb-arrow { margin-left: auto; color: var(--af-text-3); }
.kb-desc { color: var(--af-text-2); font-size: 12px; line-height: 1.8; margin: 12px 0; }
.kb-card-foot { display: flex; align-items: center; gap: 14px; color: var(--af-text-3); font-size: 11px; flex-wrap: wrap; }
.kb-card-foot span { display: inline-flex; align-items: center; gap: 4px; }
.kb-card-time { margin-left: auto; }
.kb-card-ops { display: flex; gap: 16px; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--af-border-soft); }
.mobile-empty { text-align: center; color: var(--af-text-3); font-size: 12px; padding: 40px 0; }

/* 引擎横幅 */
.engine-banner { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 16px 20px; flex-wrap: wrap; }
.engine-left { display: flex; align-items: center; gap: 13px; min-width: 0; }
.engine-icon {
  width: 40px; height: 40px; flex-shrink: 0;
  border-radius: 11px;
  background: var(--af-info-soft);
  color: var(--af-info);
  display: flex; align-items: center; justify-content: center;
  font-size: 19px;
}
.engine-text b { display: block; color: var(--af-text); font-size: 13px; }
.engine-text i { display: block; color: var(--af-text-3); font-size: 11px; font-style: normal; margin-top: 3px; }
.engine-setting { color: var(--af-text-2); font-size: 12px; border: 1px solid var(--af-border); border-radius: 8px; padding: 7px 14px; cursor: pointer; flex-shrink: 0; }

/* ===== 右侧栏 ===== */
.panel { padding: 18px 20px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.panel-title { color: var(--af-text); font-size: 15px; font-weight: 700; }
.panel-more { color: var(--af-text-3); font-size: 12px; cursor: pointer; }

.gauge-wrap { position: relative; width: 200px; margin: 4px auto 10px; }
.gauge { width: 100%; display: block; }
.gauge-center {
  position: absolute; left: 0; right: 0; bottom: 0;
  text-align: center;
}
.gauge-center b { display: block; color: var(--af-text); font-size: 26px; font-weight: 800; }
.gauge-center span { color: var(--af-text-3); font-size: 10px; }
.gauge-legend { display: flex; justify-content: center; gap: 18px; margin: 8px 0 14px; }
.gl-item { display: flex; align-items: center; gap: 6px; color: var(--af-text-2); font-size: 11px; }
.gauge-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.gs-item {
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  padding: 10px 12px;
}
.gs-item b { display: block; color: var(--af-text); font-size: 17px; font-weight: 700; }
.gs-item span { color: var(--af-text-3); font-size: 10px; }

.feed-list { display: flex; flex-direction: column; gap: 12px; }
.feed-item { display: flex; align-items: center; gap: 11px; }
.feed-icon {
  width: 32px; height: 32px; flex-shrink: 0;
  border-radius: 9px;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px;
}
.feed-icon.green { background: var(--af-success-soft); color: var(--af-success); }
.feed-icon.blue { background: var(--af-info-soft); color: var(--af-info); }
.feed-icon.red { background: rgba(255, 92, 51, 0.14); color: var(--af-danger); }
.feed-empty { text-align: center; font-size: 12px; color: var(--af-text-3); padding: 26px 0 14px; }
.feed-info { min-width: 0; }
.feed-name { color: var(--af-text); font-size: 12px; font-weight: 600; }
.feed-meta { color: var(--af-text-3); font-size: 10px; margin-top: 2px; }

/* 智能助手卡片 */
.agent-panel { padding: 18px 20px; display: flex; gap: 14px; align-items: flex-start; }
.agent-icon {
  width: 38px; height: 38px; border-radius: 10px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; font-size: 19px;
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.18), rgba(139, 92, 246, 0.18));
  color: var(--af-info);
}
.agent-text { min-width: 0; }
.agent-text b { display: block; color: var(--af-text); font-size: 13px; font-weight: 600; }
.agent-text p { margin: 6px 0 0; color: var(--af-text-3); font-size: 11.5px; line-height: 1.7; }


/* ===== 响应式 ===== */
@media (max-width: 1100px) {
  .content-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .table-card { display: none; }
  .mobile-list { display: flex; }
  .kb-hero { flex-direction: column; }
  .hero-actions { width: 100%; }
  .hero-search { flex: 1; width: auto; }
  .create-btn { flex: 1; justify-content: center; }
}
</style>
