import { beforeEach, describe, expect, it, vi } from 'vitest'
import { http } from '@/api/http'
import { applyApi } from '@/api/apply'

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

describe('applyApi', () => {
  it('create 发 POST 并带 credential_id 与 job_ids', async () => {
    await applyApi.create({ credential_id: 3, job_ids: ['j1', 'j2'] })
    expect(captured.method).toBe('post')
    expect(captured.url).toBe('/apply')
    expect(JSON.parse(captured.data as string)).toEqual({ credential_id: 3, job_ids: ['j1', 'j2'] })
  })

  it('create 缺省 job_ids 时发送 null（全部收藏）', async () => {
    await applyApi.create({ credential_id: 3, job_ids: null })
    expect(JSON.parse(captured.data as string)).toEqual({ credential_id: 3, job_ids: null })
  })

  it('list 发 GET /apply', async () => {
    await applyApi.list()
    expect(captured.method).toBe('get')
    expect(captured.url).toBe('/apply')
  })

  it('get 发 GET /apply/:id', async () => {
    await applyApi.get(5)
    expect(captured.url).toBe('/apply/5')
  })

  it('remove 发 DELETE /apply/:id', async () => {
    await applyApi.remove(5)
    expect(captured.method).toBe('delete')
    expect(captured.url).toBe('/apply/5')
  })
})
