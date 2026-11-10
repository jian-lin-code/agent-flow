<template>
  <el-dialog
    v-model="visible"
    width="580px"
    align-center
    :show-close="false"
    class="perm-dialog"
    @open="handleOpen"
  >
    <template #header>
      <div class="perm-head">
        <div class="perm-head-left">
          <div class="perm-icon"><el-icon><Lock /></el-icon></div>
          <div>
            <div class="perm-title">{{ $t('kb.permTitle') }}</div>
            <div class="perm-sub">{{ kbName }}</div>
          </div>
        </div>
        <span class="perm-close" @click="visible = false"><el-icon><Close /></el-icon></span>
      </div>
    </template>

    <!-- 添加授权 -->
    <div class="perm-add">
      <el-select
        v-model="selectedUserUid"
        class="user-select"
        filterable
        remote
        clearable
        reserve-keyword
        :remote-method="searchCandidates"
        :loading="searching"
        :placeholder="$t('kb.permSearchPh')"
      >
        <el-option
          v-for="user in candidates"
          :key="user.uid"
          :label="`${user.nickname || user.username}（${user.username}）`"
          :value="user.uid"
        >
          <div class="opt-row">
            <span class="opt-name">{{ user.nickname || user.username }}</span>
            <span class="opt-meta">{{ user.username }}</span>
            <span class="opt-role">{{ roleLabel(user.role) }}</span>
          </div>
        </el-option>
      </el-select>
      <el-select v-model="selectedPermission" class="perm-select">
        <el-option :label="$t('kb.permRead')" value="read" />
        <el-option :label="$t('kb.permManage')" value="manage" />
      </el-select>
      <el-button type="primary" :loading="granting" :disabled="!selectedUserUid" @click="handleGrant">
        {{ $t('kb.permAdd') }}
      </el-button>
    </div>

    <div v-if="isShared" class="perm-tip">
      <el-icon><InfoFilled /></el-icon>
      <span>{{ $t('kb.permSharedTip') }}</span>
    </div>

    <!-- 授权列表 -->
    <div class="perm-list" v-loading="loading">
      <div class="perm-list-head">
        <span>{{ $t('kb.permUser') }}</span>
        <span>{{ $t('kb.permPermission') }}</span>
        <span>{{ $t('kb.permGrantedBy') }}</span>
        <span></span>
      </div>

      <div v-for="item in items" :key="item.user_uid" class="perm-row">
        <div class="perm-user">
          <div class="avatar">{{ (item.nickname || item.username).slice(0, 1) }}</div>
          <div class="perm-user-info">
            <div class="perm-user-name">
              {{ item.nickname || item.username }}
              <span class="role-chip" :class="item.role">{{ roleLabel(item.role) }}</span>
            </div>
            <div class="perm-user-account">{{ item.username }}</div>
          </div>
        </div>

        <div class="perm-cell">
          <el-dropdown v-if="!isShared" trigger="click" @command="(cmd: 'read' | 'manage') => handleChangePermission(item, cmd)">
            <span class="perm-tag" :class="item.permission">
              {{ item.permission === 'manage' ? $t('kb.permManage') : $t('kb.permRead') }}
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="read">{{ $t('kb.permRead') }}</el-dropdown-item>
                <el-dropdown-item command="manage">{{ $t('kb.permManage') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <span v-else class="perm-tag read">
            {{ item.permission === 'manage' ? $t('kb.permManage') : $t('kb.permRead') }}
          </span>
        </div>

        <div class="perm-cell">
          <div class="perm-granted-by">{{ item.granted_by || '-' }}</div>
          <div class="perm-time">{{ formatDate(item.created_at) }}</div>
        </div>

        <div class="perm-cell perm-ops">
          <span class="revoke" @click="handleRevoke(item)">{{ $t('kb.permRevoke') }}</span>
        </div>
      </div>

      <div v-if="!loading && items.length === 0" class="perm-empty">
        <el-icon><UserFilled /></el-icon>
        <p>{{ $t('kb.permEmpty') }}</p>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">{{ $t('common.close') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Lock, Close, InfoFilled, ArrowDown, UserFilled } from '@element-plus/icons-vue'
import {
  grantKbPermission,
  listKbPermissions,
  revokeKbPermission,
  searchKbPermissionCandidates,
  type KnowledgeBasePermission,
  type KnowledgePermissionItem,
  type KnowledgeUserCandidate
} from '@/api/knowledge'

const props = defineProps<{
  modelValue: boolean
  kbUid: string
  kbName: string
  visibility?: 'shared' | 'private' | null
}>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const { t } = useI18n()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value)
})

const isShared = computed(() => props.visibility === 'shared')
const items = ref<KnowledgePermissionItem[]>([])
const candidates = ref<KnowledgeUserCandidate[]>([])
const selectedUserUid = ref('')
const selectedPermission = ref<KnowledgeBasePermission>('read')
const loading = ref(false)
const searching = ref(false)
const granting = ref(false)

const formatDate = (value: string) => (value ? value.replace('T', ' ').slice(0, 16) : '-')
const roleLabel = (role: string) => (role === 'admin' ? t('kb.roleAdmin') : t('kb.roleEmployee'))

const loadList = async () => {
  if (!props.kbUid) return
  loading.value = true
  try {
    const { data } = await listKbPermissions(props.kbUid)
    items.value = data.items
  } catch {
    // 错误提示由请求拦截器统一处理
    items.value = []
  } finally {
    loading.value = false
  }
}

const searchCandidates = async (keyword: string) => {
  if (!props.kbUid) return
  searching.value = true
  try {
    const { data } = await searchKbPermissionCandidates(props.kbUid, keyword)
    candidates.value = data
  } catch {
    candidates.value = []
  } finally {
    searching.value = false
  }
}

