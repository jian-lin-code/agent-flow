<template>
  <div class="layout-container">
    <!-- ===== 桌面端侧边栏 ===== -->
    <aside class="layout-aside">
      <div class="layout-logo">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="3" />
            <circle cx="5" cy="5" r="2" /><circle cx="19" cy="5" r="2" />
            <circle cx="5" cy="19" r="2" /><circle cx="19" cy="19" r="2" />
            <path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3" />
          </svg>
        </div>
        <div class="logo-text-group">
          <span class="logo-main-text">AgentFlow</span>
          <span class="logo-sub-text">{{ $t('layout.platform') }}</span>
        </div>
      </div>

      <nav class="layout-menu">
        <div
          v-for="item in visibleMenus"
          :key="item.path"
          class="menu-item"
          :class="{ active: isActive(item.path) }"
          @click="router.push(item.path)"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ $t(item.titleKey) }}</span>
        </div>
      </nav>

      <!-- 底部用户信息 -->
      <div class="aside-footer">
        <el-dropdown trigger="click" @command="handleCommand" class="user-dropdown-wrap">
          <div class="user-info-mini">
            <div class="user-avatar">{{ avatarText }}</div>
            <div class="user-text">
              <div class="user-name">{{ userStore.userInfo?.nickname || userStore.userInfo?.username }}</div>
              <div class="user-role">{{ roleLabel }}</div>
            </div>
            <el-icon class="switch-icon"><Sort /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item divided command="logout">{{ $t('layout.logout') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </aside>

    <div class="layout-right">
      <!-- ===== 顶栏 ===== -->
      <header class="layout-header">
        <div class="header-left">
          <!-- 移动端汉堡按钮 -->
          <el-icon class="hamburger" @click="drawerVisible = true"><Menu /></el-icon>
          <div class="logo-mini">
            <div class="logo-icon small">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3" />
                <circle cx="5" cy="5" r="2" /><circle cx="19" cy="5" r="2" />
                <circle cx="5" cy="19" r="2" /><circle cx="19" cy="19" r="2" />
                <path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3" />
              </svg>
            </div>
            <span class="logo-mini-text">AgentFlow</span>
          </div>
          <span class="current-page">{{ $t(String($route.meta.title || '')) }}</span>
        </div>

        <div class="header-right">
          <el-dropdown trigger="click" @command="switchLocale">
            <div class="lang-switch" :title="$t('layout.language')">
              <el-icon class="header-icon lang-icon"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" /></svg></el-icon>
              <span class="lang-label">{{ locale === 'en-US' ? 'EN' : '中文' }}</span>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="zh-CN" :class="{ 'is-active-lang': locale === 'zh-CN' }">简体中文</el-dropdown-item>
                <el-dropdown-item command="en-US" :class="{ 'is-active-lang': locale === 'en-US' }">English</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-dropdown trigger="click" @command="handleCommand">
            <div class="user-dropdown">
              <div class="user-avatar small">{{ avatarText }}</div>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>{{ userStore.userInfo?.nickname || userStore.userInfo?.username }} · {{ roleLabel }}</el-dropdown-item>
                <el-dropdown-item divided command="logout">{{ $t('layout.logout') }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- ===== 主内容 ===== -->
      <main class="layout-main" :class="{ 'no-padding': $route.path === '/ai-chat' }">
        <router-view />
      </main>
    </div>

    <!-- ===== 移动端抽屉导航 ===== -->
    <el-drawer v-model="drawerVisible" direction="ltr" size="72%" :with-header="false" class="af-nav-drawer">
      <div class="drawer-inner">
        <div class="layout-logo">
          <div class="logo-icon">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3" />
              <circle cx="5" cy="5" r="2" /><circle cx="19" cy="5" r="2" />
              <circle cx="5" cy="19" r="2" /><circle cx="19" cy="19" r="2" />
              <path d="M7 7l3 3M17 7l-3 3M7 17l3-3M17 17l-3-3" />
            </svg>
          </div>
          <div class="logo-text-group">
            <span class="logo-main-text">AgentFlow</span>
            <span class="logo-sub-text">{{ $t('layout.platform') }}</span>
          </div>
        </div>
        <nav class="layout-menu">
          <div
            v-for="item in visibleMenus"
            :key="item.path"
            class="menu-item"
            :class="{ active: isActive(item.path) }"
            @click="router.push(item.path); drawerVisible = false"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ $t(item.titleKey) }}</span>
          </div>
        </nav>
        <div class="aside-footer">
          <div class="user-info-mini" @click="handleCommand('logout')">
            <div class="user-avatar">{{ avatarText }}</div>
            <div class="user-text">
              <div class="user-name">{{ userStore.userInfo?.nickname || userStore.userInfo?.username }}</div>
              <div class="user-role">{{ roleLabel }} · {{ $t('layout.tapToLogout') }}</div>
            </div>
          </div>
        </div>
      </div>
    </el-drawer>

    <!-- ===== 移动端底部导航 ===== -->
    <nav class="mobile-tabbar">
      <div
        v-for="item in visibleMenus"
        :key="item.path"
        class="tab-item"
        :class="{ active: isActive(item.path) }"
        @click="router.push(item.path)"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ $t(item.titleKey) }}</span>
      </div>
    </nav>

    <!-- ===== 退出登录确认弹窗 ===== -->
    <LogoutDialog v-model="logoutVisible" @confirm="onLogoutConfirm" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { Sort, Menu, Monitor, ChatDotRound, Notebook, Tickets, Stamp } from '@element-plus/icons-vue'
