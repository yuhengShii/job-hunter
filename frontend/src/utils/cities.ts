// 51job 城市编码表（000000 = 全国）。与后端 keyword.city 字段对应。
export interface CityOption {
  value: string
  label: string
}

export const CITY_OPTIONS: CityOption[] = [
  { value: '000000', label: '全国' },
  { value: '010000', label: '北京' },
  { value: '020000', label: '上海' },
  { value: '030200', label: '广州' },
  { value: '040000', label: '深圳' },
  { value: '080200', label: '杭州' },
  { value: '170200', label: '郑州' },
]

const CITY_NAME_MAP: Record<string, string> = Object.fromEntries(
  CITY_OPTIONS.map((c) => [c.value, c.label]),
)

export function cityName(code: string | null | undefined): string {
  if (!code) return '全国'
  return CITY_NAME_MAP[code] ?? code
}
