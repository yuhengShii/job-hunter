import { beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn() },
}))

import { ElMessage } from 'element-plus'
import { http, TOKEN_KEY, USERNAME_KEY } from '@/api/http'

function makeError(status: number, data: unknown, url?: string): AxiosError {
  const config = { headers: {}, url } as unknown as InternalAxiosRequestConfig
  return new axios.AxiosError('Request failed', 'ERR_BAD_REQUEST', config, undefined, {
    status,
    statusText: 'Error',
    data,
    headers: {},
    config,
  })
}

let captured: InternalAxiosRequestConfig | undefined

function captureAdapter() {
  http.defaults.adapter = async (config) => {
    captured = config
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config } as never
  }
}

function rejectAdapter(err: unknown) {
  http.defaults.adapter = async () => {
    throw err
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  captured = undefined
  captureAdapter()
})

describe('请求拦截器', () => {
  it('有 token 时注入 Authorization', async () => {
    localStorage.setItem(TOKEN_KEY, 'abc')
    await http.get('/keywords')
    expect(captured?.headers?.Authorization).toBe('Bearer abc')
  })

  it('无 token 时不注入', async () => {
    await http.get('/keywords')
    expect(captured?.headers?.Authorization).toBeUndefined()
  })
})

describe('响应拦截器', () => {
  it('401 非登录请求：清理 token 并跳转登录', async () => {
    localStorage.setItem(TOKEN_KEY, 'abc')
    localStorage.setItem(USERNAME_KEY, 'admin')
    const assign = vi.fn()
    Object.defineProperty(window, 'location', { configurable: true, value: { assign } })
    rejectAdapter(makeError(401, { detail: '未授权' }))
    await expect(http.get('/tasks')).rejects.toBeTruthy()
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(localStorage.getItem(USERNAME_KEY)).toBeNull()
    expect(assign).toHaveBeenCalledWith('/login')
  })

  it('401 登录请求：不跳转，仅提示 detail', async () => {
    rejectAdapter(makeError(401, { detail: '用户名或密码错误' }, '/auth/login'))
    await expect(http.post('/auth/login', {})).rejects.toBeTruthy()
    expect(ElMessage.error).toHaveBeenCalledWith('用户名或密码错误')
  })

  it('非 401 错误显示 detail', async () => {
    rejectAdapter(makeError(409, { detail: '该关键字已有进行中的任务' }))
    await expect(http.post('/tasks', {})).rejects.toBeTruthy()
    expect(ElMessage.error).toHaveBeenCalledWith('该关键字已有进行中的任务')
  })

  it('无 detail 时显示通用文案', async () => {
    rejectAdapter(makeError(500, {}))
    await expect(http.get('/x')).rejects.toBeTruthy()
    expect(ElMessage.error).toHaveBeenCalledWith('请求失败')
  })

  it('网络错误显示无法连接', async () => {
    rejectAdapter(new axios.AxiosError('Network Error', 'ERR_NETWORK', { headers: {} } as never))
    await expect(http.get('/x')).rejects.toBeTruthy()
    expect(ElMessage.error).toHaveBeenCalledWith('无法连接服务器')
  })
})
