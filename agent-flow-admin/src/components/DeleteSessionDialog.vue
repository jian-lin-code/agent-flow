<template>
  <el-dialog
    :model-value="modelValue"
    width="400px"
    align-center
    :show-close="false"
    class="ds-dialog"
    :close-on-click-modal="true"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <!-- 顶部危险氛围亮线 -->
    <div class="ds-glow"></div>

    <div class="ds-body">
      <!-- Header -->
      <div class="ds-head">
        <div class="ds-badge">
          <el-icon :size="19"><Delete /></el-icon>
        </div>
        <div class="ds-head-text">
          <div class="ds-title-row">
            <h3 class="ds-title">{{ $t('chat.dsTitle') }}</h3>
            <span class="ds-chip">{{ $t('chat.dsChip') }}</span>
          </div>
          <p class="ds-sub">{{ $t('chat.dsDesc') }}</p>
        </div>
        <button class="ds-close" type="button" @click="close">
          <el-icon :size="14"><Close /></el-icon>
        </button>
      </div>

      <!-- 待删除会话卡片（真实数据：名称 + 最近时间） -->
      <div class="ds-card">
        <div class="ds-avatar">
          {{ initial }}
        </div>
        <div class="ds-card-text">
          <span class="ds-name" :title="session?.name">{{ session?.name || '-' }}</span>
          <span class="ds-time" v-if="session?.time">{{ $t('chat.dsLastActive') }} · {{ session.time }}</span>
        </div>
      </div>

      <!-- 影响说明 -->
      <ul class="ds-hints">
        <li>
          <span class="ds-dot danger"></span>
          <span>{{ $t('chat.dsHintMsgs') }}</span>
        </li>
        <li>
          <span class="ds-dot"></span>
          <span>{{ $t('chat.dsHintSwitch') }}</span>
        </li>
      </ul>

      <!-- Footer -->
      <div class="ds-footer">
        <button class="ds-btn" type="button" @click="close">{{ $t('common.cancel') }}</button>
        <button class="ds-confirm" type="button" @click="confirm">
          <el-icon :size="14"><Delete /></el-icon>
          <span>{{ $t('chat.dsBtn') }}</span>
        </button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Close, Delete } from '@element-plus/icons-vue'

/** 只依赖会话列表已有的字段 */
export interface DeleteSessionTarget {
  uid: string
  name: string
  time: string
}

const props = defineProps<{
  modelValue: boolean
  session: DeleteSessionTarget | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  /** 用户确认删除 */
  confirm: []
}>()

const initial = computed(() => (props.session?.name || '?').slice(0, 1).toUpperCase())

const close = () => emit('update:modelValue', false)
const confirm = () => {
  emit('update:modelValue', false)
  emit('confirm')
}
</script>

<style>
/* ===== 弹窗外壳（全局，供 teleport 使用） ===== */
.ds-dialog {
  background: #16171b;
  border: 1px solid #2a2b33;
  border-radius: 16px;
  overflow: hidden;
  box-shadow:
    0 24px 48px -12px rgba(0, 0, 0, 0.85),
    0 0 0 1px rgba(255, 255, 255, 0.06);
}
.ds-dialog .el-dialog__header { display: none; }
.ds-dialog .el-dialog__body { padding: 0; }
</style>

<style scoped>
.ds-glow {
  height: 2px;
  background: linear-gradient(90deg, transparent, rgba(255, 92, 51, 0.85), transparent);
}

.ds-body {
  padding: 18px 20px 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* ===== Header ===== */
.ds-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.ds-badge {
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

.ds-head-text { flex: 1; min-width: 0; }

.ds-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 1px 0 3px;
}

.ds-title {
  margin: 0;
  font-size: 15.5px;
  font-weight: 600;
  color: var(--af-text);
  letter-spacing: 0.2px;
}

.ds-chip {
  flex-shrink: 0;
  font-size: 10px;
  line-height: 16px;
  padding: 0 7px;
  border-radius: 999px;
  color: #ff9b74;
  background: rgba(255, 92, 51, 0.13);
  border: 1px solid rgba(255, 92, 51, 0.2);
}

.ds-sub {
  margin: 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--af-text-3);
}

.ds-close {
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
.ds-close:hover { background: var(--af-hover); color: var(--af-text); }

/* ===== 会话卡片 ===== */
.ds-card {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid #26272e;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.014));
}

.ds-avatar {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: var(--af-text-2);
  background: var(--af-hover);
  border: 1px solid #2f3038;
}

.ds-card-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ds-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--af-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ds-time {
  font-size: 11.5px;
  color: var(--af-text-3);
}

/* ===== 影响说明 ===== */
.ds-hints {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ds-hints li {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--af-text-2);
}

.ds-dot {
  width: 4px;
  height: 4px;
  margin-top: 6px;
  flex-shrink: 0;
  border-radius: 50%;
  background: var(--af-text-3);
}
.ds-dot.danger { background: #ff8a5c; }

/* ===== Footer ===== */
.ds-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 2px;
}

.ds-btn,
.ds-confirm {
  height: 34px;
  padding: 0 15px;
  border: none;
  border-radius: 9px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, filter 0.15s, transform 0.1s;
}

.ds-btn {
  background: var(--af-hover);
  color: var(--af-text);
}
.ds-btn:hover { background: #2f3038; }

.ds-confirm {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 17px;
  font-weight: 600;
  color: #fff;
  background: var(--af-primary-gradient);
  box-shadow: 0 8px 20px -9px rgba(255, 92, 51, 0.85);
}
.ds-confirm:hover { filter: brightness(1.08); }
.ds-confirm:active { transform: scale(0.97); }
</style>
