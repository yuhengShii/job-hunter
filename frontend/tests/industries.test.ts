import { describe, expect, it } from 'vitest'
import { INDUSTRY_TREE, industryNames } from '@/utils/industries'

describe('INDUSTRY_TREE', () => {
  it('包含制药/医疗及其子行业', () => {
    const pharm = INDUSTRY_TREE.find((n) => n.value === '08')
    expect(pharm?.label).toBe('制药/医疗')
    expect(pharm?.children?.map((c) => c.value)).toContain('47')
  })
})

describe('industryNames', () => {
  it('多编码按顿号拼接名称', () => {
    expect(industryNames('08,46,47')).toBe('制药/生物工程、医疗/护理/卫生、医疗设备/器械')
  })
  it('空值返回 -', () => {
    expect(industryNames(null)).toBe('-')
    expect(industryNames('')).toBe('-')
  })
  it('未知编码原样显示', () => {
    expect(industryNames('99')).toBe('99')
  })
})
