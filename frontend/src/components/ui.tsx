import clsx from 'clsx'
import { AlertTriangle, CheckCircle2, Inbox, Info, Loader2, X, XCircle } from 'lucide-react'
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { tr, useI18n } from '../lib/i18n'
import type { AttendanceStatus } from '../lib/types'

// ------------------------------------------------------------------ buttons
type Variant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'success'
const variants: Record<Variant, string> = {
  primary:
    'bg-brand-600 text-white shadow-xs shadow-[inset_0_1px_0_rgba(255,255,255,0.14)] hover:bg-brand-700 active:bg-brand-800 disabled:bg-brand-600/50',
  secondary:
    'bg-white text-slate-700 border border-slate-200 shadow-xs hover:bg-slate-50 hover:border-slate-300 active:bg-slate-100 disabled:text-slate-400 disabled:hover:bg-white',
  danger: 'bg-red-600 text-white shadow-xs hover:bg-red-700 active:bg-red-800 disabled:bg-red-600/50',
  success: 'bg-olive-600 text-white shadow-xs hover:bg-olive-700 disabled:bg-olive-600/50',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 active:bg-slate-200 disabled:text-slate-400 disabled:hover:bg-transparent',
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md' | 'lg'; loading?: boolean }) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={clsx(
        'inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-lg font-semibold transition-colors duration-150 disabled:cursor-not-allowed',
        size === 'sm' && 'h-8 px-3 text-[13px]',
        size === 'md' && 'h-10 px-4 text-sm',
        size === 'lg' && 'h-12 px-6 text-base',
        variants[variant],
        className,
      )}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
}

// -------------------------------------------------------------------- forms
const fieldBase =
  'block w-full rounded-lg border border-slate-300 bg-white px-3 h-10 text-sm text-slate-900 shadow-xs transition placeholder:text-slate-400 hover:border-slate-400 focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/15 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500 aria-[invalid=true]:border-red-500'

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={clsx(fieldBase, props.className)} />
}
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={clsx(fieldBase, 'select cursor-pointer', props.className)} />
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={clsx(fieldBase, 'h-auto min-h-[88px] py-2.5 leading-relaxed', props.className)} />
}
export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={clsx('block', className)}>
      <span className="mb-1.5 block text-[13px] font-semibold text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

// -------------------------------------------------------------------- layout
export function Card({ title, actions, children, className, padded = true }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; padded?: boolean }) {
  return (
    <section className={clsx('rounded-xl border border-slate-200 bg-white shadow-card', className)}>
      {(title || actions) && (
        <header className="flex min-h-[3.25rem] flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3">
          <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>
          <div className="flex items-center gap-2">{actions}</div>
        </header>
      )}
      <div className={clsx(padded && 'p-5')}>{children}</div>
    </section>
  )
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

type Tone = 'slate' | 'green' | 'amber' | 'red' | 'blue' | 'indigo'
const toneText: Record<Tone, string> = {
  slate: 'text-slate-900',
  green: 'text-emerald-700',
  amber: 'text-amber-600',
  red: 'text-red-600',
  blue: 'text-brand-600',
  indigo: 'text-olive-600',
}
const toneChip: Record<Tone, string> = {
  slate: 'bg-slate-100 text-slate-600',
  green: 'bg-emerald-50 text-emerald-600',
  amber: 'bg-amber-50 text-amber-600',
  red: 'bg-red-50 text-red-600',
  blue: 'bg-brand-50 text-brand-600',
  indigo: 'bg-olive-100 text-olive-600',
}

export function Stat({ label, value, sub, tone = 'slate', icon }: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; icon?: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[13px] font-medium text-slate-500">{label}</div>
        {icon && <span className={clsx('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg [&>svg]:h-4 [&>svg]:w-4', toneChip[tone])}>{icon}</span>}
      </div>
      <div className={clsx('mt-2 text-3xl font-bold leading-none tracking-tight tabular-nums', toneText[tone])}>{value}</div>
      <div className="mt-1.5 min-h-[1rem] text-xs text-slate-500">{sub}</div>
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={clsx('skeleton', className)} />
}

/** Placeholder shown while a page's first data load is in flight (avoids layout jumps). */
export function PageSkeleton({ stats = 4, rows = 5 }: { stats?: number; rows?: number }) {
  return (
    <div role="status" aria-live="polite" aria-label={tr('Loading', 'جارٍ التحميل')}>
      <div className="mb-6 space-y-2">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-72" />
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: stats }, (_, i) => (
          <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
            <Skeleton className="h-4 w-20" />
            <Skeleton className="mt-3 h-8 w-16" />
          </div>
        ))}
      </div>
      <div className="mt-6 space-y-3 rounded-xl border border-slate-200 bg-white p-5 shadow-card">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    </div>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-12 text-slate-500">
      <Loader2 className="h-5 w-5 animate-spin text-brand-600" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  )
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-14 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-brand-600">
        <Inbox className="h-6 w-6" />
      </div>
      <div className="text-base font-semibold text-slate-800">{title}</div>
      {hint && <div className="mt-1 max-w-sm text-sm text-slate-500">{hint}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useI18n()
  const message = error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <XCircle className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="flex-1">{message}</div>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          {t('Retry', 'إعادة المحاولة')}
        </Button>
      )}
    </div>
  )
}

