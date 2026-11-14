import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowDown, ArrowUp, Download, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Button, Card, EmptyState, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, Tabs, Textarea, useToast, errMsg } from '../components/ui'
import { api, download } from '../lib/api'
import { useAuth } from '../lib/auth'
import { addDays, fmtDay, fmtDateTime, todayLocal } from '../lib/format'
import { useI18n } from '../lib/i18n'
import type { Question, QuestionStat, SurveyReport, SurveyRespondent, Template, Trainer } from '../lib/types'

type Tab = 'results' | 'comments' | 'people' | 'templates'

function percentTone(avg: number | null) {
  if (avg == null) return 'bg-slate-100 text-slate-500'
  if (avg >= 4.2) return 'bg-emerald-100 text-emerald-800'
  if (avg >= 3.5) return 'bg-amber-100 text-amber-900'
  return 'bg-red-100 text-red-800'
}

function PercentCell({ q }: { q: QuestionStat }) {
  if (q.type === 'choice' && q.choices) {
    return (
      <div className="space-y-1 text-xs">
        {Object.entries(q.choices).map(([label, n]) => (
          <div key={label} className="flex items-center justify-between gap-3">
            <span className="text-slate-600">{label}</span>
            <b className="num text-slate-800">{Math.round((n / Math.max(1, q.count)) * 100)}%</b>
          </div>
        ))}
      </div>
    )
  }
  return <span className={clsx('num inline-flex min-w-16 justify-center rounded-full px-2.5 py-1 text-sm font-bold', percentTone(q.avg))}>{q.percent != null ? `${q.percent}%` : '—'}</span>
}

