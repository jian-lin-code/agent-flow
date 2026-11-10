<template>
  <el-dialog
    :model-value="modelValue"
    width="720px"
    align-center
    :show-header="false"
    :show-close="false"
    class="ck-dialog"
    :close-on-click-modal="false"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
    @closed="reset"
  >
    <!-- 顶部三色饰条 -->
    <div class="ck-topbar"></div>

    <!-- 弹窗 Header -->
    <div class="ck-header">
      <div class="ck-header-main">
        <div class="ck-icon">
          <el-icon :size="26"><Collection /></el-icon>
          <span class="ck-icon-badge"><el-icon :size="10"><MagicStick /></el-icon></span>
        </div>
        <div class="ck-header-text">
          <div class="ck-title-row">
            <h3>{{ $t('kb.createKb') }}</h3>
            <span class="ck-chip chip-primary"><i class="pulse"></i>{{ $t('kb.ckBadgeRag') }}</span>
            <span class="ck-chip">{{ $t('kb.ckBadgeEngine') }}</span>
          </div>
          <p class="ck-sub">{{ $t('kb.ckSubtitle') }}</p>
        </div>
      </div>
      <button class="ck-close" @click="close">
        <el-icon :size="16"><Close /></el-icon>
      </button>
    </div>

    <!-- 弹窗 Body -->
    <div class="ck-body">
      <!-- SECTION 1 基本信息 -->
      <section class="ck-card">
        <div class="ck-card-head">
          <span class="ck-sec-title t-primary">
            <el-icon :size="16"><InfoFilled /></el-icon>
            {{ $t('kb.ckSectionBasic') }}
          </span>
          <span class="ck-hint">{{ $t('kb.ckRequiredHint') }}</span>
        </div>

        <!-- 名称 + 字数计数 -->
        <div class="ck-field">
          <div class="ck-field-head">
            <label>{{ $t('kb.labelName') }} <i class="req">*</i></label>
            <span class="ck-counter">{{ form.name.length }} / 30</span>
          </div>
          <div class="ck-input">
            <input v-model="form.name" type="text" maxlength="30" :placeholder="$t('kb.ckPhName')" />
            <span v-if="form.name.trim()" class="ck-input-ok">
              <el-icon :size="16"><CircleCheck /></el-icon>
            </span>
          </div>
        </div>

        <!-- 预置领域模板（选中后自动填充描述，后端不单独存储分类字段） -->
        <div class="ck-field">
          <label class="ck-label-sm">{{ $t('kb.ckTemplatesLabel') }}</label>
          <div class="ck-tpl-grid">
            <button
              v-for="(tpl, i) in TEMPLATES"
              :key="tpl.key"
              type="button"
              class="ck-tpl"
              :class="{ active: tplIndex === i }"
              @click="selectTemplate(i)"
            >
              <span class="tpl-emoji">{{ tpl.icon }}</span>
              <span class="tpl-name">{{ $t(tpl.labelKey) }}</span>
              <i v-if="tplIndex === i" class="tpl-dot"></i>
            </button>
          </div>
        </div>

        <!-- 描述 + 字数计数 -->
        <div class="ck-field">
          <div class="ck-field-head">
            <label>{{ $t('kb.ckLabelDescPrompt') }}</label>
            <span class="ck-counter">{{ form.description.length }} / 200</span>
          </div>
          <textarea
            v-model="form.description"
            class="ck-textarea"
            rows="3"
            maxlength="200"
            :placeholder="$t('kb.ckDescPh')"
          ></textarea>
        </div>
      </section>

      <!-- SECTION 2 访问空间与成员授权 -->
      <section class="ck-card">
        <div class="ck-card-head">
          <span class="ck-sec-title t-success">
            <el-icon :size="16"><Lock /></el-icon>
            {{ $t('kb.ckSectionAccess') }}
          </span>
          <span class="ck-chip chip-success">
            <el-icon :size="12"><Lock /></el-icon>
            {{ $t('kb.ckRbacTag') }}
          </span>
        </div>

        <!-- 空间类型选择 -->
        <div class="ck-space-grid">
          <div class="ck-space" :class="{ active: visibility === 'private' }" @click="visibility = 'private'">
            <span class="ck-radio" :class="{ on: visibility === 'private' }"><i></i></span>
            <div class="ck-space-text">
              <div class="ck-space-title">
                {{ $t('kb.ckSpaceRestricted') }}
                <span class="ck-recommend">{{ $t('kb.ckRecommended') }}</span>
              </div>
              <p>{{ $t('kb.ckSpaceRestrictedDesc') }}</p>
            </div>
          </div>
          <div class="ck-space" :class="{ active: visibility === 'shared' }" @click="visibility = 'shared'">
            <span class="ck-radio" :class="{ on: visibility === 'shared' }"><i></i></span>
            <div class="ck-space-text">
              <div class="ck-space-title">{{ $t('kb.ckSpacePublic') }}</div>
              <p>{{ $t('kb.ckSpacePublicDesc') }}</p>
            </div>
          </div>
        </div>

        <!-- 已授权成员 -->
        <div class="ck-field">
          <div class="ck-field-head">
            <label>{{ $t('kb.ckMembersLabel') }}</label>
            <span v-if="isShared" class="ck-shared-hint">{{ $t('kb.ckSharedNoGrant') }}</span>
          </div>
          <div class="ck-tagbox">
            <div v-for="m in members" :key="m.uid" class="ck-tag">
              <span class="tag-avatar">{{ (m.nickname || m.username).slice(0, 1) }}</span>
              <span class="tag-name">{{ m.nickname || m.username }}</span>
              <el-dropdown
                trigger="click"
                @command="(p: 'read' | 'manage') => setMemberPermission(m.uid, p)"
              >
                <span class="tag-perm" :class="m.permission">
                  {{ m.permission === 'manage' ? $t('kb.permManage') : $t('kb.permRead') }}
                  <el-icon :size="10"><ArrowDown /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="read">{{ $t('kb.permRead') }}</el-dropdown-item>
                    <el-dropdown-item command="manage">{{ $t('kb.permManage') }}</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
              <button class="tag-x" type="button" @click="removeMember(m.uid)">
                <el-icon :size="12"><Close /></el-icon>
              </button>
            </div>

            <el-select
              v-if="!isShared"
              v-model="memberPick"
              class="ck-member-search"
              filterable
              remote
              clearable
              reserve-keyword
              :remote-method="searchMembers"
              :loading="searching"
              :placeholder="$t('kb.ckMemberSearchPh')"
              @change="addMember"
            >
              <el-option
                v-for="user in candidateOptions"
                :key="user.uid"
                :label="`${user.nickname || user.username}（${user.username}）`"
                :value="user.uid"
              >
                <div class="ck-opt">
                  <span class="opt-name">{{ user.nickname || user.username }}</span>
                  <span class="opt-meta">{{ user.username }}</span>
                  <span class="opt-role">{{ roleLabel(user.role) }}</span>
                </div>
              </el-option>
            </el-select>

            <span v-if="members.length === 0 && isShared" class="ck-tagbox-empty">
              {{ $t('kb.ckSharedNoGrant') }}
            </span>
          </div>
        </div>

        <!-- 治理开关（后端暂未支持，置灰占位） -->
        <div class="ck-toggle-grid">
          <div class="ck-toggle">
            <div class="ck-toggle-left">
              <el-icon :size="18" class="t-success"><CircleCheck /></el-icon>
              <div>
                <b>{{ $t('kb.ckAudit') }}</b>
                <span>{{ $t('kb.ckAuditDesc') }}</span>
              </div>
            </div>
            <div class="ck-toggle-right">
              <span class="ck-soon">{{ $t('kb.ckComingSoon') }}</span>
              <el-switch disabled />
            </div>
          </div>
          <div class="ck-toggle">
            <div class="ck-toggle-left">
              <el-icon :size="18" class="t-primary"><Postcard /></el-icon>
              <div>
                <b>{{ $t('kb.ckWatermark') }}</b>
                <span>{{ $t('kb.ckWatermarkDesc') }}</span>
              </div>
            </div>
            <div class="ck-toggle-right">
              <span class="ck-soon">{{ $t('kb.ckComingSoon') }}</span>
              <el-switch disabled />
            </div>
          </div>
        </div>
      </section>

      <!-- SECTION 3 RAG 管线（后端固定管线，仅作信息展示） -->
      <section class="ck-card">
        <div class="ck-card-head">
          <span class="ck-sec-title t-info">
            <el-icon :size="16"><Cpu /></el-icon>
            {{ $t('kb.ckSectionPipeline') }}
          </span>
          <span class="ck-hint">BGE-M3 · 1024-dim</span>
        </div>
        <div class="ck-pipe-grid">
          <div class="ck-pipe featured">
            <div class="pipe-name">
              <i class="ok"></i>
              <b>{{ $t('kb.ckPipeHybrid') }}</b>
            </div>
            <p>{{ $t('kb.ckPipeHybridDesc') }}</p>
          </div>
          <div class="ck-pipe">
            <div class="pipe-name"><b>{{ $t('kb.ckPipeParser') }}</b></div>
            <p>{{ $t('kb.ckPipeParserDesc') }}</p>
          </div>
          <div class="ck-pipe">
            <div class="pipe-name"><b>{{ $t('kb.ckPipeChunk') }}</b></div>
            <p>{{ $t('kb.ckPipeChunkDesc') }}</p>
          </div>
        </div>
      </section>
    </div>

    <!-- 弹窗 Footer -->
    <div class="ck-footer">
      <div class="ck-footer-left">
        <span class="dot-live"></span>
        <span class="ck-summary">
          {{ $t('kb.ckFooterSelected', { n: members.length }) }}
        </span>
        <i class="ck-divider"></i>
        <span class="ck-summary dim">
          {{ visibility === 'shared' ? $t('kb.ckSpacePublic') : $t('kb.ckSpaceRestricted') }}
        </span>
      </div>
      <div class="ck-footer-right">
        <button class="ck-btn" type="button" @click="close">{{ $t('common.cancel') }}</button>
        <button
          class="ck-submit"
          type="button"
          :class="{ loading: submitState !== 'idle', done: submitState === 'done' }"
          :disabled="submitState !== 'idle'"
          @click="submit"
        >
          <span class="shimmer"></span>
          <el-icon v-if="submitState === 'loading'" :size="16" class="spin"><Loading /></el-icon>
          <el-icon v-else-if="submitState === 'done'" :size="16"><Check /></el-icon>
          <el-icon v-else :size="16"><Plus /></el-icon>
          <span>
            {{ submitState === 'loading'
              ? $t('kb.ckSubmitting')
              : submitState === 'done'
                ? $t('kb.ckCreated')
                : $t('kb.ckSubmit') }}
          </span>
        </button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  ArrowDown, Check, CircleCheck, Close, Collection, Cpu, InfoFilled,
  Loading, Lock, MagicStick, Plus, Postcard
} from '@element-plus/icons-vue'
import {
  createKnowledgeBase,
  grantKbPermission,
  searchGrantableUsers,
  type KnowledgeUserCandidate
} from '@/api/knowledge'

