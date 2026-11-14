import { useMutation } from '@tanstack/react-query'
import { Copy, ExternalLink, FileText, Lock, Printer, Unlock } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, download, fetchBlobUrl } from '../lib/api'
import { fmtDayLong, fmtTime } from '../lib/format'
import { useI18n } from '../lib/i18n'
import type { Session, SurveyState } from '../lib/types'
import { Button, Field, Input, Modal, StatusChip, useToast, errMsg } from './ui'

/** Survey control for one session: QR code (title above it), open/close with a duration, link, and printing. */
export default function SurveyPanel({ session, onClose, onChanged }: { session: Session | null; onClose: () => void; onChanged: () => void }) {
  const { t } = useI18n()
  const toast = useToast()
  const [s, setS] = useState<Session | null>(session)
  const [qr, setQr] = useState<string | null>(null)
  const [minutes, setMinutes] = useState('30')
  const [, tick] = useState(0)

  useEffect(() => {
    setS(session)
    if (session) setMinutes(String(session.effective_duration_minutes))
  }, [session])

  const sessionId = session?.id
  useEffect(() => {
    if (sessionId == null) return
    let url: string | null = null
    let cancelled = false
    setQr(null)
    fetchBlobUrl(`/sessions/${sessionId}/survey-qr.svg`).then((u) => {
      url = u
      if (!cancelled) setQr(u)
    }).catch(() => undefined)
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [sessionId])

  // the state flips by itself at the closing time, so keep the display fresh
  useEffect(() => {
    if (!session) return
    const h = setInterval(() => tick((n) => n + 1), 15000)
    return () => clearInterval(h)
  }, [session])

  const open = useMutation({
    mutationFn: () => api.post<Session>(`/sessions/${s!.id}/survey/open`, { duration_minutes: Math.max(1, Number(minutes) || 30) }),
    onSuccess: (r) => {
      setS(r)
      toast.push('success', t('Survey is open', 'تم فتح الاستبيان'))
      onChanged()
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })
  const close = useMutation({
    mutationFn: () => api.post<Session>(`/sessions/${s!.id}/survey/close`),
    onSuccess: (r) => {
      setS(r)
      toast.push('success', t('Survey is closed', 'تم إغلاق الاستبيان'))
      onChanged()
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  if (!session || !s) return <Modal open={false} title="" onClose={onClose}><div /></Modal>

  const now = Date.now()
  const state: SurveyState = s.is_cancelled ? 'cancelled' : now >= new Date(s.effective_closes_at).getTime() ? 'closed' : now < new Date(s.effective_opens_at).getTime() ? 'not_open' : 'open'
  const link = s.survey_url
  const copy = () => navigator.clipboard?.writeText(link).then(() => toast.push('success', t('Link copied', 'تم نسخ الرابط'))).catch(() => undefined)

  return (
    <Modal open title={t('Survey & QR code', 'الاستبيان ورمز QR')} onClose={onClose} footer={<Button variant="secondary" onClick={onClose}>{t('Close', 'إغلاق')}</Button>}>
      <div className="grid gap-6 md:grid-cols-[auto_1fr]">
        <div className="mx-auto w-64 text-center">
          <div className="mb-3 text-lg font-bold leading-snug text-brand-800">{s.title}</div>
          <div className="mx-auto flex h-60 w-60 items-center justify-center rounded-2xl border-2 border-brand-600 bg-white p-2">
            {qr ? <img src={qr} alt="QR" className="h-full w-full" /> : <span className="text-xs text-slate-400">…</span>}
          </div>
          <div className="mt-2 text-xs text-slate-500">{[s.axis, s.trainer_name, fmtDayLong(s.day)].filter(Boolean).join(' · ')}</div>
        </div>

        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <StatusChip status={state} />
            <span className="text-sm text-slate-600">
              {state === 'open' && (new Date(s.effective_closes_at).getFullYear() >= 9000
                ? t('Stays open', 'مفتوح ولن يُغلق تلقائياً')
                : s.survey_until_end_of_day && !s.survey_closes_at
                  ? t('Closes at the end of the day', 'يُغلق آخر اليوم')
                  : t(`Closes at ${fmtTime(s.effective_closes_at)}`, `يُغلق الساعة ${fmtTime(s.effective_closes_at)}`))}
              {state === 'not_open' && t(`Opens at ${fmtTime(s.effective_opens_at)}`, `يُفتح الساعة ${fmtTime(s.effective_opens_at)}`)}
              {state === 'closed' && t('Closed — you can re-open it below.', 'مغلق — يمكنك إعادة فتحه من الأسفل.')}
            </span>
            <span className="num ms-auto text-sm text-slate-500">{t(`${s.submissions} responses`, `${s.submissions} ردّ`)}</span>
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <Field label={t('Open for (minutes)', 'مدة إتاحة الاستبيان (بالدقائق)')} hint={t('It closes automatically when the time ends. You can re-open it any time.', 'يُغلق تلقائياً عند انتهاء المدة، ويمكنك إعادة فتحه في أي وقت.')}>
              <div className="flex flex-wrap gap-2">
                <Input type="number" min={1} max={10080} className="!w-28" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
                <Button onClick={() => open.mutate()} loading={open.isPending} disabled={s.is_cancelled}>
                  <Unlock className="h-4 w-4" />
                  {state === 'open' ? t('Restart timer', 'إعادة ضبط المدة') : state === 'closed' ? t('Re-open', 'إعادة الفتح') : t('Open now', 'فتح الآن')}
                </Button>
                {state !== 'closed' && !s.is_cancelled && (
                  <Button variant="danger" onClick={() => close.mutate()} loading={close.isPending}><Lock className="h-4 w-4" />{t('Close now', 'إغلاق الآن')}</Button>
                )}
              </div>
            </Field>
          </div>

          <Field label={t('Survey link', 'رابط الاستبيان')} hint={t('Filled in automatically from this computer. A phone opens the same address.', 'بيتكتب لوحده من عنوان هذا الجهاز. الموبايل يفتح نفس العنوان.')}>
            <div className="flex gap-2">
              <Input readOnly dir="ltr" value={link} onFocus={(e) => e.currentTarget.select()} />
              <Button variant="secondary" onClick={copy} aria-label={t('Copy', 'نسخ')}><Copy className="h-4 w-4" /></Button>
              <a href={link} target="_blank" rel="noreferrer"><Button variant="secondary" aria-label={t('Open', 'فتح')}><ExternalLink className="h-4 w-4" /></Button></a>
            </div>
          </Field>

          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => download(`/sessions/${s.id}/survey-qr.pdf`, `survey_qr_${s.id}.pdf`, true).catch((e) => toast.push('error', errMsg(e)))}><Printer className="h-4 w-4" />{t('Print QR poster', 'طباعة ملصق QR')}</Button>
            <Button variant="secondary" onClick={() => window.open(`/print/survey/${s.survey_token}?print=1`, '_blank')}><FileText className="h-4 w-4" />{t('Print paper survey', 'طباعة الاستبيان ورقياً')}</Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
