import { describe, expect, it } from 'vitest'
import { formatSalaryParsed, formatSalaryRaw, formatTime, taskStatusText, taskStatusType } from '@/utils/format'

describe('formatSalaryRaw', () => {
  it('非空去空格原样返回', () => {
    expect(formatSalaryRaw(' 8千-1.2万 ')).toBe('8千-1.2万')
  })
  it('空值返回面议', () => {
    expect(formatSalaryRaw(null)).toBe('面议')
    expect(formatSalaryRaw('')).toBe('面议')
    expect(formatSalaryRaw('   ')).toBe('面议')
  })
})

describe('formatSalaryParsed', () => {
  it('区间换算为千/万', () => {
    expect(formatSalaryParsed(8000, 12000)).toBe('8千-1.2万')
    expect(formatSalaryParsed(15000, 20000)).toBe('1.5万-2万')
    expect(formatSalaryParsed(20000, 30000)).toBe('2万-3万')
  })
  it('单边', () => {
    expect(formatSalaryParsed(8000, null)).toBe('8千以上')
    expect(formatSalaryParsed(null, 15000)).toBe('1.5万以下')
  })
  it('全空返回面议', () => {
    expect(formatSalaryParsed(null, null)).toBe('面议')
  })
})

describe('formatTime', () => {
  it('合法时间格式化为 YYYY-MM-DD HH:mm', () => {
    expect(formatTime('2026-08-02T10:30:00')).toBe('2026-08-02 10:30')
  })
  it('null 返回 -', () => {
    expect(formatTime(null)).toBe('-')
  })
  it('非法时间返回 -', () => {
    expect(formatTime('not-a-date')).toBe('-')
  })
})

describe('任务状态', () => {
  it('文案映射', () => {
    expect(taskStatusText('queued')).toBe('排队中')
    expect(taskStatusText('in_progress')).toBe('进行中')
    expect(taskStatusText('success')).toBe('成功')
    expect(taskStatusText('partial_success')).toBe('部分成功')
    expect(taskStatusText('failed')).toBe('失败')
  })
  it('未知状态原样返回', () => {
    expect(taskStatusText('weird')).toBe('weird')
  })
  it('标签类型映射', () => {
    expect(taskStatusType('queued')).toBe('info')
    expect(taskStatusType('in_progress')).toBe('primary')
    expect(taskStatusType('success')).toBe('success')
    expect(taskStatusType('partial_success')).toBe('warning')
    expect(taskStatusType('failed')).toBe('danger')
    expect(taskStatusType('unknown')).toBe('info')
  })
})
