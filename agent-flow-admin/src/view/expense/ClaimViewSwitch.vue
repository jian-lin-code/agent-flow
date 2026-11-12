<template>
  <div class="claim-view-switch">
    <button
      v-for="item in items"
      :key="item.path"
      class="switch-item"
      :class="{ active: route.path === item.path }"
      @click="router.push(item.path)"
    >
      {{ $t(item.labelKey) }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from 'vue-router'

/** 报销双视图切换：待我审批（admin）/ 我的申请（employee + admin），当前页高亮、点击跳转 */
const route = useRoute()
const router = useRouter()

const items = [
  { path: '/pending-approvals', labelKey: 'nav.pendingApprovals' },
  { path: '/my-claims', labelKey: 'nav.myClaims' }
]
</script>

<style scoped>
.claim-view-switch {
  display: inline-flex;
  align-items: center;
  padding: 3px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: 10px;
  gap: 2px;
  flex-shrink: 0;
}

.switch-item {
  border: none;
  background: transparent;
  color: var(--af-text-2);
  font-size: 13px;
  font-weight: 500;
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.switch-item:hover { color: var(--af-text); background: var(--af-hover); }

/* 选中态与侧边菜单激活样式一致：主色渐变底 + 白字 */
.switch-item.active {
  background: var(--af-primary-gradient);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 2px 10px rgba(245, 73, 31, 0.35);
}
</style>
