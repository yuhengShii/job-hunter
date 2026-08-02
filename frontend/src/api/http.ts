import axios from 'axios'
import { ElMessage } from 'element-plus'

export const TOKEN_KEY = 'job_hunter_token'
export const USERNAME_KEY = 'job_hunter_username'

export const http = axios.create({ baseURL: '/api', timeout: 15000 })

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const isLoginRequest = error.config?.url?.includes('/auth/login')
    if (error.response?.status === 401 && !isLoginRequest) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USERNAME_KEY)
      window.location.assign('/login')
      return Promise.reject(error)
    }
    const detail = error.response?.data?.detail
    const msg = typeof detail === 'string' && detail ? detail : '请求失败'
    if (!error.response && !error.config?.url?.includes('/auth/login')) {
      ElMessage.error('无法连接服务器')
      return Promise.reject(error)
    }
    ElMessage.error(msg)
    return Promise.reject(error)
  },
)
