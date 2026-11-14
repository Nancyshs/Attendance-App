import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { Html5Qrcode, Html5QrcodeSupportedFormats } from 'html5-qrcode'
import { Camera, CameraOff, CloudOff, Keyboard, LogIn, LogOut, ScanLine, Volume2, VolumeX } from 'lucide-react'
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, forwardRef, type FormEvent } from 'react'
import { flushSync } from 'react-dom'
import { Avatar, Button, Card, Input, PageHeader, StatusChip } from '../components/ui'
import { api } from '../lib/api'
import { fmtHours, fmtTime } from '../lib/format'
import { useI18n } from '../lib/i18n'
import { ScanEngine, type Mode, type ScanOutcome } from '../lib/scanEngine'
import type { Dashboard } from '../lib/types'

// ------------------------------------------------------------------ feedback (sound / vibration)
let audioCtx: AudioContext | null = null
function beep(kind: 'ok' | 'out' | 'warn' | 'bad') {
  try {
    audioCtx ??= new AudioContext()
    const tones: Record<typeof kind, number[]> = { ok: [880, 1320], out: [660, 495], warn: [440, 440], bad: [220, 160] }
    let t = audioCtx.currentTime
    for (const f of tones[kind]) {
      const osc = audioCtx.createOscillator()
      const gain = audioCtx.createGain()
      osc.frequency.value = f
      osc.type = kind === 'bad' ? 'sawtooth' : 'sine'
      gain.gain.setValueAtTime(0.18, t)
      gain.gain.exponentialRampToValueAtTime(0.001, t + 0.14)
      osc.connect(gain).connect(audioCtx.destination)
      osc.start(t)
      osc.stop(t + 0.15)
      t += 0.14
    }
  } catch {
    /* audio is a nicety, never a failure */
  }
}

function tone(o: ScanOutcome): 'in' | 'out' | 'dup' | 'bad' | 'offline' {
  if (o.offline) return 'offline'
  if (!o.result) return 'bad'
  if (!o.result.ok) return 'bad'
  if (o.result.action === 'check_in') return 'in'
  if (o.result.action === 'check_out') return 'out'
  return 'dup'
}

const toneStyles = {
  in: 'bg-emerald-600 text-white',
  out: 'bg-brand-600 text-white',
  dup: 'bg-amber-500 text-white',
  bad: 'bg-red-600 text-white',
  offline: 'bg-slate-700 text-white',
}

function ResultCard({ outcome }: { outcome: ScanOutcome | null }) {
  const { t } = useI18n()
  if (!outcome) {
    return (
      <div className="flex min-h-[260px] flex-col items-center justify-center rounded-2xl border-2 border-dashed border-slate-300 bg-white p-8 text-center">
        <span className="relative mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-brand-100 text-brand-600">
          <span className="absolute inset-0 animate-ping rounded-full bg-brand-100" />
          <ScanLine className="relative h-7 w-7" />
        </span>
        <div className="text-xl font-semibold text-slate-800">{t('Ready to scan', 'جاهز للمسح')}</div>
        <div className="mt-1 text-sm text-slate-500">{t('Scan a badge with the USB reader or the camera.', 'امسح الباج بقارئ USB أو بالكاميرا.')}</div>
      </div>
    )
  }
  const kind = tone(outcome)
  const r = outcome.result
  const title =
    kind === 'in'
      ? t('Checked in', 'تم تسجيل الحضور')
      : kind === 'out'
        ? t('Checked out', 'تم تسجيل الانصراف')
        : kind === 'dup'
          ? t('Already recorded', 'مسجّل بالفعل')
          : kind === 'offline'
            ? t('Saved offline', 'تم الحفظ دون اتصال')
            : t('Not accepted', 'غير مقبول')
  const trainee = r?.trainee
  return (
    <div key={outcome.key} className={clsx('pop rounded-2xl p-6 shadow-lg', toneStyles[kind])} role="status" aria-live="assertive">
      <div className="text-sm font-semibold uppercase tracking-wider opacity-90">{title}</div>
      <div className="mt-4 flex items-center gap-5">
        {trainee ? (
          <div className="rounded-full ring-4 ring-white/40">
            <Avatar name={trainee.full_name} src={trainee.photo_url} size={96} />
          </div>
        ) : (
          <div className="flex h-24 w-24 items-center justify-center rounded-full bg-white/20">
            <ScanLine className="h-10 w-10" />
          </div>
        )}
        <div className="min-w-0">
          <div className="truncate text-3xl font-bold leading-tight">{trainee?.full_name ?? (kind === 'offline' ? t('Will sync when online', 'ستتم المزامنة عند عودة الاتصال') : t('Unknown badge', 'باج غير معروف'))}</div>
          {trainee && (
            <div className="mt-1 flex flex-wrap items-center gap-2 text-lg opacity-95">
              <span className="num font-mono font-semibold">{trainee.badge_id}</span>
              {trainee.group_name && <span>· {trainee.group_name}</span>}
            </div>
          )}
        </div>
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-1 text-lg">
        <span className="font-medium">{outcome.error ?? r?.message ?? t('Scan stored on this device', 'تم تخزين المسح على هذا الجهاز')}</span>
        {r?.status === 'late' && <span className="rounded-full bg-white/25 px-3 py-0.5 text-sm font-semibold">{t('LATE', 'متأخر')}</span>}
        {r?.early_leave && <span className="rounded-full bg-white/25 px-3 py-0.5 text-sm font-semibold">{t('EARLY LEAVE', 'انصراف مبكر')}</span>}
        {r?.worked_minutes != null && r.action === 'check_out' && <span className="num opacity-90">{fmtHours(r.worked_minutes)}</span>}
      </div>
    </div>
  )
}

