import { http } from './http'

export interface ApplyResultOut {
  job_id: string
  title: string
  status: string
  message: string
}

export interface ApplyTaskOut {
  id: number
  credential_id: number | null
  credential_username: string
  status: string
  total_count: number
  success_count: number
  failed_count: number
  skipped_count: number
  results: ApplyResultOut[]
  start_time: string | null
  end_time: string | null
  error_message: string | null
  created_at: string
}

export const applyApi = {
  create: (data: { credential_id: number; job_ids?: string[] | null }) =>
    http.post<ApplyTaskOut>('/apply', data).then((r) => r.data),
  list: () => http.get<ApplyTaskOut[]>('/apply').then((r) => r.data),
  get: (id: number) => http.get<ApplyTaskOut>(`/apply/${id}`).then((r) => r.data),
  remove: (id: number) => http.delete(`/apply/${id}`),
}
