import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import { createPinia } from 'pinia'
import './style.css'
import './style/document-preview.css'
import App from './App.vue'
import router, { prefetchLazyPages } from './router'
import i18n from './locales'

const app = createApp(App)

// 全局注册所有 element 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(ElementPlus)
app.use(createPinia())
app.use(router)
app.use(i18n)

app.mount('#app')

// 首屏渲染完空闲时预取各页面组件，消除首次切换页面时的加载/编译等待
const idleWarmup = () => prefetchLazyPages()
const requestIdle = (window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number })
  .requestIdleCallback
if (typeof requestIdle === 'function') {
  requestIdle(idleWarmup, { timeout: 3000 })
} else {
  window.setTimeout(idleWarmup, 1500)
}