const props = defineProps<{ modelValue: boolean }>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: []
}>()

const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value)
})
const close = () => emit('update:modelValue', false)

/** 预置领域模板：仅用于快速填充描述，后端不单独存储分类字段 */
const TEMPLATES = [
  { icon: '💼', key: 'finance', labelKey: 'kb.ckTplFinance', descKey: 'kb.ckTplFinanceDesc' },
  { icon: '📘', key: 'hr', labelKey: 'kb.ckTplHr', descKey: 'kb.ckTplHrDesc' },
  { icon: '🛠️', key: 'tech', labelKey: 'kb.ckTplTech', descKey: 'kb.ckTplTechDesc' },
  { icon: '⚖️', key: 'legal', labelKey: 'kb.ckTplLegal', descKey: 'kb.ckTplLegalDesc' }
] as const

const form = ref({ name: '', description: '' })
const visibility = ref<'private' | 'shared'>('private')
const tplIndex = ref<number | null>(null)

interface MemberPick {
  uid: string
  username: string
  nickname: string | null
  role: string
  permission: 'read' | 'manage'
}
const members = ref<MemberPick[]>([])
const candidates = ref<KnowledgeUserCandidate[]>([])
const memberPick = ref('')
const searching = ref(false)
const submitState = ref<'idle' | 'loading' | 'done'>('idle')

