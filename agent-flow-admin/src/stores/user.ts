import { defineStore } from 'pinia'
import { ref } from 'vue'
import { loginApi, getMeApi, type UserInfo } from '@/api/auth'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>('')
  const userInfo = ref<UserInfo | null>(null)
  // 每次页面加载只向后端刷新一次用户信息，避免缓存的角色/昵称过期
  let refreshed = false

  const initStorage = () => {
    token.value = localStorage.getItem('token') || ''
    const str = localStorage.getItem('userInfo')
    if (str) {
      try {
        userInfo.value = JSON.parse(str)
      } catch {
        userInfo.value = null
      }
    }
  }

  const persistUser = (user: UserInfo) => {
    userInfo.value = user
    localStorage.setItem('userInfo', JSON.stringify(user))
  }

  const login = async (username: string, password: string) => {
    const res = await loginApi({ username, password })
    if (res.code === 200 || res.code === 0) { // 后端可能返回 200 或 0，通常 FastAPI 成功是 200，但业务封装可能是 0
      token.value = res.data.access_token
      // 路由守卫与请求拦截器都从 localStorage 读取 token，必须持久化
      localStorage.setItem('token', res.data.access_token)
      persistUser(res.data.user)
      refreshed = false
      return true
    }
    return Promise.reject(res.msg || '登录失败')
  }

  /**
   * 从后端拉取当前用户信息并同步到 store / localStorage。
   * - 本地缓存的 role 可能过期（例如后端调整了角色），路由与菜单均以此为准；
   * - 无 token 或已刷新过时直接跳过；接口失败保持缓存不动（401 由拦截器统一处理）。
   */
  const refreshUserInfo = async () => {
    if (!token.value || refreshed) return
    refreshed = true
    try {
      const res = await getMeApi()
      if (res.code === 200 || res.code === 0) {
        if (res.data) persistUser(res.data)
      }
    } catch {
      // 静默失败：保留本地缓存，由响应拦截器处理鉴权问题
    }
  }

  const logout = () => {
    token.value = ''
    userInfo.value = null
    refreshed = false
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
  }

  initStorage()
  return { token, userInfo, login, logout, refreshUserInfo }
})
