import { http } from './http'

export interface KeywordOut {
  id: number
  keyword: string
  enabled: boolean
  scrape_mode: string
  last_scraped_at: string | null
  created_at: string
}

export const keywordsApi = {
  list: () => http.get<KeywordOut[]>('/keywords').then((r) => r.data),
  create: (data: { keyword: string; scrape_mode?: string }) =>
    http.post<KeywordOut>('/keywords', data).then((r) => r.data),
  update: (id: number, data: { keyword?: string; scrape_mode?: string }) =>
    http.put<KeywordOut>(`/keywords/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/keywords/${id}`),
  toggle: (id: number) => http.post<KeywordOut>(`/keywords/${id}/toggle`).then((r) => r.data),
}
