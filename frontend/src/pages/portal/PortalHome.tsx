import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCircle2, ChevronRight, Clock, QrCode } from 'lucide-react'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Avatar, ErrorBox, Spinner, StatusChip } from '../../components/ui'
import { api, ApiError, TRAINEE_KEY } from '../../lib/api'
import { fmtDay, fmtTime } from '../../lib/format'
import { useI18n } from '../../lib/i18n'
import type { PortalMe, PortalSession } from '../../lib/types'
import PortalShell from './PortalShell'

export default function PortalHome() {
  const { t } = useI18n()
  const hasToken = !!localStorage.getItem(TRAINEE_KEY)
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['portal-me'],
    queryFn: () => api.get<PortalMe>('/portal/me', 'trainee'),
    enabled: hasToken,
    refetchInterval: 30000,
    retry: (n, e) => !(e instanceof ApiError && e.status === 401) && n < 3,
  })

  const grouped = useMemo(() => {
    const m = new Map<string, PortalSession[]>()
    for (const s of data?.sessions ?? []) m.set(s.day, [...(m.get(s.day) ?? []), s])
    return [...m.entries()]
  }, [data])

  const expired = error instanceof ApiError && error.status === 401
  if (!hasToken || expired) {
    if (expired) localStorage.removeItem(TRAINEE_KEY)
    return (
      <PortalShell subtitle={t('Trainee portal', 'بوابة المتدرب')} title={t('Scan your badge', 'امسح الباج الخاص بك')}>
        <div className="rounded-2xl bg-white p-8 text-center shadow-md">
          <QrCode className="mx-auto h-12 w-12 text-brand-600" />
          <p className="mt-4 text-slate-700">{t('Open your phone camera and scan the QR code on your badge to see your sessions and give feedback.', 'افتح كاميرا هاتفك وامسح رمز QR الموجود على الباج لعرض محاضراتك وتقييمها.')}</p>
        </div>
      </PortalShell>
    )
  }
  if (isLoading) return <PortalShell><Spinner /></PortalShell>
  if (error || !data) return <PortalShell><ErrorBox error={error} onRetry={refetch} /></PortalShell>

  const open = data.sessions.filter((s) => s.state === 'open').length

  return (
    <PortalShell subtitle={data.program_name} title={data.trainee.full_name}>
      <div className="rounded-2xl bg-white p-5 shadow-md">
        <div className="flex items-center gap-4">
          <Avatar name={data.trainee.full_name} src={data.trainee.photo_url} size={56} />
          <div className="min-w-0 flex-1">
            <div className="num font-mono text-lg font-bold text-brand-700">{data.trainee.badge_id}</div>
            {data.today.check_in_at ? (
              <div className="mt-0.5 flex items-center gap-1.5 text-sm text-emerald-700">
                <CheckCircle2 className="h-4 w-4" />
                {t('Checked in at', 'تم الحضور الساعة')} <span className="num">{fmtTime(data.today.check_in_at)}</span>
                {data.today.check_out_at && <span className="text-slate-500">· {t('out', 'انصراف')} <span className="num">{fmtTime(data.today.check_out_at)}</span></span>}
              </div>
            ) : (
              <div className="mt-0.5 flex items-center gap-1.5 text-sm text-slate-500"><Clock className="h-4 w-4" />{t('Not checked in today', 'لم تسجل حضورك اليوم')}</div>
            )}
          </div>
        </div>
        {open > 0 && <div className="mt-4 rounded-xl bg-brand-50 px-4 py-3 text-sm font-medium text-brand-700">{t(`${open} survey(s) waiting for your feedback`, `${open} استبيان في انتظار تقييمك`)}</div>}
      </div>

      {grouped.length === 0 && <div className="rounded-2xl bg-white p-8 text-center text-sm text-slate-500 shadow-md">{t('No sessions to rate right now.', 'لا توجد محاضرات للتقييم حالياً.')}</div>}

      {grouped.map(([day, items]) => (
        <section key={day}>
          <h2 className="mb-2 mt-2 px-1 text-xs font-semibold uppercase tracking-wider text-slate-500">{fmtDay(day)}</h2>
          <div className="overflow-hidden rounded-2xl bg-white shadow-md">
            {items.map((s, i) => {
              const clickable = s.state === 'open'
              const body = (
                <div className={clsx('flex items-center gap-3 px-4 py-3.5', i > 0 && 'border-t border-slate-100', clickable && 'active:bg-slate-50')}>
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-slate-900">{s.title}</div>
                    <div className="text-xs text-slate-500"><span className="num">{s.start_time}–{s.end_time}</span>{s.trainer_name && ` · ${s.trainer_name}`}</div>
                    {s.state === 'not_open' && <div className="mt-0.5 text-xs text-slate-500">{t('Opens at', 'يفتح الساعة')} <span className="num">{fmtTime(s.opens_at)}</span></div>}
                  </div>
                  <StatusChip status={s.state} />
                  {clickable && <ChevronRight className="h-5 w-5 text-slate-400 rtl:rotate-180" />}
                </div>
              )
              return clickable ? <Link key={s.id} to={`/me/survey/${s.id}`}>{body}</Link> : <div key={s.id}>{body}</div>
            })}
          </div>
        </section>
      ))}
    </PortalShell>
  )
}
