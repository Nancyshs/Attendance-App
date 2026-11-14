import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Clock, Lock } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { Button, ErrorBox, Field, Input, Spinner } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { fmtDayLong, fmtTime } from '../../lib/format'
import { useI18n } from '../../lib/i18n'
import PortalShell from './PortalShell'

type Exam = {
  program_name: string
  title: string
  axis: string | null
  day: string
  trainer_name: string | null
  state: 'not_open' | 'open' | 'closed' | 'cancelled'
  phase: 'before' | 'after' | null
  opens_at: string | null
  closes_at: string | null
  questions: { id: number; text: string }[]
}

export default function PublicExam() {
  const { token = '' } = useParams()
  const { t } = useI18n()
  const [code, setCode] = useState('')
  const [who, setWho] = useState<{ full_name: string; badge_id: string; submitted: boolean } | null>(null)
  const [whoError, setWhoError] = useState('')
  const [checking, setChecking] = useState(false)
  const [answers, setAnswers] = useState<Record<number, boolean | null>>({})
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['public-exam', token],
    queryFn: () => api.get<Exam>(`/public/exams/${token}`, 'none'),
    refetchInterval: (q) => (q.state.data?.state === 'open' ? 60000 : 15000),
  })

  if (isLoading) return <PortalShell><Spinner /></PortalShell>
  if (error || !data) return <PortalShell title={t('Exam not found', 'الامتحان غير موجود')}><ErrorBox error={error} onRetry={refetch} /></PortalShell>

  const header = { subtitle: data.program_name, title: data.title }
  const info = (
    <section className="rounded-2xl bg-white p-4 text-sm shadow-md">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
        {data.axis && (<><dt className="text-slate-500">{t('Training axis', 'المحور التدريبي')}</dt><dd className="font-semibold text-slate-900">{data.axis}</dd></>)}
        <dt className="text-slate-500">{t('Session', 'عنوان الجلسة')}</dt><dd className="font-semibold text-slate-900">{data.title}</dd>
        {data.trainer_name && (<><dt className="text-slate-500">{t('Trainer', 'اسم المدرب')}</dt><dd className="font-semibold text-slate-900">{data.trainer_name}</dd></>)}
        <dt className="text-slate-500">{t('Date', 'التاريخ')}</dt><dd className="font-semibold text-slate-900">{fmtDayLong(data.day)}</dd>
      </dl>
    </section>
  )
  const missing = data.questions.some((q) => answers[q.id] !== true && answers[q.id] !== false)

  async function identify() {
    if (checking || !code.trim()) return
    setChecking(true)
    setWhoError('')
    try {
      const found = await api.post<{ full_name: string; badge_id: string; submitted: boolean }>(`/public/exams/${token}/identify`, { badge_id: code.trim() }, 'none')
      setWho(found)
      setDone(found.submitted)
    } catch (e) {
      setWhoError(e instanceof Error ? e.message : t('Check the code', 'تأكد من الكود'))
    } finally {
      setChecking(false)
    }
  }

  async function submit() {
    if (submitting || missing || !who) return
    setSubmitting(true)
    setSubmitError('')
    try {
      const payload: Record<number, boolean> = {}
      for (const q of data!.questions) payload[q.id] = answers[q.id] as boolean
      await api.post(`/public/exams/${token}`, { badge_id: who.badge_id, answers: payload }, 'none')
      setDone(true)
    } catch (e) {
      setSubmitError(e instanceof ApiError ? e.message : t('Failed to submit', 'فشل الإرسال'))
    } finally {
      setSubmitting(false)
    }
  }

  if (data.state !== 'open') {
    return (
      <PortalShell {...header}>
        {info}
        <div className="rounded-2xl bg-white p-8 text-center shadow-md">
          {data.state === 'not_open' ? <Clock className="mx-auto h-10 w-10 text-slate-400" /> : <Lock className="mx-auto h-10 w-10 text-slate-400" />}
          <p className="mt-3 font-medium text-slate-800">
            {data.state === 'not_open' && t('This exam has not opened yet.', 'هذا الامتحان لم يُفتح بعد.')}
            {data.state === 'closed' && t('This exam is closed.', 'هذا الامتحان مغلق.')}
            {data.state === 'cancelled' && t('This session was cancelled.', 'تم إلغاء هذه المحاضرة.')}
          </p>
          {data.opens_at && data.state === 'not_open' && <p className="mt-1 text-sm text-slate-500">{t(`It opens at ${fmtTime(data.opens_at)}.`, `يُفتح في ${fmtTime(data.opens_at)}.`)}</p>}
        </div>
      </PortalShell>
    )
  }

  if (done || who?.submitted) {
    return (
      <PortalShell {...header}>
        {info}
        <div className="pop rounded-2xl bg-white p-10 text-center shadow-md">
          <CheckCircle2 className="mx-auto h-16 w-16 text-emerald-500" />
          <h2 className="mt-4 text-xl font-bold text-slate-900">{t('With sincere wishes for continued success', 'خالص التمنيات بدوام التوفيق')}</h2>
          <p className="mt-2 text-base font-semibold text-slate-800">{t('Ertekaa Integrated Services', 'شركة ارتقاء للخدمات المتكاملة')}</p>
        </div>
      </PortalShell>
    )
  }

  if (!who) {
    return (
      <PortalShell {...header}>
        {info}
        <section className="rounded-2xl bg-white p-5 shadow-md">
          <h2 className="text-base font-bold text-slate-900">{t('Enter your code', 'أدخل الكود')}</h2>
          <div className="mt-4">
            <Field label={t('Your code', 'الكود')}>
              <Input value={code} dir="ltr" autoCapitalize="characters" onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8))} />
            </Field>
          </div>
          {whoError && <p className="mt-2 text-sm text-red-600">{whoError}</p>}
          <Button className="mt-4 w-full" onClick={() => void identify()} loading={checking}>{t('Continue', 'متابعة')}</Button>
        </section>
      </PortalShell>
    )
  }

  return (
    <PortalShell {...header}>
      {info}
      <p className="rounded-2xl bg-white px-4 py-3 text-center text-sm font-medium text-slate-800 shadow-md">
        {who.full_name} <span className="num font-mono text-brand-700">{who.badge_id}</span>
      </p>
      {data.questions.map((q, i) => (
        <section key={q.id} className="rounded-2xl bg-white p-4 shadow-md">
          <p className="font-semibold text-slate-900"><span className="num me-2 text-brand-700">{i + 1}</span>{q.text}</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {[true, false].map((value) => (
              <button
                key={String(value)}
                type="button"
                onClick={() => setAnswers((a) => ({ ...a, [q.id]: value }))}
                className={`rounded-xl border-2 py-3 text-sm font-bold ${answers[q.id] === value ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-200 text-slate-700'}`}
              >
                {value ? t('True', 'صح') : t('False', 'خطأ')}
              </button>
            ))}
          </div>
        </section>
      ))}
      {submitError && <p className="text-sm text-red-600">{submitError}</p>}
      <Button className="w-full" size="lg" disabled={missing} loading={submitting} onClick={() => void submit()}>
        {missing ? t('Answer every question before sending', 'أجب عن كل الأسئلة قبل الإرسال') : t('Submit the exam', 'إرسال الامتحان')}
      </Button>
    </PortalShell>
  )
}
