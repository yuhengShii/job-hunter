import { http } from './http'

export interface SiteCredentialOut {
  id: number
  site: string
  username: string
  remark: string | null
  has_password: boolean
  created_at: string
  updated_at: string
}

export interface TestLoginResult {
  ok: boolean
  message: string
}

export const siteCredentialsApi = {
  list: (site?: string) =>
    http.get<SiteCredentialOut[]>('/site-credentials', { params: site ? { site } : undefined }).then((r) => r.data),
  create: (data: { site: string; username: string; password: string; remark?: string | null }) =>
    http.post<SiteCredentialOut>('/site-credentials', data).then((r) => r.data),
  update: (id: number, data: { remark?: string | null; password?: string | null }) =>
    http.put<SiteCredentialOut>(`/site-credentials/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/site-credentials/${id}`),
  // 登录测试可能触发极验验证码人工验证（最多 120s），超时放宽到 3 分钟
  testLogin: (id: number) =>
    http.post<TestLoginResult>(`/site-credentials/${id}/test-login`, undefined, { timeout: 180000 }).then((r) => r.data),
}