function usePhone() {
  const [phone, setPhone] = useState(() => window.matchMedia('(max-width: 1023px)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 1023px)')
    const update = () => setPhone(mq.matches)
    update()
    mq.addEventListener('change', update)
    return () => mq.removeEventListener('change', update)
  }, [])
  return phone
}

type CameraHandle = { start: () => void; stop: () => void }

// ------------------------------------------------------------------ camera
const CameraScanner = forwardRef<CameraHandle, { onCode: (code: string) => void; onError: (msg: string) => void; onLive: (live: boolean) => void }>(
  function CameraScanner({ onCode, onError, onLive }, ref) {
    const onCodeRef = useRef(onCode)
    onCodeRef.current = onCode
    const scannerRef = useRef<Html5Qrcode | null>(null)
    const liveRef = useRef(false)

    useEffect(() => {
      const scanner = new Html5Qrcode('qr-reader', { formatsToSupport: [Html5QrcodeSupportedFormats.QR_CODE], verbose: false })
      scannerRef.current = scanner
      return () => {
        liveRef.current = false
        if (scanner.isScanning) void scanner.stop().then(() => scanner.clear()).catch(() => undefined)
      }
    }, [])

    const start = useCallback(() => {
      const scanner = scannerRef.current
      if (!scanner || liveRef.current || scanner.isScanning) return
      const config = {
        fps: 12,
        qrbox: (w: number, h: number) => {
          const edge = Math.max(50, Math.floor(Math.min(w, h) * 0.72))
          return { width: edge, height: edge }
        },
      }
      const begin = (facing: 'environment' | 'user') =>
        scanner.start({ facingMode: facing }, config, (text) => onCodeRef.current(text), () => undefined)
      // Called from the tap itself, so the phone browser is allowed to open the camera.
      void begin('environment')
        .then(() => {
          liveRef.current = true
          onLive(true)
        })
        .catch((err: unknown) => {
          const msg = err instanceof Error ? err.message : String(err)
          if (/notallowed|permission|denied/i.test(msg)) {
            onError(msg)
            return
          }
          void begin('user')
            .then(() => {
              liveRef.current = true
              onLive(true)
            })
            .catch((err2: unknown) => onError(err2 instanceof Error ? err2.message : String(err2)))
        })
    }, [onError, onLive])

    const stop = useCallback(() => {
      const scanner = scannerRef.current
      liveRef.current = false
      onLive(false)
      if (scanner?.isScanning) void scanner.stop().catch(() => undefined)
    }, [onLive])

    useImperativeHandle(ref, () => ({ start, stop }), [start, stop])

    return <div id="qr-reader" className="min-h-[280px] overflow-hidden rounded-xl bg-black [&_video]:h-auto [&_video]:min-h-[280px] [&_video]:w-full [&_video]:object-cover" />
  },
)

