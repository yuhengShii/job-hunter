import { describe, expect, it } from 'vitest'
import type { TrendSeries } from '@/api/stats'
import { trendDisplay } from '@/utils/trend'

const series = (entries: [string, number[]][]): TrendSeries[] =>
  entries.map(([key, counts]) => ({
    key,
    points: counts.map((count, i) => ({ date: `2026-08-${String(i + 1).padStart(2, '0')}`, count })),
  }))

describe('trendDisplay', () => {
  it('按计数降序输出 keys（与图表 y 轴一致）', () => {
    // 模拟 API 字母序返回：嘉定区在前、浦东新区在后
    const grouped = series([
      ['嘉定区', [1, 2]],
      ['浦东新区', [10, 20]],
    ])
    const { keys } = trendDisplay(grouped)
    expect(keys).toEqual(['浦东新区', '嘉定区'])
  })
  it('超过 20 组时聚合为其他并追加到最后', () => {
    const grouped = series(Array.from({ length: 25 }, (_, i) => [`地区${i}`, [25 - i]]))
    const { keys } = trendDisplay(grouped)
    expect(keys.length).toBe(21)
    expect(keys[20]).toBe('其他')
    expect(keys.slice(0, 20).every((k) => k !== '其他')).toBe(true)
  })
  it('dates 保持完整且与 seriesList 对齐', () => {
    const grouped = series([['甲', [1, 0]], ['乙', [0, 2]]])
    const { dates, seriesList } = trendDisplay(grouped)
    expect(dates).toEqual(['2026-08-01', '2026-08-02'])
    expect(seriesList[0].points.map((p) => p.date)).toEqual(dates)
    expect(seriesList[1].points.map((p) => p.date)).toEqual(dates)
  })
})