import { LOCALE_KEY } from '@/locales'
import LogoutDialog from '@/components/LogoutDialog.vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const drawerVisible = ref(false)
/** 退出登录确认弹窗 */
const logoutVisible = ref(false)
const { t, locale } = useI18n()

// 切换语言：即时生效并持久化
const switchLocale = (lang: string) => {
  locale.value = lang
  localStorage.setItem(LOCALE_KEY, lang)
  ElMessage.success(lang === 'en-US' ? 'Switched to English' : '已切换为中文')
}

const roleLabel = computed(() => (userStore.userInfo?.role === 'admin' ? t('layout.roleAdmin') : t('layout.roleUser')))
const avatarText = computed(() => (userStore.userInfo?.nickname || userStore.userInfo?.username || 'U').slice(0, 1))

// 导航菜单：只保留已开发页面；知识库仅管理员可见
interface MenuItem { path: string; titleKey: string; icon: any; roles?: string[] }
const menus: MenuItem[] = [
  { path: userStore.userInfo?.role === 'admin' ? '/dashboard/admin' : '/dashboard/employee', titleKey: 'nav.workbench', icon: Monitor },
  { path: '/my-claims', titleKey: 'nav.myClaims', icon: Tickets, roles: ['employee'] },
  { path: '/pending-approvals', titleKey: 'nav.pendingApprovals', icon: Stamp, roles: ['admin'] },
  { path: '/ai-chat', titleKey: 'nav.aiChat', icon: ChatDotRound },
  { path: '/kb-manage', titleKey: 'nav.knowledge', icon: Notebook, roles: ['admin'] }
]
const visibleMenus = computed(() => {
  const role = userStore.userInfo?.role
  return menus.filter((item) => !item.roles || (role && item.roles.includes(role)))
})

const isActive = (path: string) => {
  if (path.startsWith('/dashboard')) return route.path.startsWith('/dashboard')
  if (path === '/kb-manage') return route.path.startsWith('/kb-manage')
  return route.path === path
}

const handleCommand = async (cmd: string) => {
  if (cmd === 'logout') {
    logoutVisible.value = true
  }
}

/** 退出登录弹窗确认 */
const onLogoutConfirm = () => {
  userStore.logout()
  ElMessage.success(t('layout.loggedOut'))
  router.push('/login')
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
  /* iOS Safari 的 100vh 包含被底部工具栏遮挡的区域，导致页面最底部
     （如分页）永远藏在浏览器工具栏后面；dvh 随工具栏收展动态变化 */
  height: 100dvh;
  display: flex;
  background: var(--af-bg);
  overflow: hidden;
}

/* ===== 侧边栏 ===== */
.layout-aside {
  width: 232px;
  flex-shrink: 0;
  background: #0d0d0d;
  border-right: 1px solid var(--af-border-soft);
  display: flex;
  flex-direction: column;
}

.layout-logo {
  height: 72px;
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 12px;
  flex-shrink: 0;
}