const isShared = computed(() => visibility.value === 'shared')
const roleLabel = (role: string) => (role === 'admin' ? t('kb.roleAdmin') : t('kb.roleEmployee'))
const candidateOptions = computed(() =>
  candidates.value.filter((user) => !members.value.some((m) => m.uid === user.uid))
)

const selectTemplate = (index: number) => {
  tplIndex.value = tplIndex.value === index ? null : index
  if (tplIndex.value === null) return
  const tpl = TEMPLATES[index]
  const desc = t(tpl.descKey)
  const currentIsTemplate = TEMPLATES.some((item) => form.value.description === t(item.descKey))
  // 描述为空或本身就是模板文案时才覆盖，避免冲掉用户手动输入
  if (!form.value.description.trim() || currentIsTemplate) {
    form.value.description = desc
  }
}

const searchMembers = async (keyword: string) => {
  searching.value = true
  try {
    const { data } = await searchGrantableUsers(keyword)
    candidates.value = data
  } catch {
    candidates.value = []
  } finally {
    searching.value = false
  }
}

const addMember = (uid: string) => {
  if (!uid) return
  const user = candidates.value.find((item) => item.uid === uid)
  if (user && !members.value.some((m) => m.uid === uid)) {
    members.value.push({ ...user, permission: 'read' })
  }
  memberPick.value = ''
}

