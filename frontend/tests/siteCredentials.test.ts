import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/api/http'
import { siteCredentialsApi } from '@/api/siteCredentials'

let captured: { method?: string; url?: string; data?: unknown; params?: unknown } = {}

function captureAdapter() {
  http.defaults.adapter = async (config) => {
    captured = { method: config.method, url: config.url, data: config.data, params: config.params }
    return { data: {}, status: 200, statusText: 'OK', headers: {}, config } as never
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  captured = {}
  captureAdapter()
})

describe('siteCredentialsApi', () => {
  it('list 带 site 过滤参数', async () => {
    await siteCredentialsApi.list('51job')
    expect(captured.url).toBe('/site-credentials')
    expect(captured.params).toEqual({ site: '51job' })
  })

  it('list 不带 site 时无参数', async () => {
    await siteCredentialsApi.list()
    expect(captured.params).toBeUndefined()
  })

  it('create 发送 site/username/password/remark', async () => {
    await siteCredentialsApi.create({ site: '51job', username: '138', password: 'pw', remark: '主账号' })
    expect(captured.method).toBe('post')
    expect(captured.url).toBe('/site-credentials')
    expect(JSON.parse(captured.data as string)).toEqual({ site: '51job', username: '138', password: 'pw', remark: '主账号' })
  })

  it('update 只发 remark 与 password', async () => {
    await siteCredentialsApi.update(1, { remark: '新备注', password: 'newpw' })
    expect(captured.method).toBe('put')
    expect(captured.url).toBe('/site-credentials/1')
    expect(JSON.parse(captured.data as string)).toEqual({ remark: '新备注', password: 'newpw' })
  })

  it('remove 发 DELETE', async () => {
    await siteCredentialsApi.remove(2)
    expect(captured.method).toBe('delete')
    expect(captured.url).toBe('/site-credentials/2')
  })

  it('testLogin 发 POST', async () => {
    await siteCredentialsApi.testLogin(3)
    expect(captured.method).toBe('post')
    expect(captured.url).toBe('/site-credentials/3/test-login')
  })
})
