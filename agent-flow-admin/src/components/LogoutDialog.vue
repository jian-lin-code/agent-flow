<template>
  <el-dialog
    :model-value="modelValue"
    width="400px"
    align-center
    :show-close="false"
    class="lg-dialog"
    :close-on-click-modal="true"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <!-- 顶部氛围亮线 -->
    <div class="lg-glow"></div>

    <div class="lg-body">
      <!-- Header -->
      <div class="lg-head">
        <div class="lg-badge">
          <el-icon :size="19"><SwitchButton /></el-icon>
        </div>
        <div class="lg-head-text">
          <h3 class="lg-title">{{ $t('layout.logoutTitle') }}</h3>
          <p class="lg-sub">{{ $t('layout.logoutDesc') }}</p>
        </div>
        <button class="lg-close" type="button" @click="close">
          <el-icon :size="14"><Close /></el-icon>
        </button>
      </div>

      <!-- 当前登录账号（真实数据） -->
      <div class="lg-user">
        <div class="lg-avatar">
          {{ initial }}
          <span class="lg-status"></span>
        </div>
        <div class="lg-user-text">
          <div class="lg-user-row">
            <span class="lg-name">{{ displayName }}</span>
            <span class="lg-role">{{ roleLabel }}</span>
          </div>
          <span class="lg-account">@{{ userStore.userInfo?.username || '-' }}</span>
        </div>
      </div>

      <!-- 影响说明 -->
      <ul class="lg-hints">
        <li>
          <span class="lg-dot"></span>
          <span>{{ $t('layout.logoutHintToken') }}</span>
        </li>
        <li>
          <span class="lg-dot"></span>
          <span>{{ $t('layout.logoutHintSession') }}</span>
        </li>
      </ul>

      <!-- Footer -->
      <div class="lg-footer">
        <button class="lg-btn" type="button" @click="close">{{ $t('common.cancel') }}</button>
        <button class="lg-confirm" type="button" @click="confirm">
          <el-icon :size="14"><SwitchButton /></el-icon>
          <span>{{ $t('layout.logoutConfirmBtn') }}</span>
        </button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Close, SwitchButton } from '@element-plus/icons-vue'
import { useUserStore } from '@/stores/user'

defineProps<{ modelValue: boolean }>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  /** 用户确认退出登录 */
  confirm: []
}>()

const { t } = useI18n()
const userStore = useUserStore()

const displayName = computed(
  () => userStore.userInfo?.nickname || userStore.userInfo?.username || '-'
)
const initial = computed(() => displayName.value.slice(0, 1).toUpperCase())
const roleLabel = computed(() =>
  userStore.userInfo?.role === 'admin' ? t('layout.roleAdmin') : t('layout.roleUser')
)

const close = () => emit('update:modelValue', false)
const confirm = () => {
  emit('update:modelValue', false)
  emit('confirm')
}
</script>

<style>
/* ===== 弹窗外壳（全局，供 teleport 使用） ===== */
.lg-dialog {
  background: #16171b;
  border: 1px solid #2a2b33;
  border-radius: 16px;
  overflow: hidden;
  box-shadow:
    0 24px 48px -12px rgba(0, 0, 0, 0.85),
    0 0 0 1px rgba(255, 255, 255, 0.06);
}
.lg-dialog .el-dialog__header { display: none; }
.lg-dialog .el-dialog__body { padding: 0; }
</style>

<style scoped>
.lg-glow {
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(255, 92, 51, 0.85), transparent);
}

.lg-body {
  padding: 18px 20px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* ===== Header ===== */
.lg-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.lg-badge {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ff8a5c;
  background: linear-gradient(155deg, rgba(255, 122, 69, 0.22), rgba(245, 73, 31, 0.07));
  border: 1px solid rgba(255, 92, 51, 0.26);
  box-shadow: 0 10px 22px -12px rgba(255, 92, 51, 0.8);
}

.lg-head-text { flex: 1; min-width: 0; }

.lg-title {
  margin: 1px 0 3px;
  font-size: 15.5px;
  font-weight: 600;
  color: var(--af-text);
  letter-spacing: 0.2px;
}

.lg-sub {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--af-text-3);
}

.lg-close {
  width: 26px;
  height: 26px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: transparent;
  color: var(--af-text-3);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.lg-close:hover { background: var(--af-hover); color: var(--af-text); }

/* ===== 账号卡片 ===== */
.lg-user {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid #26272e;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.014));
}

.lg-avatar {
  position: relative;
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  background: var(--af-primary-gradient);
  box-shadow: 0 6px 16px -8px rgba(255, 92, 51, 0.9);
}

.lg-status {
  position: absolute;
  right: -1px;
  bottom: -1px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--af-success);
  border: 2px solid #16171b;
}

.lg-user-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.lg-user-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.lg-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--af-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lg-role {
  flex-shrink: 0;
  font-size: 10px;
  line-height: 16px;
  padding: 0 7px;
  border-radius: 999px;
  color: #ff9b74;
  background: rgba(255, 92, 51, 0.13);
  border: 1px solid rgba(255, 92, 51, 0.2);
}

.lg-account {
  font-size: 11.5px;
  color: var(--af-text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ===== 影响说明 ===== */
.lg-hints {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.lg-hints li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--af-text-2);
}

.lg-dot {
  width: 4px;
  height: 4px;
  margin-top: 6px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--af-text-3);
}

/* ===== Footer ===== */
.lg-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 2px;
}

.lg-btn,
.lg-confirm {
  height: 34px;
  padding: 0 15px;
  border: none;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, filter 0.15s, transform 0.1s;
}

.lg-btn {
  background: var(--af-hover);
  color: var(--af-text);
}
.lg-btn:hover { background: #2f3038; }

.lg-confirm {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 17px;
  font-weight: 600;
  color: #fff;
  background: var(--af-primary-gradient);
  box-shadow: 0 8px 20px -9px rgba(255, 92, 51, 0.85);
}
.lg-confirm:hover { filter: brightness(1.08); }
.lg-confirm:active { transform: scale(0.97); }
</style>
