export interface JobsRouteState {
  city: string
  district: string
  area: string
  keyword: string
  publishRange: [string, string] | null
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export function jobsStateFromRoute(query: Record<string, unknown>): JobsRouteState {
  const str = (k: string) => (typeof query[k] === 'string' ? (query[k] as string) : '')
  const from = str('publish_time_from')
  const to = str('publish_time_to')
  return {
    city: str('city'),
    district: str('district'),
    area: str('area'),
    keyword: str('keyword'),
    publishRange: DATE_RE.test(from) && DATE_RE.test(to) ? [from, to] : null,
  }
}
