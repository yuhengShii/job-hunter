import { describe, expect, it } from 'vitest'
import { favoriteParam, jobsStateFromRoute } from '@/utils/jobsQuery'

describe('jobsStateFromRoute', () => {
  it('完整参数映射', () => {
    expect(
      jobsStateFromRoute({
        city: '上海',
        district: '长宁区',
        area: '上海-长宁区',
        keyword: 'Python',
        publish_time_from: '2026-08-01',
        publish_time_to: '2026-08-01',
      }),
    ).toEqual({
      city: '上海',
      district: '长宁区',
      area: '上海-长宁区',
      keyword: 'Python',
      publishRange: ['2026-08-01', '2026-08-01'],
    })
  })
  it('日期缺失或非法返回 null', () => {
    expect(
      jobsStateFromRoute({ publish_time_from: '2026-08-01' }).publishRange,
    ).toBeNull()
    expect(
      jobsStateFromRoute({ publish_time_from: 'bad', publish_time_to: '2026-08-01' }).publishRange,
    ).toBeNull()
  })
  it('空对象返回全空', () => {
    expect(jobsStateFromRoute({})).toEqual({
      city: '',
      district: '',
      area: '',
      keyword: '',
      publishRange: null,
    })
  })
})

describe('favoriteParam', () => {
  it('maps select value to api param', () => {
    expect(favoriteParam('yes')).toBe(true)
    expect(favoriteParam('no')).toBe(false)
    expect(favoriteParam('')).toBeUndefined()
  })
})