export function Avatar({ name, src, size = 36 }: { name: string; src?: string | null; size?: number }) {
  const initials = name
    .split(' ')
    .filter((w) => w && !/^\d/.test(w))
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
  return src ? (
    <img src={src} alt="" className="shrink-0 rounded-full object-cover ring-1 ring-slate-200" style={{ width: size, height: size }} loading="lazy" />
  ) : (
    <div
      className="flex shrink-0 select-none items-center justify-center rounded-full bg-brand-100 font-semibold text-brand-700"
      style={{ width: size, height: size, fontSize: size * 0.38 }}
    >
      {initials}
    </div>
  )
}

// -------------------------------------------------------------------- status
const statusStyles: Record<string, { chip: string; dot: string }> = {
  present: { chip: 'bg-emerald-50 text-emerald-800 ring-emerald-600/15', dot: 'bg-emerald-500' },
  late: { chip: 'bg-amber-50 text-amber-800 ring-amber-600/20', dot: 'bg-amber-500' },
  absent: { chip: 'bg-red-50 text-red-700 ring-red-600/15', dot: 'bg-red-500' },
  excused: { chip: 'bg-olive-100 text-olive-700 ring-olive-600/20', dot: 'bg-olive-500' },
  not_arrived: { chip: 'bg-slate-100 text-slate-600 ring-slate-500/15', dot: 'bg-slate-400' },
  upcoming: { chip: 'bg-slate-100 text-slate-500 ring-slate-500/10', dot: 'bg-slate-300' },
  no_training: { chip: 'bg-slate-100 text-slate-500 ring-slate-500/10', dot: 'bg-slate-300' },
  open: { chip: 'bg-emerald-50 text-emerald-800 ring-emerald-600/15', dot: 'bg-emerald-500' },
  not_open: { chip: 'bg-slate-100 text-slate-600 ring-slate-500/15', dot: 'bg-slate-400' },
  closed: { chip: 'bg-slate-100 text-slate-600 ring-slate-500/15', dot: 'bg-slate-500' },
  cancelled: { chip: 'bg-red-50 text-red-700 ring-red-600/15', dot: 'bg-red-500' },
  submitted: { chip: 'bg-brand-50 text-brand-700 ring-brand-600/15', dot: 'bg-brand-500' },
  not_attended: { chip: 'bg-slate-100 text-slate-500 ring-slate-500/10', dot: 'bg-slate-300' },
}

