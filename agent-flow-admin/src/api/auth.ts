import request from './request'

export interface UserInfo {
  uid: string
  username: string
  role: 'employee' | 'admin'
  nickname?: string
}

export interface LoginResponse {
  access_token: string
  user: UserInfo
}

export interface LoginCredentials {
  username: string
  password: string
}

/**
 * 登录。后端使用 OAuth2PasswordRequestForm，
 * 只接受 application/x-www-form-urlencoded 表单，不接受 JSON。
 */
export const loginApi = (data: LoginCredentials) => {
  const form = new URLSearchParams()
  form.append('username', data.username)
  form.append('password', data.password)
  return request.post<LoginResponse>('/api/v1/auth/login', form)
}

/** 当前登录用户信息（用于刷新本地缓存的昵称 / 角色等） */
export const getMeApi = () => request.get<UserInfo>('/api/v1/auth/me')
