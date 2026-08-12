import { http } from './http'

export interface KeywordOut {
  id: number
  keyword: string
  city: string
  enabled: boolean
  scrape_mode: string
  industry: string | null
  last_scraped_at: string | null
  created_at: string
}

export const keywordsApi = {
  list: () => http.get<KeywordOut[]>('/keywords').then((r) => r.data),
  create: (data: { keyword: string; scrape_mode?: string; city?: string; industry?: string | null }) =>
    http.post<KeywordOut>('/keywords', data).then((r) => r.data),
  update: (id: number, data: { keyword?: string; scrape_mode?: string; city?: string; industry?: string | null }) =>
    http.put<KeywordOut>(`/keywords/${id}`, data).then((r) => r.data),
  remove: (id: number) => http.delete(`/keywords/${id}`),
  toggle: (id: number) => http.post<KeywordOut>(`/keywords/${id}/toggle`).then((r) => r.data),
}
