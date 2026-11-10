import axios from 'axios'
import type { AxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

// 后端统一返回结构
export interface ApiResponse<T = unknown> {
  code: number
  msg: string
  data: T
}

// 统一的 axios 实例
const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000
})

// 请求拦截器：后续在这里加 JWT token
service.interceptors.request.use(
  (config) => {
    // 假设你把登录后拿到的 token 存在了 localStorage 里
    const token = localStorage.getItem('token'); 
    
    if (token) {
      // 拼接 Bearer 前缀
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器：后端返回 { code, msg, data } 结构，直接返回 data 层
service.interceptors.response.use(
  (res) => {
    const { code, msg } = res.data
    // 处理业务状态码（即使 HTTP 状态码为 200）
    if (code === 401) {
      handleAuthError('登录凭证已失效，请重新登录')
      return Promise.reject(new Error(msg || '登录失效'))
    }
    // 403 可能是「账号停用」，也可能是业务无权限（如知识库只读）；
    // 只有账号停用才清理登录态，其余交给业务层提示
    if (code === 403 && isAccountDisabled(msg)) {
      handleAuthError('账号已停用，请联系管理员')
      return Promise.reject(new Error(msg || '账号停用'))
    }
    return res.data
  },
  (err) => {
    if (err.response) {
      // FastAPI 的 HTTPException 错误信息在 detail 字段，统一响应结构在 msg 字段
      const { code, msg, detail } = err.response.data || {}
      const status = err.response.status

      // 处理 HTTP 状态码或响应体中的业务状态码
      if (status === 401 || code === 401) {
        handleAuthError('登录凭证已失效，请重新登录')
        return Promise.reject(new Error(msg || '登录失效'))
      }
      // 403：仅账号停用才踢登录；无权限（如知识库只读）按普通错误提示
      if ((status === 403 || code === 403) && isAccountDisabled(msg || detail)) {
        handleAuthError('账号已停用，请联系管理员')
        return Promise.reject(new Error(msg || '账号停用'))
      }
      ElMessage.error(msg || detail || `请求错误 (${status})`)
    } else {
      ElMessage.error('网络连接异常，请检查网络')
    }
    console.error('请求错误', err)
    return Promise.reject(err)
  }
)

/** 判断 403 是否由「账号停用」引起（后端 detail/msg 为「账号已停用」） */
function isAccountDisabled(message?: unknown): boolean {
  return typeof message === 'string' && message.includes('账号已停用')
}

// 提取统一的鉴权错误处理
function handleAuthError(message: string) {
  ElMessage.closeAll() // 防止重复弹窗
  ElMessage.error(message)
  localStorage.removeItem('token')
  localStorage.removeItem('userInfo')
  router.push('/login')
}

// 带返回类型的请求封装：让 TS 知道响应是 ApiResponse 而非 AxiosResponse
const request = {
  get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return service.get(url, config) as Promise<ApiResponse<T>>
  },
  post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return service.post(url, data, config) as Promise<ApiResponse<T>>
  },
  put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return service.put(url, data, config) as Promise<ApiResponse<T>>
  },
  patch<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return service.patch(url, data, config) as Promise<ApiResponse<T>>
  },
  delete<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<ApiResponse<T>> {
    return service.delete(url, config) as Promise<ApiResponse<T>>
  }
}

export default request