function Results() {
  const { t } = useI18n()
  const { user } = useAuth()
  const toast = useToast()
  const [from, setFrom] = useState(addDays(todayLocal(), -30))
  const [to, setTo] = useState(todayLocal())
  const [trainerId, setTrainerId] = useState('')
  const isTrainer = user?.role === 'trainer'
  const trainers = useQuery({ queryKey: ['trainers'], queryFn: () => api.get<Trainer[]>('/trainers') })
  const qs = `date_from=${from}&date_to=${to}${trainerId && !isTrainer ? `&trainer_id=${trainerId}` : ''}`
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['survey-report', qs], queryFn: () => api.get<SurveyReport>(`/reports/surveys?${qs}`) })

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label={t('From', 'من')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('To', 'إلى')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        {!isTrainer && (
          <Field label={t('Trainer', 'المحاضر')}>
            <Select value={trainerId} onChange={(e) => setTrainerId(e.target.value)} className="!w-48">
              <option value="">{t('All trainers', 'كل المحاضرين')}</option>
              {trainers.data?.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </Select>
          </Field>
        )}
        <Button variant="secondary" className="ms-auto" onClick={() => download(`/reports/surveys.xlsx?${qs}`, `feedback_${from}_${to}.xlsx`).catch((e) => toast.push('error', errMsg(e)))}><Download className="h-4 w-4" />{t('Export Excel', 'تصدير Excel')}</Button>
      </div>

      {isLoading ? <Spinner /> : error || !data ? <ErrorBox error={error} onRetry={refetch} /> : data.sessions.length === 0 ? (
        <Card><EmptyState title={t('No sessions in this range', 'لا توجد محاضرات في هذه الفترة')} /></Card>
      ) : (
        <Card padded={false}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] border-separate border-spacing-0 text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="bg-brand-800 text-xs text-white">
                  <th className="px-4 py-3 text-start font-semibold">{t('Session', 'المحاضرة')}</th>
                  <th className="px-3 py-3 text-start font-semibold">{t('Date', 'التاريخ')}</th>
                  <th className="px-3 py-3 text-start font-semibold">{t('Trainer', 'المدرب')}</th>
                  <th className="px-3 py-3 text-center font-semibold">{t('Session percentage', 'نسبة الجلسة')}</th>
                  <th className="px-3 py-3 text-start font-semibold">{t('Question', 'السؤال')}</th>
                  <th className="px-3 py-3 text-center font-semibold">{t('Question percentage', 'نسبة السؤال')}</th>
                  <th className="px-4 py-3 text-center font-semibold">{t('Answers', 'الإجابات')}</th>
                </tr>
              </thead>
              <tbody>
                {data.sessions.map((s, index) => {
                  const questions = s.questions.length ? s.questions : [null]
                  const stripe = index % 2 === 0 ? 'bg-white' : 'bg-brand-50/50'
                  return questions.map((q, row) => (
                    <tr key={q ? `${s.id}-${q.question_id}` : s.id} className={stripe}>
                      {row === 0 && (
                        <>
                          <td rowSpan={questions.length} className={`border-b border-slate-200 px-4 py-3 align-top font-medium text-slate-900 ${stripe}`}>{s.title}</td>
                          <td rowSpan={questions.length} className={`num border-b border-slate-200 px-3 py-3 align-top text-slate-600 ${stripe}`}>{fmtDay(s.day)}<div className="text-xs text-slate-400">{s.start_time}–{s.end_time}</div></td>
                          <td rowSpan={questions.length} className={`border-b border-slate-200 px-3 py-3 align-top text-slate-700 ${stripe}`}>{s.trainer_name || '—'}</td>
                          <td rowSpan={questions.length} className={`border-b border-slate-200 px-3 py-3 text-center align-middle ${stripe}`}>
                            <span className={clsx('num inline-flex min-w-16 justify-center rounded-full px-2.5 py-1 text-sm font-bold', percentTone(s.avg_rating))}>{s.percent != null ? `${s.percent}%` : '—'}</span>
                          </td>
                        </>
                      )}
                      <td className="border-b border-slate-100 px-3 py-3 text-slate-800">{q?.text ?? '—'}</td>
                      <td className="border-b border-slate-100 px-3 py-3 text-center">{q ? <PercentCell q={q} /> : '—'}</td>
                      <td className="num border-b border-slate-100 px-4 py-3 text-center text-slate-600">{q?.count ?? s.responses}</td>
                    </tr>
                  ))
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </>
  )
}

const RATING_AR = ['ضعيف جدًا', 'ضعيف', 'مقبول', 'جيد', 'ممتاز']
const RATING_EN = ['Very poor', 'Poor', 'Fair', 'Good', 'Excellent']

function includes(value: string | null | undefined, query: string) {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  return (value || '').toLowerCase().includes(needle)
}

function answerLabel(type: string, value: number | string | null, arabic: boolean) {
  if (value == null || value === '') return '—'
  if (type === 'rating' && typeof value === 'number') {
    const word = (arabic ? RATING_AR : RATING_EN)[value - 1]
    return word ? `${value} — ${word}` : String(value)
  }
  return String(value)
}

function Respondents() {
  const { t, lang } = useI18n()
  const [from, setFrom] = useState(addDays(todayLocal(), -30))
  const [to, setTo] = useState(todayLocal())
  const [filters, setFilters] = useState({ name: '', code: '', governorate: '', organization: '', job: '', phone: '', nationalId: '', session: '', trainer: '' })
  const [open, setOpen] = useState<SurveyRespondent | null>(null)
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['survey-respondents', from, to],
    queryFn: () => api.get<{ rows: SurveyRespondent[] }>(`/reports/survey-respondents?date_from=${from}&date_to=${to}`),
  })
  const set = (key: keyof typeof filters, value: string) => setFilters((f) => ({ ...f, [key]: value }))
  const sessions = [...new Map((data?.rows ?? []).map((r) => [r.session.id, r.session])).values()]
  const rows = (data?.rows ?? []).filter((r) => {
    const p = r.trainee
    return (
      includes(p.full_name, filters.name) &&
      includes(p.badge_id, filters.code) &&
      includes(p.governorate, filters.governorate) &&
      includes(p.organization, filters.organization) &&
      includes(p.job_title, filters.job) &&
      includes(p.phone, filters.phone) &&
      includes(p.national_id, filters.nationalId) &&
      includes(r.session.trainer_name, filters.trainer) &&
      (!filters.session || String(r.session.id) === filters.session)
    )
  })
  const arabic = lang !== 'en'

  return (
    <>
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label={t('From', 'من')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('To', 'إلى')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Field label={t('Session', 'الجلسة')}>
          <Select value={filters.session} onChange={(e) => set('session', e.target.value)}>
            <option value="">{t('All sessions', 'كل الجلسات')}</option>
            {sessions.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </Select>
        </Field>
        <Field label={t('Trainer', 'المحاضر')}><Input value={filters.trainer} onChange={(e) => set('trainer', e.target.value)} /></Field>
        <Field label={t('Name', 'الاسم')}><Input value={filters.name} onChange={(e) => set('name', e.target.value)} /></Field>
        <Field label={t('Code', 'الكود')}><Input value={filters.code} onChange={(e) => set('code', e.target.value)} dir="ltr" /></Field>
        <Field label={t('Governorate', 'المحافظة')}><Input value={filters.governorate} onChange={(e) => set('governorate', e.target.value)} /></Field>
        <Field label={t('Organization', 'الجهة')}><Input value={filters.organization} onChange={(e) => set('organization', e.target.value)} /></Field>
        <Field label={t('Job title', 'الوظيفة')}><Input value={filters.job} onChange={(e) => set('job', e.target.value)} /></Field>
        <Field label={t('Phone', 'رقم التليفون')}><Input value={filters.phone} onChange={(e) => set('phone', e.target.value)} dir="ltr" /></Field>
        <Field label={t('National ID', 'رقم البطاقة')}><Input value={filters.nationalId} onChange={(e) => set('nationalId', e.target.value)} dir="ltr" /></Field>
      </div>
      {isLoading ? <Spinner /> : error ? <ErrorBox error={error} onRetry={refetch} /> : rows.length === 0 ? (
        <Card><EmptyState title={t('No trainees match', 'لا يوجد متدربون مطابقون')} /></Card>
      ) : (
        <Card title={t(`${rows.length} trainees`, `${rows.length} متدرب`)} padded={false}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-4 py-3 text-start font-medium">{t('Name', 'الاسم')}</th>
                  <th className="px-3 py-3 text-start font-medium">{t('Code', 'الكود')}</th>
                  <th className="px-3 py-3 text-start font-medium">{t('Session', 'الجلسة')}</th>
                  <th className="px-3 py-3 text-start font-medium">{t('Trainer', 'المحاضر')}</th>
                  <th className="px-3 py-3 text-start font-medium">{t('Governorate', 'المحافظة')}</th>
                  <th className="px-3 py-3 text-start font-medium">{t('Organization', 'الجهة')}</th>
                  <th className="px-3 py-3 text-start font-medium">{t('Job title', 'الوظيفة')}</th>
                  <th className="px-3 py-3 text-start font-medium">{t('Phone', 'التليفون')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.response_id} className="cursor-pointer hover:bg-brand-50/50" onClick={() => setOpen(r)}>
                    <td className="px-4 py-3 font-medium text-slate-900">{r.trainee.full_name}</td>
                    <td className="num px-3 py-3 font-mono text-brand-800">{r.trainee.badge_id}</td>
                    <td className="px-3 py-3 text-slate-700">{r.session.title}</td>
                    <td className="px-3 py-3 text-slate-700">{r.session.trainer_name || '—'}</td>
                    <td className="px-3 py-3 text-slate-700">{r.trainee.governorate || '—'}</td>
                    <td className="px-3 py-3 text-slate-700">{r.trainee.organization || '—'}</td>
                    <td className="px-3 py-3 text-slate-700">{r.trainee.job_title || '—'}</td>
                    <td className="num px-3 py-3 text-slate-700" dir="ltr">{r.trainee.phone || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <Modal open={!!open} title={open?.trainee.full_name || ''} onClose={() => setOpen(null)} wide>
        {open && (
          <div className="space-y-4">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <dt className="text-slate-500">{t('Code', 'الكود')}</dt><dd className="num font-mono font-semibold text-brand-800">{open.trainee.badge_id}</dd>
              <dt className="text-slate-500">{t('Governorate', 'المحافظة')}</dt><dd>{open.trainee.governorate || '—'}</dd>
              <dt className="text-slate-500">{t('Organization', 'الجهة')}</dt><dd>{open.trainee.organization || '—'}</dd>
              <dt className="text-slate-500">{t('Job title', 'الوظيفة')}</dt><dd>{open.trainee.job_title || '—'}</dd>
              <dt className="text-slate-500">{t('Phone', 'رقم التليفون')}</dt><dd className="num" dir="ltr">{open.trainee.phone || '—'}</dd>
              <dt className="text-slate-500">{t('National ID', 'رقم البطاقة')}</dt><dd className="num" dir="ltr">{open.trainee.national_id || '—'}</dd>
              <dt className="text-slate-500">{t('Session', 'الجلسة')}</dt><dd>{open.session.title}</dd>
              <dt className="text-slate-500">{t('Trainer', 'المحاضر')}</dt><dd>{open.session.trainer_name || '—'}</dd>
              <dt className="text-slate-500">{t('Date', 'التاريخ')}</dt><dd>{fmtDay(open.session.day)}</dd>
            </dl>
            <div className="space-y-2">
              {open.answers.map((a, i) => (
                <div key={a.question_id} className="rounded-xl border border-slate-200 px-4 py-3">
                  <div className="text-sm font-medium text-slate-900"><span className="num me-2 text-brand-700">{i + 1}</span>{a.text}</div>
                  <div className="mt-1 text-sm text-slate-700">{answerLabel(a.type, a.value, arabic)}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

function Comments() {
  const { t } = useI18n()
  const [from, setFrom] = useState(addDays(todayLocal(), -30))
  const [to, setTo] = useState(todayLocal())
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['survey-comments', from, to], queryFn: () => api.get<SurveyReport>(`/reports/surveys?date_from=${from}&date_to=${to}`) })
  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label={t('From', 'من')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('To', 'إلى')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
      </div>
      {isLoading ? <Spinner /> : error || !data ? <ErrorBox error={error} onRetry={refetch} /> : data.comments.length === 0 ? (
        <Card><EmptyState title={t('No comments yet', 'لا توجد تعليقات بعد')} /></Card>
      ) : (
        <div className="space-y-3">
          {data.comments.map((c, i) => (
            <Card key={i}>
              <p className="text-slate-800">“{c.text}”</p>
              <p className="mt-2 text-xs text-slate-500">{c.session_title} · {fmtDay(c.day)}{c.trainer_name && ` · ${c.trainer_name}`} · <span className="num">{fmtDateTime(c.submitted_at)}</span></p>
            </Card>
          ))}
        </div>
      )}
    </>
  )
}

// ------------------------------------------------------------------ templates
interface TemplateDraft {
  id?: number
  name: string
  description: string
  is_anonymous: boolean
  is_default: boolean
  is_active: boolean
  questions: (Question & { key: string; optionsText: string })[]
}

const newQuestion = (): TemplateDraft['questions'][number] => ({ key: crypto.randomUUID?.() ?? String(Math.random()), text: '', type: 'rating', options: null, required: true, optionsText: '' })

function Templates() {
  const { t } = useI18n()
  const qc = useQueryClient()
  const toast = useToast()
  const [draft, setDraft] = useState<TemplateDraft | null>(null)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['templates'], queryFn: () => api.get<Template[]>('/survey-templates') })

  const save = useMutation({
    mutationFn: () => {
      const d = draft!
      const body = {
        name: d.name.trim(),
        description: d.description.trim() || null,
        is_anonymous: d.is_anonymous,
        is_default: d.is_default,
        is_active: d.is_active,
        questions: d.questions.map((q) => ({
          id: q.id ?? null,
          text: q.text.trim(),
          type: q.type,
          required: q.required,
          options: q.type === 'choice' ? q.optionsText.split('\n').map((o) => o.trim()).filter(Boolean) : null,
        })),
      }
      return d.id ? api.put(`/survey-templates/${d.id}`, body) : api.post('/survey-templates', body)
    },
    onSuccess: () => {
      toast.push('success', t('Template saved', 'تم حفظ القالب'))
      setDraft(null)
      void qc.invalidateQueries({ queryKey: ['templates'] })
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  function edit(tpl?: Template) {
    setDraft(
      tpl
        ? { id: tpl.id, name: tpl.name, description: tpl.description ?? '', is_anonymous: tpl.is_anonymous, is_default: tpl.is_default, is_active: tpl.is_active, questions: tpl.questions.map((q) => ({ ...q, key: String(q.id), optionsText: (q.options ?? []).join('\n') })) }
        : { name: '', description: '', is_anonymous: true, is_default: false, is_active: true, questions: [newQuestion()] },
    )
  }
  function move(i: number, d: -1 | 1) {
    setDraft((cur) => {
      if (!cur) return cur
      const qs = [...cur.questions]
      const j = i + d
      if (j < 0 || j >= qs.length) return cur
      ;[qs[i], qs[j]] = [qs[j], qs[i]]
      return { ...cur, questions: qs }
    })
  }
  const typeLabel = (x: string) => ({ rating: t('Rating 1–5', 'تقييم 1–5'), nps: t('Score 0–10', 'درجة 0–10'), choice: t('Choice', 'اختيار'), text: t('Free text', 'نص حر') })[x]

  return (
    <>
      {isLoading ? <Spinner /> : error ? <ErrorBox error={error} onRetry={refetch} /> : (
        <div className="grid gap-4 md:grid-cols-2">
          {data?.map((tpl) => (
            <Card key={tpl.id} title={<span className="flex items-center gap-2">{tpl.name}{tpl.is_default && <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs text-brand-700">{t('Default', 'افتراضي')}</span>}{!tpl.is_active && <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs">{t('Inactive', 'غير نشط')}</span>}</span>} actions={<Button size="sm" variant="ghost" onClick={() => edit(tpl)}><Pencil className="h-4 w-4" /></Button>}>
              <ol className="list-decimal space-y-1.5 ps-5 text-sm text-slate-700">
                {tpl.questions.map((q) => <li key={q.id}>{q.text} <span className="text-xs text-slate-400">· {typeLabel(q.type)}{!q.required && ` · ${t('optional', 'اختياري')}`}</span></li>)}
              </ol>
              <p className="mt-3 text-xs text-slate-500">{tpl.is_anonymous ? t('Anonymous responses', 'ردود مجهولة') : t('Responses show the trainee name', 'الردود تظهر اسم المتدرب')}</p>
            </Card>
          ))}
        </div>
      )}

      <Modal wide open={!!draft} title={draft?.id ? t('Edit template', 'تعديل القالب') : t('New template', 'قالب جديد')} onClose={() => setDraft(null)}
        footer={<><Button variant="secondary" onClick={() => setDraft(null)}>{t('Cancel', 'إلغاء')}</Button><Button onClick={() => save.mutate()} loading={save.isPending} disabled={!draft?.name.trim() || !draft.questions.length || draft.questions.some((q) => !q.text.trim())}>{t('Save', 'حفظ')}</Button></>}>
        {draft && (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t('Template name', 'اسم القالب')}><Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} autoFocus /></Field>
              <Field label={t('Description', 'الوصف')}><Input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></Field>
            </div>
            <div className="flex flex-wrap gap-5 text-sm">
              <label className="flex items-center gap-2"><input type="checkbox" checked={draft.is_anonymous} onChange={(e) => setDraft({ ...draft, is_anonymous: e.target.checked })} />{t('Anonymous', 'مجهول')}</label>
              <label className="flex items-center gap-2"><input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />{t('Active', 'نشط')}</label>
            </div>
            <div className="space-y-3">
              {draft.questions.map((q, i) => (
                <div key={q.key} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex flex-wrap items-start gap-2">
                    <span className="num mt-2 w-5 text-sm font-semibold text-slate-400">{i + 1}</span>
                    <div className="min-w-[200px] flex-1"><Input placeholder={t('Question text', 'نص السؤال')} value={q.text} onChange={(e) => setDraft({ ...draft, questions: draft.questions.map((x) => (x.key === q.key ? { ...x, text: e.target.value } : x)) })} /></div>
                    <Select className="!w-36" value={q.type} onChange={(e) => setDraft({ ...draft, questions: draft.questions.map((x) => (x.key === q.key ? { ...x, type: e.target.value as Question['type'] } : x)) })}>
                      <option value="rating">{typeLabel('rating')}</option><option value="nps">{typeLabel('nps')}</option><option value="choice">{typeLabel('choice')}</option><option value="text">{typeLabel('text')}</option>
                    </Select>
                    <div className="flex">
                      <Button size="sm" variant="ghost" onClick={() => move(i, -1)} disabled={i === 0}><ArrowUp className="h-4 w-4" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => move(i, 1)} disabled={i === draft.questions.length - 1}><ArrowDown className="h-4 w-4" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => setDraft({ ...draft, questions: draft.questions.filter((x) => x.key !== q.key) })}><Trash2 className="h-4 w-4 text-red-500" /></Button>
                    </div>
                  </div>
                  {q.type === 'choice' && <Textarea className="mt-2" rows={3} placeholder={t('One option per line', 'خيار واحد في كل سطر')} value={q.optionsText} onChange={(e) => setDraft({ ...draft, questions: draft.questions.map((x) => (x.key === q.key ? { ...x, optionsText: e.target.value } : x)) })} />}
                  <label className="mt-2 flex items-center gap-2 text-xs text-slate-600"><input type="checkbox" checked={q.required} onChange={(e) => setDraft({ ...draft, questions: draft.questions.map((x) => (x.key === q.key ? { ...x, required: e.target.checked } : x)) })} />{t('Required', 'إجباري')}</label>
                </div>
              ))}
              <Button variant="secondary" size="sm" onClick={() => setDraft({ ...draft, questions: [...draft.questions, newQuestion()] })}><Plus className="h-4 w-4" />{t('Add question', 'إضافة سؤال')}</Button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}

export default function Feedback() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [tab, setTab] = useState<Tab>('results')
  const tabs: { id: Tab; label: string }[] = [{ id: 'results', label: t('Results', 'النتائج') }]
  if (user?.role !== 'trainer') tabs.push({ id: 'people', label: t('Trainee report', 'تقرير المتدربين') })
  tabs.push({ id: 'comments', label: t('Comments', 'التعليقات') })
  if (user?.role === 'admin') tabs.push({ id: 'templates', label: t('Survey templates', 'قوالب الاستبيان') })
  return (
    <>
      <PageHeader title={t('Feedback', 'التقييمات')} subtitle={t('What trainees think of every session', 'رأي المتدربين في كل محاضرة')} />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={tabs} />
      {tab === 'results' && <Results />}
      {tab === 'people' && <Respondents />}
      {tab === 'comments' && <Comments />}
      {tab === 'templates' && <Templates />}
    </>
  )
}
