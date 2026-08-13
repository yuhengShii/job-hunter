export interface JobFilterState {
  page: number
  page_size: number
  keyword: string
  city: string
  district: string
  area: string
  company_id: string
  tag: string
  favorite: '' | 'yes' | 'no'
  salary_min: number | undefined
  salary_max: number | undefined
  primary_sort: '' | 'activity_score' | 'publish_time'
  primary_dir: 'asc' | 'desc'
  secondary_sort: '' | 'activity_score' | 'publish_time'
  secondary_dir: 'asc' | 'desc'
  publishRange: [string, string] | null
}

export function createDefaultJobFilterState(): JobFilterState {
  return {
    page: 1,
    page_size: 20,
    keyword: '',
    city: '',
    district: '',
    area: '',
    company_id: '',
    tag: '',
    favorite: '',
    salary_min: undefined,
    salary_max: undefined,
    primary_sort: '',
    primary_dir: 'desc',
    secondary_sort: '',
    secondary_dir: 'desc',
    publishRange: null,
  }
}
