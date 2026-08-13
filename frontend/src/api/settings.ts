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

export interface ScraperLoginOut {
  enabled: boolean
  credential_id: number | null
}

export const settingsApi = {
  getSchedule: () => http.get<ScheduleOut>('/settings/schedule').then((r) => r.data),
  updateSchedule: (data: ScheduleOut) => http.put<ScheduleOut>('/settings/schedule', data).then((r) => r.data),
  getScraperConfig: () => http.get<ScraperConfigOut>('/settings/scraper').then((r) => r.data),
  getScraperLogin: () => http.get<ScraperLoginOut>('/settings/scraper-login').then((r) => r.data),
  updateScraperLogin: (data: ScraperLoginOut) =>
    http.put<ScraperLoginOut>('/settings/scraper-login', data).then((r) => r.data),
}
