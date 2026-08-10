import { http } from './http'

export interface ScheduleOut {
  enabled: boolean
  interval_minutes: number
  keyword_ids: number[]
}

export interface ScraperConfigOut {
  max_pages: number
  headful: boolean
}

export const settingsApi = {
  getSchedule: () => http.get<ScheduleOut>('/settings/schedule').then((r) => r.data),
  updateSchedule: (data: ScheduleOut) => http.put<ScheduleOut>('/settings/schedule', data).then((r) => r.data),
  getScraperConfig: () => http.get<ScraperConfigOut>('/settings/scraper').then((r) => r.data),
}
