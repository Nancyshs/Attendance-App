import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Clock, Lock } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import SurveyForm, { type Answers } from '../../components/SurveyForm'
import { Button, ErrorBox, Field, Input, Spinner } from '../../components/ui'
import { api, ApiError } from '../../lib/api'
import { fmtDayLong, fmtTime, uuid } from '../../lib/format'
import { useI18n } from '../../lib/i18n'
import type { PublicSurvey as Survey } from '../../lib/types'
import PortalShell from './PortalShell'

type Who = {
  full_name: string
  badge_id: string
  submitted: boolean
  answers: Record<string, number | string | null>
}

function readWho(key: string): Who | null {
  try {
    const raw = JSON.parse(sessionStorage.getItem(key) || 'null') as Who | null
    if (!raw || typeof raw.submitted !== 'boolean' || !raw.badge_id) return null
    return raw
  } catch {
    return null
  }
}

function toAnswers(raw: Record<string, number | string | null> | undefined): Answers {
  const out: Answers = {}
  for (const [key, value] of Object.entries(raw || {})) out[Number(key)] = value
  return out
}

function deviceId(): string {
  try {
    let id = localStorage.getItem('device_id')
    if (!id) {
      id = uuid()
      localStorage.setItem('device_id', id)
    }
    return id
  } catch {
    return uuid()
  }
}

