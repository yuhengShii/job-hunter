import { http } from './http'

export interface JobOut {
  id: number
  job_id: string
  title: string
  salary_raw: string | null
  salary_min: number | null
  salary_max: number | null
  city: string | null
  district: string | null
  area: string | null
  tags: string[]
  publish_time: string | null
  source: string
  company_id: string | null
  company_name?: string | null
  company_activity?: string | null
  company_activity_score?: number
  job_url: string | null
  created_at: string
  updated_at: string
}

export interface JobPage {
  total: number
  items: JobOut[]
}

export interface JobQuery {
  city?: string
  company_id?: string
  keyword?: string
  tag?: string
  salary_min?: number
  salary_max?: number
  page?: number
  page_size?: number
}

export const jobsApi = {
  list: (params: JobQuery) => http.get<JobPage>('/jobs', { params }).then((r) => r.data),
  get: (jobId: string) => http.get<JobOut>(`/jobs/${jobId}`).then((r) => r.data),
}
