<template>
  <div class="claim-view-switch">
    <!-- 滑块：路由切换时组件虽会重挂载，但起始位置取上一次视图的位置，
         挂载后开启过渡滑到当前项，视觉上就是「背景从一侧移动到另一侧」 -->
    <span
      v-if="thumbIndex >= 0"
      class="switch-thumb"
      :class="{ animated }"
      :style="{ transform: `translateX(${thumbIndex * 100}%)` }"
    ></span>
    <button
      v-for="item in items"
      :key="item.path"
      class="switch-item"
      :class="{ active: route.path === item.path }"
      @click="router.push(item.path)"
    >
      {{ $t(item.labelKey) }}
      <span v-if="item.count !== null && item.count !== undefined" class="switch-count">{{ item.count }}</span>
    </button>
  </div>
</template>

<script lang="ts">
/** 模块级状态：组件在路由切换时会重挂载，<script setup> 内的变量每次实例化都会重置，
 *  必须放在普通 <script> 块里才能跨页面记住滑块上一次的位置。 */
let lastThumbIndex: number | null = null
</script>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

/** 报销双视图切换：待我审批（左，默认）/ 我的申请（右）。
 *  分段控件：主色滑块在两格间平移，选中项文字翻白；两侧可带数量徽标。 */
const props = defineProps<{
  /** 左侧「待我审批」的数量徽标 */
  leftCount?: number | null
  /** 右侧「我的申请」的数量徽标 */
  rightCount?: number | null
}>()

const route = useRoute()
const router = useRouter()

const items = computed(() => [
  { path: '/pending-approvals', labelKey: 'nav.pendingApprovals', count: props.leftCount ?? null },
  { path: '/my-claims', labelKey: 'nav.myClaims', count: props.rightCount ?? null }
])

const activeIndex = computed(() => items.value.findIndex((item) => item.path === route.path))
const thumbIndex = ref(lastThumbIndex ?? activeIndex.value)
const animated = ref(false)

const moveTo = (index: number) => {
  animated.value = true
  thumbIndex.value = index
  lastThumbIndex = index
}

onMounted(() => {
  // 双 rAF：确保浏览器先按「上一次的位置」完成首次绘制，再开启过渡滑到当前项
  requestAnimationFrame(() => {
    requestAnimationFrame(() => moveTo(activeIndex.value))
  })
})

watch(activeIndex, (index) => moveTo(index))
</script>

<style scoped>
.claim-view-switch {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 1fr;
  align-items: stretch;
  padding: 3px;
  background: var(--af-card-soft);
  border: 1px solid var(--af-border-soft);
  border-radius: 10px;
  flex-shrink: 0;
  min-width: 224px;
}

.switch-thumb {
  position: absolute;
  top: 3px;
  bottom: 3px;
  left: 3px;
  width: calc(50% - 3px);
  background: var(--af-primary-gradient);
  border-radius: 7px;
  box-shadow: 0 2px 10px rgba(245, 73, 31, 0.35);
  will-change: transform;
}

.switch-thumb.animated {
  transition: transform 0.32s cubic-bezier(0.4, 0, 0.2, 1);
}

.switch-item {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: var(--af-text-2);
  font-size: 13px;
  font-weight: 500;
  padding: 6px 14px;
  cursor: pointer;
  transition: color 0.2s;
  white-space: nowrap;
}

.switch-item:hover { color: var(--af-text); }

/* 选中项文字翻白，背景由滑块承担 */
.switch-item.active {
  color: #fff;
  font-weight: 600;
}

/* 数量徽标：选中项白色半透明底，未选中描边灰 */
.switch-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  margin-left: 6px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  line-height: 1;
  color: var(--af-text-3);
  border: 1px solid var(--af-border-soft);
  transition: all 0.2s;
}

.switch-item.active .switch-count {
  color: #fff;
  background: rgba(255, 255, 255, 0.22);
  border-color: rgba(255, 255, 255, 0.35);
}
</style>
