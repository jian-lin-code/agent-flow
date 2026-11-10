<template>
  <div ref="root" class="swipe-table">
    <div class="swipe-area">
      <slot />
      <!-- 右缘渐隐：提示内容被裁剪，可向右滑动 -->
      <div v-if="ready && overflow" class="swipe-fade" aria-hidden="true"></div>
    </div>
    <!-- 自定义滑块：直观告诉用户“可以拖过去看”，且可直接拖拽滚动 -->
    <div
      v-if="ready && overflow"
      class="swipe-bar"
      @pointerdown.prevent="onScrub"
    >
      <div class="swipe-track" aria-hidden="true"></div>
      <div class="swipe-thumb" :style="thumbStyle"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, type CSSProperties } from 'vue'

/**
 * 表格横向滑动提示容器：
 * - 内部 el-table 横向溢出时，底部显示一个常驻“滑块”滚动条（可拖拽同步滚动）
 * - 表格右缘叠加渐隐遮罩，暗示右侧还有内容
 * - 无溢出时两者都不渲染，桌面端宽屏下零干扰
 */

const root = ref<HTMLElement>()
const ready = ref(false)
const overflow = ref(false)
/** 滑块宽度占轨道比例 = 可视宽 / 滚动总宽 */
const thumbRatio = ref(1)
/** 滑块左偏移占轨道比例 */
const thumbPos = ref(0)

let wrap: HTMLElement | null = null
let resizeObserver: ResizeObserver | null = null

const thumbStyle = computed<CSSProperties>(() => ({
  width: `${thumbRatio.value * 100}%`,
  left: `${thumbPos.value * 100}%`
}))

const sync = () => {
  if (!wrap) return
  const scrollWidth = wrap.scrollWidth
  const clientWidth = wrap.clientWidth
  overflow.value = scrollWidth > clientWidth + 1
  if (!overflow.value) return
  thumbRatio.value = Math.min(1, clientWidth / scrollWidth)
  const maxScroll = scrollWidth - clientWidth
  thumbPos.value = maxScroll > 0
    ? (wrap.scrollLeft / maxScroll) * (1 - thumbRatio.value)
    : 0
}

const attach = () => {
  const el = root.value
  if (!el) return
  wrap = el.querySelector('.el-scrollbar__wrap')
  if (!wrap) return
  ready.value = true
  wrap.addEventListener('scroll', sync, { passive: true })
  resizeObserver = new ResizeObserver(sync)
  resizeObserver.observe(wrap)
  sync()
}

const detach = () => {
  if (wrap) wrap.removeEventListener('scroll', sync)
  resizeObserver?.disconnect()
  resizeObserver = null
  wrap = null
}

/** 拖拽/点按滑块直接滚动表格 */
const onScrub = (event: PointerEvent) => {
  if (!root.value || !wrap) return
  const bar = root.value.querySelector('.swipe-bar') as HTMLElement | null
  if (!bar) return
  const rect = bar.getBoundingClientRect()

  const scrollTo = (clientX: number) => {
    if (!wrap) return
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
    wrap.scrollLeft = ratio * (wrap.scrollWidth - wrap.clientWidth)
  }
  scrollTo(event.clientX)

  const onMove = (ev: PointerEvent) => scrollTo(ev.clientX)
  const onUp = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    window.removeEventListener('pointercancel', onUp)
  }
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
}

onMounted(async () => {
  await nextTick()
  attach()
})

onBeforeUnmount(detach)
</script>

<style scoped>
.swipe-area {
  position: relative;
  min-width: 0;
}

/* 右缘渐隐遮罩（只在有横向溢出时出现） */
.swipe-fade {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 14px;
  width: 30px;
  pointer-events: none;
  background: linear-gradient(to right, rgba(10, 10, 10, 0), rgba(10, 10, 10, 0.72));
  border-top-right-radius: 8px;
  border-bottom-right-radius: 8px;
}

/* 滑块滚动条：常驻可见，可拖拽 */
.swipe-bar {
  position: relative;
  height: 20px;
  margin-top: 4px;
  cursor: pointer;
  /* 阻止 iOS 触发页面滚动/长按菜单，保证拖拽顺滑 */
  touch-action: none;
  -webkit-user-select: none;
  user-select: none;
}

.swipe-track {
  position: absolute;
  left: 2px;
  right: 2px;
  top: 50%;
  height: 4px;
  transform: translateY(-50%);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.swipe-thumb {
  position: absolute;
  top: 50%;
  height: 7px;
  transform: translateY(-50%);
  border-radius: 999px;
  background: var(--af-primary, #ff5c33);
  opacity: 0.85;
  box-shadow: 0 0 8px rgba(255, 92, 51, 0.35);
}
</style>