export default function PublicSurvey() {
  const { token = '' } = useParams()
  const { t } = useI18n()
  const draftKey = `public_survey_draft_${token}`
  const [answers, setAnswers] = useState<Answers>(() => {
    try {
      return JSON.parse(localStorage.getItem(draftKey) || '{}') as Answers
    } catch {
      return {}
    }
  })
  const [done, setDone] = useState(false)
  const [editing, setEditing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const gateKey = `public_survey_gate_${token}`
  const [identified, setIdentified] = useState<Who | null>(() => readWho(gateKey))
  const [whoCode, setWhoCode] = useState('')
  const [whoError, setWhoError] = useState('')
  const [checking, setChecking] = useState(false)

  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['public-survey', token],
    queryFn: () => api.get<Survey>(`/public/surveys/${token}`, 'none'),
    // waiting for the admin to open it -> keep checking, and pick up a close/re-open without a manual refresh
    refetchInterval: (q) => (q.state.data?.state === 'not_open' || q.state.data?.state === 'closed' ? 15000 : 60000),
    retry: (n, e) => !(e instanceof ApiError && e.status < 500 && e.status !== 0) && n < 3,
  })
  useEffect(() => {
    if (!data || data.state !== 'open') return
    const left = new Date(data.closes_at).getTime() - Date.now()
    if (left <= 0 || left > 36 * 3600 * 1000) return
    const timer = window.setTimeout(() => void refetch(), left + 400)
    return () => window.clearTimeout(timer)
  }, [data, refetch])

  useEffect(() => {
    localStorage.setItem(draftKey, JSON.stringify(answers))
  }, [answers, draftKey])

  if (isLoading) return <PortalShell><Spinner /></PortalShell>
  if (error || !data) return <PortalShell title={t('Survey not found', 'الاستبيان غير موجود')}><ErrorBox error={error} onRetry={refetch} /></PortalShell>

  async function identify() {
    if (checking || !whoCode.trim()) return
    setChecking(true)
    setWhoError('')
    try {
      const who = await api.post<Who>(
        `/public/surveys/${token}/identify`,
        { badge_id: whoCode.trim() },
        'none',
      )
      sessionStorage.setItem(gateKey, JSON.stringify(who))
      setIdentified(who)
      setEditing(false)
      setDone(false)
    } catch (e) {
      setWhoError(e instanceof Error ? e.message : t('Check the code', 'تأكد من الكود'))
    } finally {
      setChecking(false)
    }
  }

  const set = (qid: number, v: number | string | null) => setAnswers((a) => ({ ...a, [qid]: v }))
  const missing = data.questions.filter((q) => {
    const value = answers[q.id]
    return value === undefined || value === null || (typeof value === 'string' && value.trim() === '')
  })
  const header = { subtitle: data.program_name, title: data.session.title }

  async function submit() {
    if (submitting || missing.length) return // guards against double taps
    setSubmitting(true)
    setSubmitError('')
    try {
      await api.post(`/public/surveys/${token}`, { device_id: deviceId(), badge_id: identified?.badge_id, answers }, 'none')
      localStorage.removeItem(draftKey)
      if (identified) {
        const saved = { ...identified, submitted: true, answers: Object.fromEntries(Object.entries(answers)) }
        sessionStorage.setItem(gateKey, JSON.stringify(saved))
        setIdentified(saved)
      }
      setEditing(false)
      setDone(true)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'already_submitted') {
        localStorage.removeItem(draftKey)
        setEditing(false)
        setDone(true)
      } else {
        if (e instanceof ApiError && (e.code === 'survey_closed' || e.code === 'survey_not_open')) void refetch()
        setSubmitError(e instanceof Error ? e.message : t('Failed to submit', 'فشل الإرسال'))
      }
    } finally {
      setSubmitting(false)
    }
  }

  const info = (
    <section className="rounded-2xl bg-white p-4 text-sm shadow-md">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
        {data.session.axis && (<><dt className="text-slate-500">{t('Training axis', 'المحور التدريبي')}</dt><dd className="font-semibold text-slate-900">{data.session.axis}</dd></>)}
        <dt className="text-slate-500">{t('Session', 'عنوان الجلسة')}</dt><dd className="font-semibold text-slate-900">{data.session.title}</dd>
        {data.session.trainer_name && (<><dt className="text-slate-500">{t('Trainer', 'اسم المدرب')}</dt><dd className="font-semibold text-slate-900">{data.session.trainer_name}</dd></>)}
        <dt className="text-slate-500">{t('Date', 'التاريخ')}</dt><dd className="font-semibold text-slate-900">{fmtDayLong(data.session.day)}</dd>
      </dl>
    </section>
  )

  if (data.state !== 'open') {
    const closed = data.state === 'closed'
    return (
      <PortalShell {...header}>
        {info}
        <div className="rounded-2xl bg-white p-8 text-center shadow-md">
          {data.state === 'not_open' ? <Clock className="mx-auto h-10 w-10 text-slate-400" /> : <Lock className="mx-auto h-10 w-10 text-slate-400" />}
          <p className="mt-3 font-medium text-slate-800">
            {data.state === 'not_open' && t('This survey has not opened yet.', 'هذا الاستبيان لم يُفتح بعد.')}
            {closed && t('This survey is closed.', 'هذا الاستبيان مغلق.')}
            {data.state === 'cancelled' && t('This session was cancelled.', 'تم إلغاء هذه المحاضرة.')}
          </p>
          {data.state === 'not_open' && <p className="mt-1 text-sm text-slate-500">{t(`It opens at ${fmtTime(data.opens_at)}. This page updates by itself.`, `يُفتح في ${fmtTime(data.opens_at)}. تتحدث هذه الصفحة تلقائياً.`)}</p>}
          {closed && <p className="mt-1 text-sm text-slate-500">{t('Ask the organisers if it should be re-opened.', 'اسأل المنظمين إن كان سيُعاد فتحه.')}</p>}
        </div>
      </PortalShell>
    )
  }

  if (!identified) {
    return (
      <PortalShell {...header}>
        {info}
        <section className="rounded-2xl bg-white p-5 shadow-md">
          <h2 className="text-base font-bold text-slate-900">{t('Enter your code', 'أدخل الكود')}</h2>
          <p className="mt-1 text-sm text-slate-500">{t('Please enter your code before starting the survey.', 'يرجى إدخال الكود قبل بدء الاستبيان.')}</p>
          <div className="mt-4">
            <Field label={t('Your code', 'الكود')}>
              <Input
                value={whoCode}
                onChange={(e) => setWhoCode(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8))}
                dir="ltr"
                autoCapitalize="characters"
                autoComplete="off"
                autoFocus
                className="font-mono tracking-widest"
              />
            </Field>
          </div>
          {whoError && <div role="alert" className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{whoError}</div>}
          <Button size="lg" className="mt-5 w-full" onClick={() => void identify()} loading={checking} disabled={!whoCode.trim()}>
            {t('Continue to the survey', 'متابعة إلى الاستبيان')}
          </Button>
        </section>
      </PortalShell>
    )
  }

  function startEdit() {
    if (!identified) return
    setAnswers(toAnswers(identified.answers))
    setSubmitError('')
    setDone(false)
    setEditing(true)
  }

  if ((done || identified.submitted) && !editing) {
    return (
      <PortalShell {...header}>
        {info}
        <div className="pop rounded-2xl bg-white p-10 text-center shadow-md">
          <CheckCircle2 className="mx-auto h-16 w-16 text-emerald-500" />
          <h2 className="mt-4 text-xl font-bold text-slate-900">
            {done
              ? t('With sincere wishes for continued success', 'خالص التمنيات بدوام التوفيق')
              : t('You already answered this survey', 'لقد أجبت على هذا الاستبيان')}
          </h2>
          {done && (
            <p className="mt-2 text-base font-semibold text-slate-800">{t('Ertekaa Integrated Services', 'شركة ارتقاء للخدمات المتكاملة')}</p>
          )}
          <p className="mt-3 text-sm text-slate-500">{t('You can change your answers while the survey is open.', 'تقدر تعدّل إجاباتك طول ما الاستبيان مفتوح.')}</p>
          <Button size="lg" className="mt-6" onClick={startEdit}>{t('Edit', 'تعديل')}</Button>
        </div>
      </PortalShell>
    )
  }

  return (
    <PortalShell {...header}>
      {info}
      <p className="px-1 text-center text-sm text-slate-600">
        <span className="font-semibold text-slate-900">{identified.full_name}</span>
        <span className="num mx-2 font-mono font-semibold text-brand-700">{identified.badge_id}</span>
      </p>
      <p className="rounded-2xl bg-white px-4 py-3 text-center text-sm font-medium leading-relaxed text-slate-800 shadow-md">
        {t('Please rate the session according to the following criteria. Note that 5 is the best rating.', 'يرجى تقييم الجلسة طبقًا للمعايير التالية، علمًا بأن 5 أفضل تقييم.')}
      </p>
      <SurveyForm
        key={editing ? 'edit' : 'new'}
        questions={data.questions}
        answers={answers}
        onChange={set}
        onSubmit={() => void submit()}
        submitting={submitting}
        canSubmit={missing.length === 0}
        submitError={submitError}
        submitLabel={
          missing.length
            ? t('Answer every question before sending', 'أجب عن كل الأسئلة قبل الإرسال')
            : identified.submitted
              ? t('Save changes', 'حفظ التعديل')
              : t('Finish the evaluation', 'إنهاء التقييم')
        }
      />
      <p className="px-1 text-center text-xs text-slate-500">{t('🔒 Your answers are anonymous.', '🔒 إجاباتك مجهولة الهوية.')}</p>
    </PortalShell>
  )
}
