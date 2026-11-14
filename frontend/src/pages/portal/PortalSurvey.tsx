import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, Lock } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import SurveyForm, { type Answers } from '../../components/SurveyForm'
import { Button, ErrorBox, Spinner } from '../../components/ui'
import { api, ApiError, TRAINEE_KEY } from '../../lib/api'
import { fmtDay } from '../../lib/format'
import { useI18n } from '../../lib/i18n'
import type { PortalSurvey as Survey } from '../../lib/types'
import PortalShell from './PortalShell'

export default function PortalSurvey() {
  const { id = '' } = useParams()
  const { t } = useI18n()
  const draftKey = `survey_draft_${id}`
  const [answers, setAnswers] = useState<Answers>(() => {
    try {
      return JSON.parse(localStorage.getItem(draftKey) || '{}') as Answers
    } catch {
      return {}
    }
  })
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['portal-survey', id],
    queryFn: () => api.get<Survey>(`/portal/sessions/${id}/survey`, 'trainee'),
    enabled: !!localStorage.getItem(TRAINEE_KEY),
    retry: (n, e) => !(e instanceof ApiError && e.status < 500 && e.status !== 0) && n < 3,
  })

  // answers survive an accidental refresh / lost connection
  useEffect(() => {
    localStorage.setItem(draftKey, JSON.stringify(answers))
  }, [answers, draftKey])

  if (!localStorage.getItem(TRAINEE_KEY)) {
    return <PortalShell title={t('Please scan your badge again', 'من فضلك امسح الباج مرة أخرى')}><div /></PortalShell>
  }
  if (isLoading) return <PortalShell><Spinner /></PortalShell>
  if (error || !data) return <PortalShell><ErrorBox error={error} onRetry={refetch} /></PortalShell>

  const set = (qid: number, v: number | string | null) => setAnswers((a) => ({ ...a, [qid]: v }))
  const missing = data.questions.filter((q) => {
    const value = answers[q.id]
    return value === undefined || value === null || (typeof value === 'string' && value.trim() === '')
  })

  async function submit() {
    if (submitting || missing.length) return // guards against double taps
    setSubmitting(true)
    setSubmitError('')
    try {
      await api.post(`/portal/sessions/${id}/survey`, { answers }, 'trainee')
      localStorage.removeItem(draftKey)
      setDone(true)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'already_submitted') {
        localStorage.removeItem(draftKey)
        setDone(true)
      } else {
        setSubmitError(e instanceof Error ? e.message : t('Failed to submit', 'فشل الإرسال'))
      }
    } finally {
      setSubmitting(false)
    }
  }

  const header = { subtitle: fmtDay(data.session.day), title: data.session.title }

  if (done || data.state === 'submitted') {
    return (
      <PortalShell {...header}>
        <div className="pop rounded-2xl bg-white p-10 text-center shadow-md">
          <CheckCircle2 className="mx-auto h-16 w-16 text-emerald-500" />
          <h2 className="mt-4 text-xl font-bold text-slate-900">{t('With sincere wishes for continued success', 'خالص التمنيات بدوام التوفيق')}</h2>
          <p className="mt-2 text-base font-semibold text-slate-800">{t('Ertekaa Integrated Services', 'شركة ارتقاء للخدمات المتكاملة')}</p>
          <Link to="/me"><Button className="mt-6" size="lg">{t('Back to my sessions', 'العودة إلى محاضراتي')}</Button></Link>
        </div>
      </PortalShell>
    )
  }

  if (data.state !== 'open') {
    const reasons: Record<string, string> = {
      not_open: t('This survey has not opened yet.', 'هذا الاستبيان لم يُفتح بعد.'),
      closed: t('This survey is closed.', 'هذا الاستبيان مغلق.'),
      cancelled: t('This session was cancelled.', 'تم إلغاء هذه المحاضرة.'),
      not_attended: t('Only trainees who attended that day can rate its sessions.', 'فقط من حضر في هذا اليوم يمكنه تقييم محاضراته.'),
    }
    return (
      <PortalShell {...header}>
        <div className="rounded-2xl bg-white p-8 text-center shadow-md">
          <Lock className="mx-auto h-10 w-10 text-slate-400" />
          <p className="mt-3 text-slate-700">{reasons[data.state] ?? data.state}</p>
          <Link to="/me"><Button className="mt-5" variant="secondary">{t('Back', 'رجوع')}</Button></Link>
        </div>
      </PortalShell>
    )
  }

  return (
    <PortalShell {...header}>
      {data.session.trainer_name && <div className="px-1 pt-6 text-sm text-slate-500">{t('Trainer', 'المحاضر')}: <b className="text-slate-700">{data.session.trainer_name}</b></div>}
      <SurveyForm
        questions={data.questions}
        answers={answers}
        onChange={set}
        onSubmit={() => void submit()}
        submitting={submitting}
        canSubmit={missing.length === 0}
        submitError={submitError}
        submitLabel={missing.length ? t('Answer every question before sending', 'أجب عن كل الأسئلة قبل الإرسال') : t('Finish the evaluation', 'إنهاء التقييم')}
      />
      <p className="px-1 text-center text-xs text-slate-500">{data.is_anonymous ? t('🔒 Your answers are anonymous.', '🔒 إجاباتك مجهولة الهوية.') : t('Your name is shown with your answers.', 'يظهر اسمك مع إجاباتك.')}</p>
    </PortalShell>
  )
}