const handleOpen = async () => {
  selectedUserUid.value = ''
  selectedPermission.value = 'read'
  items.value = []
  await Promise.all([loadList(), searchCandidates('')])
}

const handleGrant = async () => {
  if (!selectedUserUid.value) {
    ElMessage.warning(t('kb.permSelectUser'))
    return
  }
  granting.value = true
  try {
    await grantKbPermission(props.kbUid, {
      user_uid: selectedUserUid.value,
      permission: selectedPermission.value
    })
    ElMessage.success(t('kb.permGranted'))
    selectedUserUid.value = ''
    await loadList()
  } finally {
    granting.value = false
  }
}

const handleChangePermission = async (item: KnowledgePermissionItem, permission: KnowledgeBasePermission) => {
  if (item.permission === permission) return
  await grantKbPermission(props.kbUid, { user_uid: item.user_uid, permission })
  ElMessage.success(t('kb.permUpdated'))
  await loadList()
}

const handleRevoke = async (item: KnowledgePermissionItem) => {
  const name = item.nickname || item.username
  const confirmed = await ElMessageBox.confirm(
    t('kb.permRevokeConfirm', { name }),
    t('kb.permRevokeTitle'),
    { type: 'warning', confirmButtonText: t('kb.permRevoke'), cancelButtonText: t('common.cancel') }
  ).then(() => true).catch(() => false)
  if (!confirmed) return
  await revokeKbPermission(props.kbUid, item.user_uid)
  ElMessage.success(t('kb.permRevoked'))
  await loadList()
}
</script>

<style scoped>
.perm-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.perm-head-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.perm-icon {
  width: 40px; height: 40px; flex-shrink: 0;
  border-radius: 11px;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  display: flex; align-items: center; justify-content: center;
  font-size: 19px;
}
.perm-title { color: var(--af-text); font-size: 16px; font-weight: 700; }
.perm-sub {
  color: var(--af-text-3); font-size: 12px; margin-top: 3px;
  max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.perm-close { color: var(--af-text-3); cursor: pointer; font-size: 16px; line-height: 1; }
.perm-close:hover { color: var(--af-text); }

.perm-add { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.user-select { flex: 1; min-width: 0; }
.perm-select { width: 108px; flex-shrink: 0; }

.opt-row { display: flex; align-items: center; gap: 8px; }
.opt-name { color: var(--af-text); font-size: 13px; }
.opt-meta { color: var(--af-text-3); font-size: 11px; }
.opt-role {
  margin-left: auto; font-size: 10px; color: var(--af-text-3);
  border: 1px solid var(--af-border); border-radius: 5px; padding: 0 6px;
}

.perm-tip {
  display: flex; align-items: center; gap: 8px;
  color: var(--af-warning); background: var(--af-warning-soft);
  border: 1px solid rgba(245, 166, 35, 0.22);
  border-radius: var(--af-radius-sm);
  font-size: 12px; line-height: 1.6;
  padding: 9px 12px; margin-bottom: 14px;
}

.perm-list {
  border: 1px solid var(--af-border-soft);
  border-radius: var(--af-radius-sm);
  overflow: hidden;
  min-height: 120px;
  max-height: 336px;
  overflow-y: auto;
}
.perm-list-head {
  display: grid;
  grid-template-columns: 1fr 96px 120px 52px;
  gap: 8px;
  background: var(--af-card-soft);
  color: var(--af-text-3);
  font-size: 11px;
  padding: 9px 14px;
  border-bottom: 1px solid var(--af-border-soft);
  position: sticky; top: 0; z-index: 1;
}
.perm-row {
  display: grid;
  grid-template-columns: 1fr 96px 120px 52px;
  gap: 8px;
  align-items: center;
  padding: 11px 14px;
  border-bottom: 1px solid var(--af-border-soft);
}
.perm-row:last-child { border-bottom: none; }
.perm-row:hover { background: var(--af-hover); }
.perm-user { display: flex; align-items: center; gap: 10px; min-width: 0; }
.avatar {
  width: 32px; height: 32px; flex-shrink: 0;
  border-radius: 50%;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  font-size: 13px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.perm-user-info { min-width: 0; }
.perm-user-name { display: flex; align-items: center; gap: 6px; color: var(--af-text); font-size: 13px; font-weight: 600; }
.perm-user-account { color: var(--af-text-3); font-size: 11px; margin-top: 2px; }
.role-chip { font-size: 10px; font-weight: 400; border-radius: 5px; padding: 1px 6px; border: 1px solid var(--af-border); color: var(--af-text-3); }
.role-chip.admin { color: var(--af-info); border-color: rgba(77, 141, 255, 0.3); background: var(--af-info-soft); }
.perm-cell { min-width: 0; }
.perm-tag {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; line-height: 1.6; padding: 2px 8px;
  border-radius: 6px; cursor: pointer; white-space: nowrap;
  border: 1px solid transparent;
}
.perm-tag.read { color: var(--af-warning); background: var(--af-warning-soft); border-color: rgba(245, 166, 35, 0.25); }
.perm-tag.manage { color: var(--af-success); background: var(--af-success-soft); border-color: rgba(46, 204, 113, 0.25); }
.perm-granted-by { color: var(--af-text-2); font-size: 12px; }
.perm-time { color: var(--af-text-3); font-size: 11px; margin-top: 2px; }
.perm-ops { text-align: right; }
.revoke { color: var(--af-danger); font-size: 12px; cursor: pointer; }
.revoke:hover { text-decoration: underline; }
.perm-empty { text-align: center; color: var(--af-text-3); padding: 34px 0; }
.perm-empty .el-icon { font-size: 26px; margin-bottom: 8px; }
.perm-empty p { font-size: 12px; }
</style>