const removeMember = (uid: string) => {
  members.value = members.value.filter((m) => m.uid !== uid)
}

const setMemberPermission = (uid: string, permission: 'read' | 'manage') => {
  const member = members.value.find((m) => m.uid === uid)
  if (member) member.permission = permission
}

const reset = () => {
  form.value = { name: '', description: '' }
  visibility.value = 'private'
  tplIndex.value = null
  members.value = []
  candidates.value = []
  memberPick.value = ''
  submitState.value = 'idle'
}

const submit = async () => {
  if (submitState.value !== 'idle') return
  if (!form.value.name.trim()) {
    ElMessage.warning(t('kb.ruleName'))
    return
  }
  submitState.value = 'loading'
  try {
    const { data: kb } = await createKnowledgeBase({
      name: form.value.name.trim(),
      description: form.value.description.trim(),
      visibility: visibility.value
    })

    // 受限空间：创建成功后逐条写入成员授权（公开空间全员可读，无需授权）
    if (!isShared.value && members.value.length) {
      const results = await Promise.allSettled(
        members.value.map((m) =>
          grantKbPermission(kb.uid, { user_uid: m.uid, permission: m.permission })
        )
      )
      const failed = results.filter((r) => r.status === 'rejected').length
      if (failed > 0) {
        ElMessage.warning(t('kb.ckGrantFailed', { n: failed }))
      }
    }

    submitState.value = 'done'
    emit('created')
    setTimeout(() => {
      visible.value = false
    }, 700)
  } catch {
    // 创建失败（如重名）由请求拦截器统一提示，这里复位等待用户重试
    submitState.value = 'idle'
  }
}
</script>

<style>
/* ===== 弹窗外壳（全局，供 teleport 使用） ===== */
.ck-dialog {
  background: #16171b;
  border: 1px solid #2a2b33;
  border-radius: 16px;
  overflow: hidden;
  box-shadow:
    0 24px 60px -12px rgba(0, 0, 0, 0.75),
    0 0 0 1px rgba(255, 255, 255, 0.07);
}
.ck-dialog .el-dialog__header { display: none; }
.ck-dialog .el-dialog__body { padding: 0; }
</style>

<style scoped>
.ck-topbar {
  height: 4px;
  background: linear-gradient(90deg, var(--af-primary), var(--af-success), var(--af-info));
}

