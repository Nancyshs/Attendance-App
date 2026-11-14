import { useMutation } from '@tanstack/react-query'
import { Copy, ExternalLink, Lock, Printer, Unlock } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api, download, fetchBlobUrl } from '../lib/api'
import { fmtDayLong, fmtTime } from '../lib/format'
import { useI18n } from '../lib/i18n'
import type { Session, SurveyState } from '../lib/types'
import { Button, Field, Input, Modal, StatusChip, useToast, errMsg } from './ui'

type Phase = 'before' | 'after'

function sittingState(opens: string | null, closes: string | null, cancelled: boolean): SurveyState {
  if (cancelled) return 'cancelled'
  if (!opens || !closes) return 'not_open'
  const now = Date.now()
  if (now >= new Date(closes).getTime()) return 'closed'
  if (now < new Date(opens).getTime()) return 'not_open'
  return 'open'
}

/** Exam QR with the same open / close controls as the survey, once before the lecture and once after it. */
export default function ExamPanel({ session, onClose, onChanged }: { session: Session | null; onClose: () => void; onChanged: () => void }) {
  const { t } = useI18n()
  const toast = useToast()
  const [s, setS] = useState<Session | null>(session)
  const [qr, setQr] = useState<string | null>(null)
  const [beforeMinutes, setBeforeMinutes] = useState('30')
  const [afterMinutes, setAfterMinutes] = useState('30')
  const [, tick] = useState(0)

  useEffect(() => setS(session), [session])
  const sessionId = session?.id
  useEffect(() => {
    if (sessionId == null) return
    let url: string | null = null
    let cancelled = false
    setQr(null)
    fetchBlobUrl(`/sessions/${sessionId}/exam-qr.svg`).then((u) => {
      url = u
      if (!cancelled) setQr(u)
    }).catch(() => undefined)
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [sessionId])

  useEffect(() => {
    if (!session) return
    const h = setInterval(() => tick((n) => n + 1), 15000)
    return () => clearInterval(h)
  }, [session])

  const open = useMutation({
    mutationFn: ({ phase, minutes }: { phase: Phase; minutes: string }) =>
      api.post<Session>(`/sessions/${s!.id}/exam/open`, { phase, minutes: Math.max(1, Number(minutes) || 30) }),
    onSuccess: (r) => {
      setS(r)
      toast.push('success', t('The exam is open', 'تم فتح الامتحان'))
      onChanged()
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })
  const close = useMutation({
    mutationFn: (phase: Phase) => api.post<Session>(`/sessions/${s!.id}/exam/close`, { phase }),
    onSuccess: (r) => {
      setS(r)
      toast.push('success', t('The exam is closed', 'تم إغلاق الامتحان'))
      onChanged()
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  if (!session || !s) return <Modal open={false} title="" onClose={onClose}><div /></Modal>
  const link = s.exam_url
  const copy = () => navigator.clipboard?.writeText(link).then(() => toast.push('success', t('Link copied', 'تم نسخ الرابط'))).catch(() => undefined)
  const before = sittingState(s.exam_before_opens_at, s.exam_before_closes_at, s.is_cancelled)
  const after = sittingState(s.exam_after_opens_at, s.exam_after_closes_at, s.is_cancelled)
  const state: SurveyState = before === 'open' ? 'open' : after === 'open' ? 'open' : before === 'closed' || after === 'closed' ? 'closed' : 'not_open'
  const openUntil = before === 'open' ? s.exam_before_closes_at : s.exam_after_closes_at

  return (
    <Modal open title={t('Exam & QR code', 'الامتحان ورمز QR')} onClose={onClose} footer={<Button variant="secondary" onClick={onClose}>{t('Close', 'إغلاق')}</Button>}>
      <div className="grid gap-6 md:grid-cols-[auto_1fr]">
        <div className="mx-auto w-64 text-center">
          <div className="mb-3 text-lg font-bold leading-snug text-brand-800">{s.title}</div>
          <div className="mx-auto flex h-60 w-60 items-center justify-center rounded-2xl border-2 border-brand-600 bg-white p-2">
            {qr ? <img src={qr} alt="QR" className="h-full w-full" /> : <span className="text-xs text-slate-400">…</span>}
          </div>
          <div className="mt-2 text-xs text-slate-500">{[s.trainer_name, fmtDayLong(s.day)].filter(Boolean).join(' · ')}</div>
        </div>
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <StatusChip status={state} />
            <span className="text-sm text-slate-600">
              {state === 'open' && t(`Closes at ${fmtTime(openUntil)}`, `يُغلق الساعة ${fmtTime(openUntil)}`)}
              {state === 'not_open' && t('Not open yet.', 'لم يُفتح بعد.')}
              {state === 'closed' && t('Closed — you can re-open it below.', 'مغلق — يمكنك إعادة فتحه من الأسفل.')}
            </span>
            <span className="num ms-auto text-sm text-slate-500">{t(`${s.exam_questions.length} questions`, `${s.exam_questions.length} سؤال`)}</span>
          </div>

          <div className="space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
            <SittingControls
              label={t('Before the lecture (minutes)', 'مدة إتاحة الامتحان قبل المحاضرة (بالدقائق)')}
              hint={t('It closes automatically when the time ends. You can re-open it any time.', 'يُغلق تلقائياً عند انتهاء المدة، ويمكنك إعادة فتحه في أي وقت.')}
              minutes={beforeMinutes}
              onMinutes={setBeforeMinutes}
              state={before}
              cancelled={s.is_cancelled}
              opening={open.isPending}
              closing={close.isPending}
              onOpen={() => open.mutate({ phase: 'before', minutes: beforeMinutes })}
              onClose={() => close.mutate('before')}
            />
            <SittingControls
              label={t('After the lecture (minutes)', 'مدة إتاحة الامتحان بعد المحاضرة (بالدقائق)')}
              hint={t('It closes automatically when the time ends. You can re-open it any time.', 'يُغلق تلقائياً عند انتهاء المدة، ويمكنك إعادة فتحه في أي وقت.')}
              minutes={afterMinutes}
              onMinutes={setAfterMinutes}
              state={after}
              cancelled={s.is_cancelled}
              opening={open.isPending}
              closing={close.isPending}
              onOpen={() => open.mutate({ phase: 'after', minutes: afterMinutes })}
              onClose={() => close.mutate('after')}
            />
          </div>

          <Field label={t('Exam link', 'رابط الامتحان')}>
            <div className="flex gap-2">
              <Input readOnly dir="ltr" value={link} onFocus={(e) => e.currentTarget.select()} />
              <Button variant="secondary" onClick={copy} aria-label={t('Copy', 'نسخ')}><Copy className="h-4 w-4" /></Button>
              <a href={link} target="_blank" rel="noreferrer"><Button variant="secondary" aria-label={t('Open', 'فتح')}><ExternalLink className="h-4 w-4" /></Button></a>
            </div>
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => download(`/sessions/${s.id}/exam-qr.pdf`, `exam_qr_${s.id}.pdf`, true).catch((e) => toast.push('error', errMsg(e)))}><Printer className="h-4 w-4" />{t('Print QR poster', 'طباعة ملصق QR')}</Button>
            <Button variant="secondary" onClick={() => download(`/sessions/${s.id}/exam.xlsx?part=before`, `امتحان_قبل_المحاضرة_${s.id}.xlsx`).catch((e) => toast.push('error', errMsg(e)))}>{t('Excel before the lecture', 'إكسل قبل المحاضرة')}</Button>
            <Button variant="secondary" onClick={() => download(`/sessions/${s.id}/exam.xlsx?part=after`, `امتحان_بعد_المحاضرة_${s.id}.xlsx`).catch((e) => toast.push('error', errMsg(e)))}>{t('Excel after the lecture', 'إكسل بعد المحاضرة')}</Button>
            <Button variant="secondary" onClick={() => download(`/sessions/${s.id}/exam.xlsx?part=compare`, `امتحان_المقارنة_${s.id}.xlsx`).catch((e) => toast.push('error', errMsg(e)))}>{t('Excel comparison', 'إكسل المقارنة')}</Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

function SittingControls({ label, hint, minutes, onMinutes, state, cancelled, opening, closing, onOpen, onClose }: {
  label: string
  hint: string
  minutes: string
  onMinutes: (value: string) => void
  state: SurveyState
  cancelled: boolean
  opening: boolean
  closing: boolean
  onOpen: () => void
  onClose: () => void
}) {
  const { t } = useI18n()
  return (
    <Field label={label} hint={hint}>
      <div className="flex flex-wrap gap-2">
        <Input type="number" min={1} max={1440} className="!w-28" value={minutes} onChange={(e) => onMinutes(e.target.value)} />
        <Button onClick={onOpen} loading={opening} disabled={cancelled}>
          <Unlock className="h-4 w-4" />
          {state === 'open' ? t('Restart timer', 'إعادة ضبط المدة') : state === 'closed' ? t('Re-open', 'إعادة الفتح') : t('Open now', 'فتح الآن')}
        </Button>
        {state === 'open' && !cancelled && (
          <Button variant="danger" onClick={onClose} loading={closing}><Lock className="h-4 w-4" />{t('Close now', 'إغلاق الآن')}</Button>
        )}
      </div>
    </Field>
  )
}