.logo-icon {
  width: 38px;
  height: 38px;
  background: var(--af-primary-gradient);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.logo-icon.small { width: 30px; height: 30px; border-radius: 9px; }

.logo-text-group { display: flex; flex-direction: column; }
.logo-main-text { color: var(--af-text); font-size: 17px; font-weight: 700; letter-spacing: 0.2px; }
.logo-sub-text { color: var(--af-text-3); font-size: 10px; transform-origin: left; }

.layout-menu {
  flex: 1;
  padding: 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow-y: auto;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 44px;
  padding: 0 14px;
  border-radius: 10px;
  color: var(--af-text-2);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.menu-item:hover { background: var(--af-hover); color: var(--af-text); }

.menu-item.active {
  background: var(--af-primary-gradient);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 4px 16px rgba(245, 73, 31, 0.35);
}

.menu-item .el-icon { font-size: 18px; }

.aside-footer {
  padding: 14px 12px;
  border-top: 1px solid var(--af-border-soft);
  flex-shrink: 0;
}

.user-dropdown-wrap { width: 100%; }

.user-info-mini {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s;
}
.user-info-mini:hover { background: var(--af-hover); }

.user-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--af-primary-soft);
  color: var(--af-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 14px;
  flex-shrink: 0;
}
.user-avatar.small { width: 32px; height: 32px; }

.user-text { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.user-name { font-size: 13px; font-weight: 600; color: var(--af-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.user-role { font-size: 11px; color: var(--af-text-3); }
.switch-icon { color: var(--af-text-3); font-size: 14px; }

/* ===== 右侧区域 ===== */
.layout-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.layout-header {
  height: 60px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  border-bottom: 1px solid var(--af-border-soft);
  /* 用近乎不透明的底色替代 backdrop-filter：毛玻璃会让浏览器在每次重绘时
     重新模糊整条顶栏，在无 GPU 加速的环境下会明显拖慢页面切换与滚动 */
  background: rgba(10, 10, 10, 0.96);
}

.header-left { display: flex; align-items: center; gap: 16px; min-width: 0; }
.hamburger { display: none; font-size: 22px; color: var(--af-text-2); cursor: pointer; }
.logo-mini { display: none; align-items: center; gap: 8px; }
.logo-mini-text { color: var(--af-text); font-weight: 700; font-size: 15px; }
.current-page { font-size: 14px; color: var(--af-text-3); }

.header-right { display: flex; align-items: center; gap: 16px; }

.header-icon { font-size: 19px; color: var(--af-text-2); cursor: pointer; }
.header-icon:hover { color: var(--af-text); }

.user-dropdown { cursor: pointer; display: flex; }

/* 语言切换 */
.lang-switch {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 6px 10px;
  border-radius: 10px;
  border: 1px solid var(--af-border-soft);
  background: var(--af-card);
  transition: background 0.15s;
}
.lang-switch:hover { background: var(--af-hover); }
.lang-icon { display: flex; color: var(--af-text-2); }
.lang-label { font-size: 12px; color: var(--af-text-2); font-weight: 600; }
.is-active-lang { color: var(--af-primary); font-weight: 600; }

@media (max-width: 768px) {
  .lang-label { display: none; }
  .lang-switch { padding: 6px 8px; }
}

/* ===== 主内容 ===== */
.layout-main {
  flex: 1;
  padding: 20px 24px;
  overflow-y: auto;
  /* 禁止页面级横向滚动：宽内容（表格/分页）由组件内部滚动，
     避免整页被撑宽导致卡片错位、分页被推出屏幕 */
  overflow-x: hidden;
  min-height: 0;
  min-width: 0;
}
.layout-main.no-padding { padding: 0; overflow: hidden; }

/* ===== 移动端底部导航 ===== */
.mobile-tabbar { display: none; }

/* ===== 移动端适配 ===== */
@media (max-width: 768px) {
  .layout-aside { display: none; }

  .layout-header {
    padding: 0 14px;
    height: 56px;
  }
  .hamburger { display: block; }
  .logo-mini { display: flex; }
  .current-page { display: none; }

  .header-right { gap: 14px; margin-left: auto; }

  .layout-main {
    padding: 14px;
    /* 底部导航栏高度 + 安全区域 */
    padding-bottom: calc(62px + env(safe-area-inset-bottom));
  }
  .layout-main.no-padding { padding: 0 0 calc(62px + env(safe-area-inset-bottom)); }

  .mobile-tabbar {
    display: flex;
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 100;
    height: calc(62px + env(safe-area-inset-bottom));
    padding-bottom: env(safe-area-inset-bottom);
    background: rgba(13, 13, 13, 0.98);
    border-top: 1px solid var(--af-border-soft);
  }

  .tab-item {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    color: var(--af-text-3);
    font-size: 10px;
    cursor: pointer;
    min-height: 44px;
  }
  .tab-item .el-icon { font-size: 21px; }
  .tab-item.active { color: var(--af-primary); }
}

@media (max-width: 480px) {
  .layout-main { padding: 12px; }
}

/* 抽屉内部 */
.drawer-inner {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #0d0d0d;
}
</style>
