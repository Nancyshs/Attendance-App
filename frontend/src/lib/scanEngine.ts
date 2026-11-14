import { tr } from './i18n'
/**
 * Scan engine used by the scanner screen.
 *
 *  - scans are processed one at a time, in the order they were read (a queue at the door never races itself)
 *  - every scan carries a client_id, so a retry after a timeout can never double-count
 *  - when the server/network is unreachable the scan is saved on the device (with its real time) and replayed
 *    automatically, so nobody is ever turned away because of a Wi-Fi hiccup
 */
import { ApiError, api } from './api'
import { uuid } from './format'
import type { ScanResult } from './types'

export type Mode = 'auto' | 'in' | 'out'
export type Source = 'usb' | 'camera' | 'manual'

export interface QueuedScan {
  client_id: string
  code: string
  mode: Mode
  source: Source
  device: string | null
  scanned_at: string
}

export interface ScanOutcome {
  key: string
  at: number
  code: string
  result: ScanResult | null
  offline?: boolean
  error?: string
  source: Source
}

const QUEUE_KEY = 'scan_queue_v1'
const DEDUPE_MS = 2500

function loadQueue(): QueuedScan[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]') as QueuedScan[]
  } catch {
    return []
  }
}
function saveQueue(q: QueuedScan[]) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(q))
}

const isTransient = (e: unknown) =>
  e instanceof ApiError && (e.status === 0 || e.status === 502 || e.status === 503 || e.status === 504 || e.status === 408)

export class ScanEngine {
  private pending: { item: QueuedScan; resolve?: () => void }[] = []
  private running = false
  private lastSeen = new Map<string, number>()
  private timer: number | undefined
  private flushing = false

  private onOutcome: (o: ScanOutcome) => void
  private onQueueChange: (waiting: number, offline: number) => void
  private getSettings: () => { mode: Mode; device: string | null }

  constructor(
    onOutcome: (o: ScanOutcome) => void,
    onQueueChange: (waiting: number, offline: number) => void,
    getSettings: () => { mode: Mode; device: string | null },
  ) {
    this.onOutcome = onOutcome
    this.onQueueChange = onQueueChange
    this.getSettings = getSettings
  }

  /** Starts the background replay of offline scans. Call from an effect; pair with destroy(). */
  start() {
    this.destroy()
    this.timer = window.setInterval(() => void this.flushOffline(), 5000)
    window.addEventListener('online', this.onOnline)
    this.notify()
    void this.flushOffline()
  }

  destroy() {
    window.clearInterval(this.timer)
    window.removeEventListener('online', this.onOnline)
  }

  private onOnline = () => void this.flushOffline()

  private notify() {
    this.onQueueChange(this.pending.length, loadQueue().length)
  }

  /** Called for every code read by USB / camera / manual input. */
  submit(rawCode: string, source: Source) {
    const code = rawCode.trim()
    if (code.length < 3) return
    const now = Date.now()
    const last = this.lastSeen.get(code)
    if (last && now - last < DEDUPE_MS) return // camera sees the same QR many times per second
    this.lastSeen.set(code, now)
    if (this.lastSeen.size > 200) {
      for (const [k, t] of this.lastSeen) if (now - t > 60000) this.lastSeen.delete(k)
    }
    const { mode, device } = this.getSettings()
    this.pending.push({
      item: { client_id: uuid(), code, mode, source, device, scanned_at: new Date().toISOString() },
    })
    this.notify()
    void this.run()
  }

  private async run() {
    if (this.running) return
    this.running = true
    try {
      while (this.pending.length) {
        const { item } = this.pending[0]
        await this.send(item)
        this.pending.shift()
        this.notify()
      }
    } finally {
      this.running = false
    }
  }

  private async send(item: QueuedScan) {
    const base = { key: item.client_id, at: Date.now(), code: item.code, source: item.source }
    try {
      // live scans use the SERVER clock (scanned_at is only sent when replaying an offline scan)
      const result = await api.post<ScanResult>('/scan', {
        code: item.code,
        mode: item.mode,
        source: item.source,
        client_id: item.client_id,
        device: item.device,
      })
      this.onOutcome({ ...base, result })
    } catch (e) {
      if (isTransient(e)) {
        const queue = loadQueue()
        queue.push(item)
        saveQueue(queue)
        this.onOutcome({ ...base, result: null, offline: true })
      } else {
        this.onOutcome({ ...base, result: null, error: e instanceof Error ? e.message : tr('Scan failed', 'فشل المسح') })
      }
    }
  }

  /** Replays scans that were saved while offline, oldest first, stopping at the first transient failure. */
  async flushOffline() {
    if (this.flushing) return
    this.flushing = true
    try {
      for (;;) {
        const queue = loadQueue()
        if (!queue.length) break
        const item = queue[0]
        try {
          const result = await api.post<ScanResult>('/scan', { ...item })
          this.onOutcome({ key: item.client_id + ':replay', at: Date.now(), code: item.code, result, source: item.source })
        } catch (e) {
          if (isTransient(e) || (e instanceof ApiError && (e.status === 401 || e.status === 429))) break
          this.onOutcome({
            key: item.client_id + ':failed',
            at: Date.now(),
            code: item.code,
            result: null,
            error: e instanceof Error ? e.message : tr('Scan failed', 'فشل المسح'),
            source: item.source,
          })
        }
        saveQueue(loadQueue().slice(1))
        this.notify()
      }
    } finally {
      this.flushing = false
      this.notify()
    }
  }
}
