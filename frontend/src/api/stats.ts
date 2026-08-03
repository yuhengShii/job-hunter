import { http } from './http'

export interface StatsOverview {
  total_jobs: number
  total_cities: number
  total_companies: number
  salary_parsed: number
}

export interface SalaryGroup {
  key: string
  count: number
  min: number
  max: number
  median: number
}

export interface SalaryStats {
  group_by: string
  items: SalaryGroup[]
}

export interface CountItem {
  key: string
  count: number
  ratio: number
}

export interface CompanyStats {
  industry: CountItem[]
  type: CountItem[]
  size: CountItem[]
}

export interface TrendResult {
  days: { date: string; count: number }[]
}

export interface TagItem {
  tag: string
  count: number
}

export interface DistributionItem {
  key: string
  count: number
}

export interface DistributionResult {
  group_by: string
  items: DistributionItem[]
}

export const statsApi = {
  overview: (keyword_id?: number | null) =>
    http.get<StatsOverview>('/stats/overview', { params: { keyword_id } }).then((r) => r.data),
  salary: (keyword_id?: number | null, group_by = 'city') =>
    http.get<SalaryStats>('/stats/salary', { params: { keyword_id, group_by } }).then((r) => r.data),
  company: (keyword_id?: number | null) =>
    http.get<CompanyStats>('/stats/company', { params: { keyword_id } }).then((r) => r.data),
  trend: (keyword_id?: number | null, days = 30) =>
    http.get<TrendResult>('/stats/trend', { params: { keyword_id, days } }).then((r) => r.data),
  tags: (keyword_id?: number | null, top_n = 10) =>
    http.get<TagItem[]>('/stats/tags', { params: { keyword_id, top_n } }).then((r) => r.data),
  distribution: (keyword_id?: number | null, group_by = 'city') =>
    http.get<DistributionResult>('/stats/distribution', { params: { keyword_id, group_by } }).then((r) => r.data),
}
