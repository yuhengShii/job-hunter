import { http } from './http'

export interface TaskOut {
  id: number
  keyword_id: number
  mode: string
  status: string
  total_pages: number | null
  total_found: number
  success_count: number
  failed_count: number
  last_page: number
  start_time: string | null
  end_time: string | null
  error_message: string | null
  created_at: string
  login_credential_id: number | null
  login_username: string | null
}

export const tasksApi = {
  create: (data: { keyword_id: number; mode?: string; max_pages?: number | null; login_credential_id?: number | null }) =>
    http.post<TaskOut>('/tasks', data).then((r) => r.data),
  list: () => http.get<TaskOut[]>('/tasks').then((r) => r.data),
  remove: (id: number) => http.delete(`/tasks/${id}`),
}
