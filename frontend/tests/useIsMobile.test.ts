import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useIsMobile } from '@/composables/useIsMobile'

type Listener = (e: { matches: boolean }) => void

function stubMatchMedia(initialMatches: boolean) {
  const listeners = new Set<Listener>()
  const mql = {
    matches: initialMatches,
    addEventListener: vi.fn((_type: string, cb: Listener) => {
      listeners.add(cb)
    }),
    removeEventListener: vi.fn((_type: string, cb: Listener) => {
      listeners.delete(cb)
    }),
  }
  vi.stubGlobal('matchMedia', vi.fn(() => mql))
  return { mql, listeners }
}

describe('useIsMobile', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  it('宽度 ≤768px 返回 true', () => {
    stubMatchMedia(true)
    expect(useIsMobile().value).toBe(true)
  })

  it('宽度 >768px 返回 false', () => {
    stubMatchMedia(false)
    expect(useIsMobile().value).toBe(false)
  })

  it('matchMedia change 事件更新状态', () => {
    const { listeners } = stubMatchMedia(false)
    const isMobile = useIsMobile()
    expect(isMobile.value).toBe(false)
    listeners.forEach((cb) => cb({ matches: true }))
    expect(isMobile.value).toBe(true)
  })

  it('查询字符串为 (max-width: 768px)', () => {
    const { mql } = stubMatchMedia(false)
    useIsMobile()
    expect(window.matchMedia).toHaveBeenCalledWith('(max-width: 768px)')
  })
})
