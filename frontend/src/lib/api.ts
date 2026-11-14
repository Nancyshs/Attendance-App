/** Thin fetch wrapper: JSON in/out, auth headers, consistent errors, network-failure detection. */
import { getLang, tr } from './i18n'

export class ApiError extends Error {
  status: number
  code: string
  constructor(message: string, status: number, code = 'error') {
    super(message)
    this.status = status
    this.code = code
  }
  get isNetwork() {
    return this.status === 0
  }
}

export const STAFF_KEY = 'staff_token'
export const TRAINEE_KEY = 'trainee_token'

type Kind = 'staff' | 'trainee' | 'none'

interface Options {
  method?: string
  body?: unknown
  form?: FormData
  kind?: Kind
  signal?: AbortSignal
  timeoutMs?: number
}

export const authEvents = new EventTarget()

function tokenFor(kind: Kind): string | null {
  if (kind === 'staff') return localStorage.getItem(STAFF_KEY)
  if (kind === 'trainee') return localStorage.getItem(TRAINEE_KEY)
  return null
}

export async function request<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const { method = 'GET', body, form, kind = 'staff', signal, timeoutMs = 20000 } = opts
  const headers: Record<string, string> = { Accept: 'application/json', 'X-Lang': getLang() }
  const token = tokenFor(kind)
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), timeoutMs)
  signal?.addEventListener('abort', () => ctrl.abort())

  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal: ctrl.signal,
    })
  } catch {
    throw new ApiError(tr('Cannot reach the server. Check the connection.', 'تعذّر الاتصال بالسيرفر. تحقق من الاتصال.'), 0, 'network')
  } finally {
    clearTimeout(timer)
  }

  if (res.status === 204) return undefined as T
  const isJson = res.headers.get('content-type')?.includes('application/json')
  const data = isJson ? await res.json().catch(() => null) : null

  if (!res.ok) {
    if (res.status === 401 && kind !== 'none') {
      authEvents.dispatchEvent(new CustomEvent('unauthorized', { detail: kind }))
    }
    const detail = data && typeof data.detail === 'string' ? data.detail : tr(`Request failed (${res.status})`, `فشل الطلب (${res.status})`)
    throw new ApiError(detail, res.status, data?.code ?? 'error')
  }
  return data as T
}

export const api = {
  get: <T>(path: string, kind: Kind = 'staff') => request<T>(path, { kind }),
  post: <T>(path: string, body?: unknown, kind: Kind = 'staff') => request<T>(path, { method: 'POST', body: body ?? {}, kind }),
  put: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PUT', body: body ?? {} }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: 'PATCH', body: body ?? {} }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', form, timeoutMs: 60000 }),
}

/** Downloads a protected file (PDF / XLSX) using the bearer token. */
export async function download(path: string, filename?: string, openInTab = false): Promise<void> {
  const token = localStorage.getItem(STAFF_KEY)
  const res = await fetch(`/api${path}`, { headers: { 'X-Lang': getLang(), ...(token ? { Authorization: `Bearer ${token}` } : {}) } })
  if (!res.ok) {
    const data = await res.json().catch(() => null)
    throw new ApiError(data?.detail ?? tr(`Download failed (${res.status})`, `فشل التحميل (${res.status})`), res.status)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  if (openInTab) {
    window.open(url, '_blank')
  } else {
    const a = document.createElement('a')
    a.href = url
    a.download = filename ?? 'download'
    a.click()
  }
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

export async function fetchBlobUrl(path: string): Promise<string> {
  const token = localStorage.getItem(STAFF_KEY)
  const res = await fetch(`/api${path}`, { headers: { 'X-Lang': getLang(), ...(token ? { Authorization: `Bearer ${token}` } : {}) } })
  if (!res.ok) throw new ApiError(tr('Failed to load', 'فشل التحميل'), res.status)
  return URL.createObjectURL(await res.blob())
}