export function StatusChip({ status }: { status: AttendanceStatus | string }) {
  const { t } = useI18n()
  const labels: Record<string, string> = {
    present: t('Present', 'حاضر'),
    late: t('Late', 'متأخر'),
    absent: t('Absent', 'غائب'),
    excused: t('Excused', 'بعذر'),
    not_arrived: t('Not arrived', 'لم يصل بعد'),
    upcoming: t('Upcoming', 'قادم'),
    no_training: t('No training', 'لا يوجد تدريب'),
    open: t('Open', 'مفتوح'),
    not_open: t('Not open yet', 'لم يفتح بعد'),
    closed: t('Closed', 'مغلق'),
    cancelled: t('Cancelled', 'ملغي'),
    submitted: t('Submitted', 'تم الإرسال'),
    not_attended: t('Not attended', 'لم تحضر'),
  }
  const s = statusStyles[status] ?? statusStyles.not_arrived
  return (
    <span className={clsx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset', s.chip)}>
      <span className={clsx('h-1.5 w-1.5 rounded-full', s.dot)} />
      {labels[status] ?? status}
    </span>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (id: T) => void }) {
  return (
    <div role="tablist" className="mb-5 flex gap-1 overflow-x-auto overflow-y-hidden border-b [scrollbar-width:none] border-slate-200">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={value === tab.id}
          onClick={() => onChange(tab.id)}
          className={clsx(
            '-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors',
            value === tab.id ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

// -------------------------------------------------------------------- modal
export function Modal({ open, title, onClose, children, footer, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCloseRef.current()
    }
    document.addEventListener('keydown', onKey)
    const node = ref.current
    // Focus once when the dialog opens. Re-running this on every keystroke
    // (onClose is a new function each render) was pulling focus off the input.
    if (node && !node.contains(document.activeElement)) {
      const auto = node.querySelector<HTMLElement>('[autofocus]')
      ;(auto ?? node).focus()
    }
    return () => document.removeEventListener('keydown', onKey)
  }, [open])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-navy-950/45 p-0 backdrop-blur-[2px] sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={clsx('pop flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-pop outline-none sm:rounded-2xl', wide ? 'sm:max-w-3xl' : 'sm:max-w-lg')}
      >
        <header className="flex items-center justify-between gap-3 border-b border-slate-100 px-6 py-4">
          <h3 className="text-base font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} aria-label={tr('Close', 'إغلاق')} className="-me-2 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700">
            <X className="h-5 w-5" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 rounded-b-2xl border-t border-slate-100 bg-slate-50/70 px-6 py-3.5">{footer}</footer>}
      </div>
    </div>
  )
}

export function useConfirm() {
  const { t } = useI18n()
  const [state, setState] = useState<{ message: string; resolve: (v: boolean) => void } | null>(null)
  const confirm = useCallback(
    (message: string) => new Promise<boolean>((resolve) => setState({ message, resolve })),
    [],
  )
  const close = (v: boolean) => {
    state?.resolve(v)
    setState(null)
  }
  const dialog = (
    <Modal
      open={!!state}
      title={t('Please confirm', 'من فضلك أكّد')}
      onClose={() => close(false)}
      footer={
        <>
          <Button variant="secondary" onClick={() => close(false)}>
            {t('Cancel', 'إلغاء')}
          </Button>
          <Button variant="danger" onClick={() => close(true)}>
            {t('Confirm', 'تأكيد')}
          </Button>
        </>
      }
    >
      <div className="flex gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600">
          <AlertTriangle className="h-5 w-5" />
        </span>
        <p className="pt-2 text-sm text-slate-700">{state?.message}</p>
      </div>
    </Modal>
  )
  return { confirm, dialog }
}

// -------------------------------------------------------------------- toasts
type ToastKind = 'success' | 'error' | 'info'
interface ToastItem {
  id: number
  kind: ToastKind
  message: string
}
const ToastCtx = createContext<{ push: (kind: ToastKind, message: string) => void } | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const push = useCallback((kind: ToastKind, message: string) => {
    const id = Date.now() + Math.random()
    setItems((prev) => [...prev.slice(-3), { id, kind, message }])
    setTimeout(() => setItems((prev) => prev.filter((i) => i.id !== id)), kind === 'error' ? 6000 : 3500)
  }, [])
  const value = useMemo(() => ({ push }), [push])
  const icons = { success: CheckCircle2, error: XCircle, info: Info }
  const iconColor = { success: 'text-emerald-600', error: 'text-red-600', info: 'text-brand-600' }
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div aria-live="polite" className="no-print pointer-events-none fixed inset-x-0 bottom-4 z-[60] flex flex-col items-center gap-2 px-4">
        {items.map((i) => {
          const Icon = icons[i.kind]
          return (
            <div
              key={i.id}
              role="status"
              className="pop pointer-events-auto flex max-w-md items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-800 shadow-pop"
            >
              <Icon className={clsx('h-5 w-5 shrink-0', iconColor[i.kind])} />
              {i.message}
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastCtx)
  if (!ctx) throw new Error('ToastProvider missing')
  return ctx
}

export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : tr('Something went wrong', 'حدث خطأ غير متوقع')
}
