import { http } from './http'

export interface CompanyOut {
  id: number
  company_id: string
  name: string
  type: string | null
  industry: string | null
  size: string | null
  activity: string | null
  created_at: string
  updated_at: string
}

export interface CompanyPage {
  total: number
  items: CompanyOut[]
}

export interface CompanyQuery {
  type?: string
  industry?: string
  size?: string
  page?: number
  page_size?: number
}

export const companiesApi = {
  list: (params: CompanyQuery) => http.get<CompanyPage>('/companies', { params }).then((r) => r.data),
}
