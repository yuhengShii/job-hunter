import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/auth', () => ({
  login: vi.fn(async (_u: string, _p: string) => ({ access_token: 'tok123', token_type: 'bearer' })),
}))

import { login as loginApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

describe('auth store', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('login 持久化 token 与 username', async () => {
    const store = useAuthStore()
    await store.login('admin', 'secret')
    expect(loginApi).toHaveBeenCalledWith('admin', 'secret')
    expect(store.token).toBe('tok123')
    expect(store.username).toBe('admin')
    expect(store.isAuthenticated).toBe(true)
    expect(localStorage.getItem('job_hunter_token')).toBe('tok123')
    expect(localStorage.getItem('job_hunter_username')).toBe('admin')
  })

  it('初始化时从 localStorage 恢复', () => {
    localStorage.setItem('job_hunter_token', 'saved')
    localStorage.setItem('job_hunter_username', 'alice')
    const store = useAuthStore()
    expect(store.token).toBe('saved')
    expect(store.username).toBe('alice')
    expect(store.isAuthenticated).toBe(true)
  })

  it('logout 清空状态与存储', async () => {
    const store = useAuthStore()
    await store.login('admin', 'x')
    store.logout()
    expect(store.token).toBe('')
    expect(store.username).toBe('')
    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem('job_hunter_token')).toBeNull()
  })
})