// ------------------------------------------------------------------ page
export default function Scanner() {
  const { t } = useI18n()
  const [mode, setMode] = useState<Mode>('auto')
  const [device, setDevice] = useState(() => localStorage.getItem('scan_device') ?? '')
  const [sound, setSound] = useState(() => localStorage.getItem('scan_sound') !== 'off')
  const phone = usePhone()
  const cameraRef = useRef<CameraHandle>(null)
  const [cameraOn, setCameraOn] = useState(false)
  const [cameraError, setCameraError] = useState('')
  const [current, setCurrent] = useState<ScanOutcome | null>(null)
  const [history, setHistory] = useState<ScanOutcome[]>([])
  const [waiting, setWaiting] = useState(0)
  const [offlineCount, setOfflineCount] = useState(0)
  const [manual, setManual] = useState('')

  const settingsRef = useRef({ mode, device: device || null })
  settingsRef.current = { mode, device: device || null }
  const soundRef = useRef(sound)
  soundRef.current = sound

  const engine = useMemo(
    () =>
      new ScanEngine(
        (o) => {
          setCurrent(o)
          setHistory((h) => [o, ...h].slice(0, 30))
          const k = tone(o)
          if (soundRef.current) beep(k === 'in' ? 'ok' : k === 'out' ? 'out' : k === 'dup' || k === 'offline' ? 'warn' : 'bad')
          if (navigator.vibrate) navigator.vibrate(k === 'bad' ? [120, 60, 120] : 60)
        },
        (w, o) => {
          setWaiting(w)
          setOfflineCount(o)
        },
        () => settingsRef.current,
      ),
    [],
  )
  useEffect(() => {
    engine.start()
    return () => engine.destroy()
  }, [engine])

  // today's counters
  const { data: dash } = useQuery({
    queryKey: ['dashboard', 'scanner'],
    queryFn: () => api.get<Dashboard>('/reports/dashboard'),
    refetchInterval: 6000,
  })

  // ---- USB reader: acts as a keyboard, types the code very fast and ends with Enter
  useEffect(() => {
    let buffer = ''
    let lastKey = 0
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const now = performance.now()
      if (now - lastKey > 150) buffer = '' // a human typing is slow; a scanner is not
      lastKey = now
      if (e.key === 'Enter') {
        if (buffer.length >= 3) {
          e.preventDefault()
          engine.submit(buffer, 'usb')
        }
        buffer = ''
      } else if (e.key.length === 1) {
        buffer += e.key
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [engine])

  // keep the screen awake while scanning
  useEffect(() => {
    let lock: WakeLockSentinel | null = null
    const request = async () => {
      try {
        lock = (await navigator.wakeLock?.request('screen')) ?? null
      } catch {
        /* not supported / denied */
      }
    }
    void request()
    const onVisible = () => document.visibilityState === 'visible' && void request()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      void lock?.release()
    }
  }, [])

  const onCamera = useCallback((code: string) => engine.submit(code, 'camera'), [engine])
  const onCameraLive = useCallback((live: boolean) => setCameraOn(live), [])
  const onCameraError = useCallback(
    (msg: string) => {
      setCameraOn(false)
      // A phone blocks the camera until the person taps. The button is the retry.
      if (window.isSecureContext && /notallowed|permission|denied/i.test(msg)) return
      setCameraError(
        !window.isSecureContext
          ? t('The camera needs a secure (HTTPS) connection. Use the USB reader or open the site over HTTPS.', 'الكاميرا تحتاج اتصالاً آمناً (HTTPS). استخدم قارئ USB أو افتح الموقع عبر HTTPS.')
          : msg,
      )
    },
    [t],
  )
  const opening = useRef(false)
  const openCamera = useCallback(() => {
    if (opening.current) return
    const devices = navigator.mediaDevices
    if (!devices?.getUserMedia) {
      onCameraError('camera')
      return
    }
    opening.current = true
    setCameraError('')
    // The call itself has to happen inside the tap, or the phone refuses the camera.
    const request = devices.getUserMedia({ video: { facingMode: 'environment' } })
    void request
      .then((stream) => {
        stream.getTracks().forEach((track) => track.stop())
        flushSync(() => setCameraOn(true))
        document.getElementById('qr-reader')?.getBoundingClientRect()
        window.setTimeout(() => cameraRef.current?.start(), 200)
      })
      .catch((err: unknown) => onCameraError(err instanceof Error ? err.message : String(err)))
      .finally(() => {
        opening.current = false
      })
  }, [onCameraError])

  useEffect(() => {
    if (!phone) return
    const id = window.setTimeout(() => openCamera(), 300)
    return () => window.clearTimeout(id)
  }, [phone, openCamera])

  function submitManual(e: FormEvent) {
    e.preventDefault()
    if (manual.trim()) engine.submit(manual, 'manual')
    setManual('')
  }

  const modes: { id: Mode; label: string; icon: typeof LogIn }[] = [
    { id: 'auto', label: t('Auto', 'تلقائي'), icon: ScanLine },
    { id: 'in', label: t('Check-in', 'حضور'), icon: LogIn },
    { id: 'out', label: t('Check-out', 'انصراف'), icon: LogOut },
  ]
  const totals = dash?.totals

  return (
    <>
      <PageHeader
        title={t('Scanner', 'ماسح الحضور')}
        subtitle={t('One scan to check in, one scan to check out. Works with a USB reader and phone cameras.', 'مسحة واحدة للحضور وأخرى للانصراف. تعمل مع قارئ USB وكاميرا الهاتف.')}
        actions={
          <Button variant="secondary" size="sm" onClick={() => { setSound((s) => { localStorage.setItem('scan_sound', s ? 'off' : 'on'); return !s }) }}>
            {sound ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
            {sound ? t('Sound on', 'الصوت يعمل') : t('Sound off', 'الصوت متوقف')}
          </Button>
        }
      />

      {(offlineCount > 0 || waiting > 1) && (
        <div role="status" className="mb-4 flex items-center gap-2 rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <CloudOff className="h-4 w-4 shrink-0" />
          {offlineCount > 0 && (
            <span>
              {t(`${offlineCount} scan(s) saved on this device and will sync automatically.`, `${offlineCount} مسح محفوظ على هذا الجهاز وستتم مزامنته تلقائياً.`)}
            </span>
          )}
          {waiting > 1 && <span>{t(`${waiting} waiting to be processed…`, `${waiting} في الانتظار…`)}</span>}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-5">
        <div className="order-2 space-y-4 lg:order-1 lg:col-span-3">
          <ResultCard outcome={current} />

          <Card padded>
            <div className="flex flex-wrap items-center gap-3">
              <div className="inline-flex rounded-lg bg-slate-100 p-1">
                {modes.map(({ id, label, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => setMode(id)}
                    className={clsx('flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition', mode === id ? 'bg-white text-brand-700 shadow-sm' : 'text-slate-600 hover:text-slate-900')}
                  >
                    <Icon className="h-4 w-4" />
                    {label}
                  </button>
                ))}
              </div>
              <Input
                className="!w-40"
                placeholder={t('Device name (e.g. Gate 1)', 'اسم الجهاز (مثال: البوابة 1)')}
                value={device}
                maxLength={40}
                onChange={(e) => {
                  setDevice(e.target.value)
                  localStorage.setItem('scan_device', e.target.value)
                }}
              />
              {totals && (
                <div className="ms-auto text-end">
                  <div className="num text-2xl font-bold text-slate-900">
                    {totals.arrived}
                    <span className="text-base font-medium text-slate-400"> / {totals.active}</span>
                  </div>
                  <div className="text-xs text-slate-500">{t('arrived today', 'وصلوا اليوم')}</div>
                </div>
              )}
            </div>
            {mode !== 'auto' && (
              <p className="mt-3 text-xs text-slate-500">
                {mode === 'in'
                  ? t('Forced check-in: a second scan will never turn into a check-out.', 'حضور إجباري: المسح الثاني لن يتحول إلى انصراف.')
                  : t('Forced check-out: records the check-out immediately.', 'انصراف إجباري: يسجل الانصراف فوراً.')}
              </p>
            )}

            <form onSubmit={submitManual} className="mt-4 flex gap-2">
              <div className="relative flex-1">
                <Keyboard className="pointer-events-none absolute start-3 top-2.5 h-4 w-4 text-slate-400" />
                <Input className="ps-9 uppercase placeholder:normal-case" placeholder={t('Type a Badge ID (e.g. A07) and press Enter', 'اكتب رقم الباج (مثال A07) واضغط Enter')} value={manual} onChange={(e) => setManual(e.target.value)} maxLength={20} autoComplete="off" />
              </div>
              <Button type="submit" variant="secondary">
                {t('Record', 'تسجيل')}
              </Button>
            </form>
          </Card>
        </div>

        <div className="order-1 space-y-4 lg:order-2 lg:col-span-2">
          <Card
            title={t('Camera', 'الكاميرا')}
            actions={
              <Button size="sm" variant={cameraOn ? 'secondary' : 'primary'} onClick={() => (cameraOn ? cameraRef.current?.stop() : openCamera())}>
                {cameraOn ? <CameraOff className="h-4 w-4" /> : <Camera className="h-4 w-4" />}
                {cameraOn ? t('Stop', 'إيقاف') : t('Start camera', 'تشغيل الكاميرا')}
              </Button>
            }
          >
            {!cameraOn && (
              <button
                type="button"
                onClick={openCamera}
                className="mb-3 flex w-full flex-col items-center gap-2 rounded-2xl bg-brand-700 px-4 py-8 text-white lg:hidden"
              >
                <Camera className="h-10 w-10" />
                <span className="text-lg font-bold">{t('Open the phone camera', 'فتح كاميرا الموبايل')}</span>
              </button>
            )}
            <div className={cameraOn ? 'block' : 'hidden'}>
              <CameraScanner ref={cameraRef} onCode={onCamera} onError={onCameraError} onLive={onCameraLive} />
            </div>
            {!cameraOn && !phone && (
              <p className="py-6 text-center text-sm text-slate-500">{t('Camera is off. The USB reader works without it.', 'الكاميرا متوقفة. قارئ USB يعمل بدونها.')}</p>
            )}
            {cameraError && <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{cameraError}</p>}
          </Card>

          <Card title={t('Recent scans', 'آخر عمليات المسح')} padded={false}>
            {history.length === 0 ? (
              <p className="p-5 text-sm text-slate-500">{t('Nothing scanned yet.', 'لم يتم مسح أي شيء بعد.')}</p>
            ) : (
              <ul className="max-h-[360px] divide-y divide-slate-100 overflow-y-auto">
                {history.map((h) => {
                  const k = tone(h)
                  return (
                    <li key={h.key + h.at} className="flex items-center gap-3 px-4 py-2.5">
                      <span className={clsx('h-2.5 w-2.5 shrink-0 rounded-full', k === 'in' && 'bg-emerald-500', k === 'out' && 'bg-brand-500', k === 'dup' && 'bg-amber-500', k === 'bad' && 'bg-red-500', k === 'offline' && 'bg-slate-500')} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-slate-800">{h.result?.trainee?.full_name ?? (k === 'offline' ? t('Saved offline', 'محفوظ دون اتصال') : t('Unknown badge', 'باج غير معروف'))}</div>
                        <div className="truncate text-xs text-slate-500">{h.error ?? h.result?.message ?? ''}</div>
                      </div>
                      {h.result?.status && (h.result.action === 'check_in' || h.result.action === 'check_out') && <StatusChip status={h.result.status} />}
                      <span className="num text-xs text-slate-400">{fmtTime(new Date(h.at).toISOString())}</span>
                    </li>
                  )
                })}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  )
}
