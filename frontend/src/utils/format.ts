export function formatTime(dt: string | null | undefined): string {
  if (!dt) return '-'
  const d = new Date(dt)
  if (Number.isNaN(d.getTime())) return '-'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function formatSalaryRaw(raw: string | null | undefined): string {
  return raw && raw.trim() ? raw.trim() : '面议'
}

function fmtSalary(n: number): string {
  if (n >= 10000) {
    const w = n / 10000
    return `${Number.isInteger(w) ? w : w.toFixed(1)}万`
  }
  if (n % 1000 === 0) return `${n / 1000}千`
  return String(n)
}

export function formatSalaryParsed(min: number | null, max: number | null): string {
  if (min != null && max != null) return `${fmtSalary(min)}-${fmtSalary(max)}`
  if (min != null) return `${fmtSalary(min)}以上`
  if (max != null) return `${fmtSalary(max)}以下`
  return '面议'
}

export type TaskStatus = 'queued' | 'in_progress' | 'success' | 'partial_success' | 'failed'

const TASK_STATUS_TEXT: Record<TaskStatus, string> = {
  queued: '排队中',
  in_progress: '进行中',
  success: '成功',
  partial_success: '部分成功',
  failed: '失败',
}

const TASK_STATUS_TYPE: Record<TaskStatus, 'info' | 'primary' | 'success' | 'warning' | 'danger'> = {
  queued: 'info',
  in_progress: 'primary',
  success: 'success',
  partial_success: 'warning',
  failed: 'danger',
}

export function taskStatusText(s: string): string {
  return TASK_STATUS_TEXT[s as TaskStatus] ?? s
}

export function taskStatusType(s: string): 'info' | 'primary' | 'success' | 'warning' | 'danger' {
  return TASK_STATUS_TYPE[s as TaskStatus] ?? 'info'
}
