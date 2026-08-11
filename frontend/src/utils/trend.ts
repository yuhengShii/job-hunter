import type { TrendSeries } from '@/api/stats'

export const TREND_TOP_N = 20

export interface TrendDisplay {
  seriesList: TrendSeries[]
  keys: string[]
  dates: string[]
}

export function trendDisplay(grouped: TrendSeries[]): TrendDisplay {
  const total = (s: TrendSeries) => s.points.reduce((a, p) => a + p.count, 0)
  const sorted = [...grouped].sort((a, b) => total(b) - total(a))
  const top = sorted.slice(0, TREND_TOP_N)
  const rest = sorted.slice(TREND_TOP_N)
  const dates = (top[0]?.points ?? rest[0]?.points ?? []).map((p) => p.date)
  let seriesList = top
  const keys = top.map((s) => s.key)
  if (rest.length) {
    seriesList = [
      ...top,
      {
        key: '其他',
        points: dates.map((d) => ({
          date: d,
          count: rest.reduce((s, it) => s + (it.points.find((p) => p.date === d)?.count ?? 0), 0),
        })),
      },
    ]
    keys.push('其他')
  }
  return { seriesList, keys, dates }
}