/* ===== Header ===== */
.ck-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
  padding: 18px 20px 12px;
}
.ck-header-main { display: flex; align-items: flex-start; gap: 13px; min-width: 0; }
.ck-icon {
  position: relative;
  width: 48px; height: 48px; flex-shrink: 0;
  border-radius: 13px;
  background: linear-gradient(135deg, #2a2b33, #34353d);
  color: var(--af-primary);
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 0 20px -3px rgba(255, 92, 51, 0.25);
}
.ck-icon-badge {
  position: absolute; right: -5px; bottom: -5px;
  width: 16px; height: 16px;
  border-radius: 50%;
  background: var(--af-success);
  color: #062b18;
  display: flex; align-items: center; justify-content: center;
}
.ck-header-text { min-width: 0; }
.ck-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ck-title-row h3 { margin: 0; color: var(--af-text); font-size: 18px; font-weight: 700; }
.ck-chip {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 10px; line-height: 1.6; padding: 1px 8px;
  border-radius: 999px;
  background: var(--af-hover);
  color: var(--af-text-3);
  white-space: nowrap;
}
.ck-chip.chip-primary { color: var(--af-primary); background: var(--af-primary-soft); }
.ck-chip.chip-success { color: var(--af-success); background: var(--af-success-soft); }
.pulse {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--af-primary);
  animation: ck-pulse 1.6s ease-in-out infinite;
}
@keyframes ck-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}
.ck-sub { margin: 5px 0 0; color: var(--af-text-3); font-size: 12px; line-height: 1.6; }
.ck-close {
  width: 30px; height: 30px; flex-shrink: 0;
  border: none; border-radius: 9px;
  background: var(--af-hover);
  color: var(--af-text-3);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.ck-close:hover { color: var(--af-text); background: #2f3038; }

/* ===== Body ===== */
.ck-body {
  padding: 4px 20px 6px;
  max-height: 56vh;
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 14px;
}
.ck-card {
  background: #1c1d23;
  border: 1px solid #26272e;
  border-radius: 12px;
  padding: 14px 16px;
  display: flex; flex-direction: column; gap: 12px;
}
.ck-card-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.ck-sec-title {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600;
}
.ck-sec-title.t-primary { color: var(--af-primary); }
.ck-sec-title.t-success { color: var(--af-success); }
.ck-sec-title.t-info { color: var(--af-info); }
.ck-hint { color: var(--af-text-3); font-size: 10px; }

.ck-field { display: flex; flex-direction: column; gap: 6px; }
.ck-field-head { display: flex; align-items: center; justify-content: space-between; }
.ck-field-head label, .ck-label-sm { color: var(--af-text-2); font-size: 12px; font-weight: 500; }
.ck-field-head .req { color: var(--af-primary); font-style: normal; }
.ck-counter { color: var(--af-text-3); font-size: 10px; font-variant-numeric: tabular-nums; }

.ck-input { position: relative; display: flex; align-items: center; }
.ck-input input {
  width: 100%;
  background: #101114;
  border: 1px solid #2a2b33;
  border-radius: 9px;
  padding: 9px 34px 9px 12px;
  color: var(--af-text);
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s, background 0.2s;
}
.ck-input input::placeholder { color: rgba(168, 168, 168, 0.45); }
.ck-input input:focus { border-color: rgba(255, 92, 51, 0.55); background: #1a1b21; }
.ck-input-ok {
  position: absolute; right: 10px;
  color: var(--af-success);
  display: flex;
}
.ck-textarea {
  width: 100%;
  background: #101114;
  border: 1px solid #2a2b33;
  border-radius: 9px;
  padding: 10px 12px;
  color: var(--af-text);
  font-size: 12px;
  line-height: 1.7;
  resize: none;
  outline: none;
  transition: border-color 0.2s, background 0.2s;
}
.ck-textarea::placeholder { color: rgba(168, 168, 168, 0.45); }
.ck-textarea:focus { border-color: rgba(255, 92, 51, 0.55); background: #1a1b21; }

/* 预置模板徽章 */
.ck-tpl-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.ck-tpl {
  position: relative;
  display: flex; align-items: center; gap: 7px;
  padding: 8px 10px;
  border: 1px solid #2a2b33;
  border-radius: 9px;
  background: #101114;
  color: var(--af-text-2);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.ck-tpl:hover { background: #1e1f26; color: var(--af-text); }
.ck-tpl.active { background: #26272e; color: var(--af-text); border-color: rgba(255, 92, 51, 0.45); }
.tpl-emoji { font-size: 14px; line-height: 1; }
.tpl-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; }
.tpl-dot {
  position: absolute; top: 4px; right: 4px;
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--af-primary);
}

/* 空间选择 */
.ck-space-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ck-space {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 12px;
  border-radius: 11px;
  background: #101114;
  border: 1px solid #26272e;
  cursor: pointer;
  opacity: 0.72;
  transition: opacity 0.15s, background 0.15s, border-color 0.15s;
}
.ck-space:hover { opacity: 1; }
.ck-space.active {
  opacity: 1;
  background: #24252c;
  border-color: rgba(255, 92, 51, 0.4);
}
.ck-radio {
  margin-top: 2px;
  width: 15px; height: 15px; flex-shrink: 0;
  border-radius: 50%;
  background: #2a2b33;
  display: flex; align-items: center; justify-content: center;
}
.ck-radio.on { background: var(--af-primary); }
.ck-radio i {
  width: 6px; height: 6px; border-radius: 50%;
  background: transparent;
}
.ck-radio.on i { background: #3d0600; }
.ck-space-text { min-width: 0; }
.ck-space-title {
  display: flex; align-items: center; gap: 7px; flex-wrap: wrap;
  color: var(--af-text); font-size: 12px; font-weight: 600;
}
.ck-recommend {
  font-size: 10px; font-weight: 400;
  color: var(--af-primary);
  background: rgba(255, 92, 51, 0.16);
  border-radius: 5px;
  padding: 0 6px;
}
.ck-space-text p { margin: 4px 0 0; color: var(--af-text-3); font-size: 11px; line-height: 1.6; }

/* 成员标签 */
.ck-shared-hint { color: var(--af-warning); font-size: 10px; }
.ck-tagbox {
  display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
  min-height: 52px;
  background: #101114;
  border: 1px solid #26272e;
  border-radius: 9px;
  padding: 8px 10px;
}
.ck-tagbox.disabled { opacity: 0.65; }
.ck-tag {
  display: inline-flex; align-items: center; gap: 6px;
  background: #26272e;
  border-radius: 8px;
  padding: 4px 5px 4px 8px;
  color: var(--af-text);
  font-size: 12px;
}
.tag-avatar {
  width: 18px; height: 18px;
  border-radius: 50%;
  background: rgba(255, 92, 51, 0.2);
  color: var(--af-primary);
  font-size: 10px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.tag-name { font-weight: 500; }
.tag-perm {
  display: inline-flex; align-items: center; gap: 2px;
  font-size: 10px;
  border-radius: 5px;
  padding: 1px 6px;
  cursor: pointer;
}
.tag-perm.manage { color: var(--af-success); background: rgba(46, 204, 113, 0.14); }
.tag-perm.read { color: var(--af-info); background: rgba(77, 141, 255, 0.14); }
.tag-x {
  width: 18px; height: 18px;
  border: none; border-radius: 5px;
  background: transparent;
  color: var(--af-text-3);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.tag-x:hover { color: var(--af-danger); background: rgba(255, 77, 79, 0.12); }
.ck-tagbox-empty { color: var(--af-text-3); font-size: 11px; }

.ck-member-search { width: 210px; }
.ck-member-search :deep(.el-select__wrapper) {
  background: transparent;
  box-shadow: none;
  min-height: 28px;
  padding-left: 6px;
}
.ck-opt { display: flex; align-items: center; gap: 8px; }
.opt-name { color: var(--af-text); font-size: 12px; }
.opt-meta { color: var(--af-text-3); font-size: 10px; }
.opt-role {
  margin-left: auto;
  font-size: 10px;
  color: var(--af-text-3);
  border: 1px solid var(--af-border);
  border-radius: 5px;
  padding: 0 6px;
}

/* 治理开关（置灰占位） */
.ck-toggle-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.ck-toggle {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  background: #101114;
  border-radius: 9px;
  padding: 10px 12px;
  opacity: 0.72;
}
.ck-toggle-left { display: flex; align-items: center; gap: 9px; min-width: 0; }
.ck-toggle-left b { display: block; color: var(--af-text-2); font-size: 11px; font-weight: 600; }
.ck-toggle-left span { display: block; color: var(--af-text-3); font-size: 10px; margin-top: 2px; }
.t-success { color: var(--af-success); }
.t-primary { color: var(--af-primary); }
.ck-toggle-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.ck-soon {
  font-size: 9px;
  color: var(--af-text-3);
  border: 1px solid var(--af-border);
  border-radius: 5px;
  padding: 1px 5px;
}

/* RAG 管线信息 */
.ck-pipe-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.ck-pipe {
  position: relative;
  overflow: hidden;
  background: #101114;
  border-radius: 9px;
  padding: 10px 12px;
}
.ck-pipe.featured { background: #24252c; }
.ck-pipe.featured::before {
  content: '';
  position: absolute; top: 0; left: 0;
  width: 100%; height: 2px;
  background: var(--af-primary);
}
.pipe-name { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.pipe-name b { color: var(--af-text); font-size: 11px; font-weight: 600; }
.pipe-name .ok {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--af-success);
}
.ck-pipe p { margin: 0; color: var(--af-text-3); font-size: 10px; line-height: 1.6; }

/* ===== Footer ===== */
.ck-footer {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 13px 20px;
  border-top: 1px solid #26272e;
  flex-wrap: wrap;
}
.ck-footer-left { display: flex; align-items: center; gap: 9px; }
.dot-live {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--af-success);
  animation: ck-pulse 1.6s ease-in-out infinite;
}
.ck-summary { color: var(--af-text-3); font-size: 11px; }
.ck-summary b { color: var(--af-text); font-weight: 600; }
.ck-summary.dim { color: rgba(111, 111, 111, 0.8); }
.ck-divider { width: 1px; height: 12px; background: #2a2b33; }
.ck-footer-right { display: flex; align-items: center; gap: 10px; }
.ck-btn {
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
.ck-btn:hover { background: #2f3038; }

.ck-submit {
  position: relative;
  overflow: hidden;
  display: inline-flex; align-items: center; gap: 7px;
  border: none;
  border-radius: 9px;
  background: var(--af-primary-gradient);
  color: #3d0600;
  font-size: 12px;
  font-weight: 700;
  padding: 9px 18px;
  cursor: pointer;
  box-shadow: 0 0 20px -2px rgba(255, 92, 51, 0.45);
  transition: filter 0.15s, transform 0.1s;
}
.ck-submit:hover:not(:disabled) { filter: brightness(1.12); }
.ck-submit:active:not(:disabled) { transform: scale(0.96); }
.ck-submit:disabled { cursor: default; }
.ck-submit.done { background: var(--af-success); color: #062b18; box-shadow: 0 0 20px -2px rgba(46, 204, 113, 0.45); }
.shimmer {
  position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.22), transparent);
  transform: translateX(-100%);
}
.ck-submit:hover:not(:disabled) .shimmer { animation: ck-shimmer 1s ease; }
@keyframes ck-shimmer {
  to { transform: translateX(100%); }
}
.spin { animation: ck-rotate 0.9s linear infinite; }
@keyframes ck-rotate {
  to { transform: rotate(360deg); }
}

/* ===== 响应式 ===== */
@media (max-width: 640px) {
  .ck-tpl-grid { grid-template-columns: repeat(2, 1fr); }
  .ck-space-grid, .ck-toggle-grid { grid-template-columns: 1fr; }
  .ck-pipe-grid { grid-template-columns: 1fr; }
  .ck-footer { flex-direction: column; align-items: stretch; }
  .ck-footer-right { justify-content: flex-end; }
}
</style>
