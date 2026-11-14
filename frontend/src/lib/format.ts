import { getLang, tr } from './i18n'

export let TIMEZONE = 'Africa/Cairo'
export function setTimezone(tz: string) {
  TIMEZONE = tz
}

// Arabic month / weekday names with Latin digits (matches badge IDs and 24h times); British English otherwise.
const locale = () => (getLang() === 'ar' ? 'ar-EG-u-nu-latn' : 'en-GB')

const opt = (o: Intl.DateTimeFormatOptions): Intl.DateTimeFormatOptions => ({ ...o, timeZone: TIMEZONE })

export const fmtTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleTimeString(locale(), opt({ hour: '2-digit', minute: '2-digit', hour12: false })) : '—'

export const fmtDateTime = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleString(locale(), opt({ day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }))
    : '—'

export const fmtDay = (day?: string | null) => {
  if (!day) return '—'
  const d = new Date(`${day}T12:00:00`)
  return d.toLocaleDateString(locale(), { weekday: 'short', day: '2-digit', month: 'short' })
}

export const fmtDayLong = (day: string) =>
  new Date(`${day}T12:00:00`).toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })

/** Today's date (YYYY-MM-DD) in the program timezone. */
export function todayLocal(): string {
  return new Date().toLocaleDateString('en-CA', { timeZone: TIMEZONE })
}

export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T12:00:00`)
  d.setDate(d.getDate() + n)
  return d.toLocaleDateString('en-CA')
}

export const fmtHours = (minutes?: number | null) =>
  minutes == null ? '—' : tr(`${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`, `${Math.floor(minutes / 60)}س ${String(minutes % 60).padStart(2, '0')}د`)

export function uuid(): string {
  if (crypto.randomUUID) return crypto.randomUUID().replaceAll('-', '')
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')
}

const SOURCE_LABELS: Record<string, [string, string]> = {
  usb: ['USB reader', 'قارئ USB'],
  camera: ['Camera', 'كاميرا'],
  manual: ['Manual', 'يدوي'],
  portal: ['Portal', 'بوابة'],
  offline: ['Offline', 'بدون اتصال'],
}
export const sourceLabel = (s?: string | null) => (s ? (SOURCE_LABELS[s] ? tr(...SOURCE_LABELS[s]) : s) : '')
