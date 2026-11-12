import { createRouter, createWebHistory } from 'vue-router'
import MainLayout from '@/layout/MainLayout.vue'
import { useUserStore } from '@/stores/user'

// 路由级懒加载统一收敛到这里，便于空闲时预取（消除首次点击页面时的编译/加载等待）
export const lazyPages = {
  login: () => import('@/view/login.vue'),
  dashboardEmployee: () => import('@/view/dashboard/employee.vue'),
  dashboardAdmin: () => import('@/view/dashboard/admin.vue'),
  aiChat: () => import('@/view/ai-chat.vue'),
  myClaims: () => import('@/view/expense/my-claims.vue'),
  pendingApprovals: () => import('@/view/expense/pending-approvals.vue'),
  knowledgeList: () => import('@/view/knowledge/index.vue'),
  knowledgeDetail: () => import('@/view/knowledge/detail.vue'),
  knowledgeDocument: () => import('@/view/knowledge/document.vue')
}

/** 空闲时预加载全部页面组件（dev 下提前触发 Vite 编译，prod 下提前下载 chunk） */
export const prefetchLazyPages = () => {
  Object.values(lazyPages).forEach((load) => {
    load().catch(() => {
      // 预取失败静默忽略，真正导航时会重试
    })
  })
}

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: lazyPages.login
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        // 进入 /dashboard 时按角色跳转到对应子路由；本地缓存角色过期时由 beforeEach 刷新后纠正
        redirect: () => (useUserStore().userInfo?.role === 'admin' ? '/dashboard/admin' : '/dashboard/employee'),
        children: [
          {
            path: 'employee',
            name: 'DashboardEmployee',
            component: lazyPages.dashboardEmployee,
            meta: { title: 'router.workbench', role: 'employee', roles: ['employee'] }
          },
          {
            path: 'admin',
            name: 'DashboardAdmin',
            component: lazyPages.dashboardAdmin,
            meta: { title: 'router.workbench', role: 'admin' }
          }
        ]
      },
      {
        path: 'ai-chat',
        name: 'AiChat',
        component: lazyPages.aiChat,
        meta: { title: 'router.aiChat' }
      },
      {
        path: 'my-claims',
        name: 'MyClaims',
        component: lazyPages.myClaims,
        // 管理员也能发起报销，需查看自己的单据；入口在「待我审批」页内 Tab 切换，菜单不单列
        meta: { title: 'router.myClaims', roles: ['employee', 'admin'] }
      },
      {
        path: 'pending-approvals',
        name: 'PendingApprovals',
        component: lazyPages.pendingApprovals,
        meta: { title: 'router.pendingApprovals', roles: ['admin'] }
      },
      {
        // 知识库对所有登录角色开放：页面按钮均按后端返回的 permission（read/manage）
        // 显隐，员工只能看到共享/自建/被授权的库；后端接口同样按权限二次校验。
        path: 'kb-manage',
        name: 'KnowledgeList',
        component: lazyPages.knowledgeList,
        meta: { title: 'router.kbList' }
      },
      {
        path: 'kb-manage/:kbId',
        name: 'KnowledgeDetail',
        component: lazyPages.knowledgeDetail,
        meta: { title: 'router.kbDetail' }
      },
      {
        path: 'kb-manage/:kbId/docs/:docId',
        name: 'KnowledgeDocument',
        component: lazyPages.knowledgeDocument,
        meta: { title: 'router.docDetail' }
      },
      {
        // 引用原文预览：从聊天引用卡片跳转进来，所有登录角色都可只读查看，
        // 不挂 roles 限制；能否看到内容仍由后端按知识库权限二次校验。
        path: 'citation/:kbId/docs/:docId',
        name: 'CitationDocument',
        component: lazyPages.knowledgeDocument,
        meta: { title: 'router.docDetail' }
      }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})


// 每次页面加载（SPA 刷新/首次进入）只同步一次用户信息，避免每次导航都被 /auth/me 请求阻塞
let userInfoRefreshed = false

router.beforeEach(async (to, _from, next) => {
  const userStore = useUserStore()
  const token = localStorage.getItem('token')

  if (to.path === '/login') {
    if (token) {
      // 已登录，刷新用户信息后跳转到对应角色工作台
      await userStore.refreshUserInfo()
      userInfoRefreshed = true
      next(userStore.userInfo?.role === 'admin' ? '/dashboard/admin' : '/dashboard/employee')
    } else {
      next()
    }
  }
  else {
    if (token) {
      // 首次导航时同步一次用户信息，角色以服务端为准（本地缓存可能过期）
      if (!userInfoRefreshed) {
        await userStore.refreshUserInfo()
        userInfoRefreshed = true
      }
      // 角色权限：页面声明了 roles 时，当前角色不在名单内则回到自己的工作台
      const roles = to.meta?.roles as string[] | undefined
      const role = userStore.userInfo?.role
      if (roles && role && !roles.includes(role)) {
        next(role === 'admin' ? '/dashboard/admin' : '/dashboard/employee')
        return
      }
      next()
    } else {
      next('/login')
    }
  }
})


export default router
