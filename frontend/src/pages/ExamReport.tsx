import { useQuery } from '@tanstack/react-query'
import { Fragment } from 'react'
import { Download } from 'lucide-react'
import { useState } from 'react'
import { Button, Card, EmptyState, ErrorBox, Field, Input, PageHeader, Select, Spinner, useToast, errMsg } from '../components/ui'
import { api, download } from '../lib/api'
import { addDays, fmtDay, todayLocal } from '../lib/format'
import { useI18n } from '../lib/i18n'
import type { Session } from '../lib/types'

export type ExamPart = 'before' | 'after' | 'compare'

type Sitting = { answers: (boolean | null)[]; score: number } | null
type Report = {
  title: string
  day: string
  questions: string[]
  total: number
  rows: { badge_id: string; full_name: string; before: Sitting; after: Sitting }[]
}

function Answer({ value }: { value: boolean | null | undefined }) {
  if (value == null) return <span className="inline-flex min-w-14 justify-center rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-400">—</span>
  return value
    ? <span className="inline-flex min-w-14 justify-center rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-bold text-emerald-800">صح</span>
    : <span className="inline-flex min-w-14 justify-center rounded-full bg-red-100 px-2.5 py-1 text-xs font-bold text-red-800">غلط</span>
}

export default function ExamReport({ part }: { part: ExamPart }) {
  const { t } = useI18n()
  const toast = useToast()
  const [from, setFrom] = useState(addDays(todayLocal(), -14))
  const [to, setTo] = useState(addDays(todayLocal(), 14))
  const [sessionId, setSessionId] = useState<number | null>(null)

  const sessions = useQuery({
    queryKey: ['sessions', from, to],
    queryFn: () => api.get<Session[]>(`/sessions?date_from=${from}&date_to=${to}`),
  })
  const exams = (sessions.data ?? []).filter((s) => s.exam_questions.length > 0)
  const chosen = exams.find((s) => s.id === sessionId) ?? exams[0] ?? null

  const report = useQuery({
    queryKey: ['exam-report', chosen?.id],
    queryFn: () => api.get<Report>(`/sessions/${chosen!.id}/exam-report`),
    enabled: chosen != null,
  })

  const title = part === 'before'
    ? t('Exam before the lecture', 'امتحان قبل المحاضرة')
    : part === 'after'
      ? t('Exam after the lecture', 'امتحان بعد المحاضرة')
      : t('Exam comparison', 'مقارنة الامتحان')
  const file = part === 'before' ? 'امتحان_قبل_المحاضرة' : part === 'after' ? 'امتحان_بعد_المحاضرة' : 'امتحان_المقارنة'

  return (
    <>
      <PageHeader title={title} subtitle={t('Results of the true / false exam', 'نتائج امتحان صح أو غلط')} />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label={t('From', 'من')}><Input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setSessionId(null) }} /></Field>
        <Field label={t('To', 'إلى')}><Input type="date" value={to} onChange={(e) => { setTo(e.target.value); setSessionId(null) }} /></Field>
        <Field label={t('Lecture', 'المحاضرة')}>
          <Select className="!w-64" value={chosen ? String(chosen.id) : ''} onChange={(e) => setSessionId(Number(e.target.value))}>
            {exams.length === 0 && <option value="">{t('No exam in this range', 'لا يوجد امتحان في هذه الفترة')}</option>}
            {exams.map((s) => <option key={s.id} value={s.id}>{fmtDay(s.day)} · {s.title}</option>)}
          </Select>
        </Field>
        <Button
          variant="secondary"
          className="ms-auto"
          disabled={!chosen}
          onClick={() => chosen && download(`/sessions/${chosen.id}/exam.xlsx?part=${part}`, `${file}_${chosen.id}.xlsx`).catch((e) => toast.push('error', errMsg(e)))}
        >
          <Download className="h-4 w-4" />{t('Export Excel', 'تصدير Excel')}
        </Button>
      </div>

      {sessions.isLoading || report.isLoading ? <Spinner /> : sessions.error ? <ErrorBox error={sessions.error} onRetry={sessions.refetch} /> : !chosen ? (
        <Card><EmptyState title={t('No exam in this range', 'لا يوجد امتحان في هذه الفترة')} hint={t('Add exam questions to a lecture first.', 'أضيفي أسئلة الامتحان للمحاضرة أولاً.')} /></Card>
      ) : report.error || !report.data ? <ErrorBox error={report.error} onRetry={report.refetch} /> : report.data.rows.length === 0 ? (
        <Card><EmptyState title={t('No one has sat this exam yet', 'لم يمتحن أحد بعد')} /></Card>
      ) : part === 'compare' ? (
        <CompareTable report={report.data} />
      ) : (
        <SittingTable report={report.data} phase={part} />
      )}
    </>
  )
}

function SittingTable({ report, phase }: { report: Report; phase: 'before' | 'after' }) {
  const { t } = useI18n()
  const answers = report.rows.flatMap((row) => row[phase]?.answers ?? [])
  const yes = answers.filter((v) => v === true).length
  const no = answers.filter((v) => v === false).length
  const missing = report.rows.filter((row) => !row[phase]).length
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Summary label={t('Trainees', 'المتدربون')} value={report.rows.length} tone="bg-brand-800 text-white" />
        <Summary label={t('True', 'صح')} value={yes} tone="bg-emerald-600 text-white" />
        <Summary label={t('False', 'غلط')} value={no} tone="bg-red-600 text-white" />
        <Summary label={t('Did not sit', 'لم يمتحن')} value={missing} tone="bg-slate-200 text-slate-700" />
      </div>
      <Card padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
            <thead className="sticky top-0 z-10 text-xs text-white">
              <tr className="bg-brand-800">
                <th className="sticky start-0 z-20 bg-brand-800 px-4 py-3 text-start font-semibold">{t('Code', 'الكود')}</th>
                <th className="sticky start-24 z-20 bg-brand-800 px-4 py-3 text-start font-semibold">{t('Name', 'الاسم')}</th>
                {report.questions.map((q, i) => (
                  <th key={i} className="min-w-36 px-3 py-3 text-start font-semibold" title={q}>
                    <span className="me-1 inline-flex h-5 w-5 items-center justify-center rounded-full bg-white/15 text-[11px]">{i + 1}</span>
                    <span className="line-clamp-2 align-middle leading-snug">{q}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row, n) => {
                const given = row[phase]?.answers ?? []
                const stripe = n % 2 === 0 ? 'bg-white' : 'bg-brand-50/60'
                return (
                  <tr key={row.badge_id} className={stripe}>
                    <td className={`num sticky start-0 px-4 py-3 font-mono font-semibold text-brand-800 ${stripe}`}>{row.badge_id}</td>
                    <td className={`sticky start-24 px-4 py-3 font-medium text-slate-900 ${stripe}`}>{row.full_name}</td>
                    {report.questions.map((_, i) => <td key={i} className="px-3 py-3 text-center"><Answer value={given[i]} /></td>)}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function Summary({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`rounded-2xl px-4 py-3 shadow-sm ${tone}`}>
      <div className="text-2xl font-bold leading-none">{value}</div>
      <div className="mt-1 text-xs font-semibold opacity-90">{label}</div>
    </div>
  )
}

function CompareTable({ report }: { report: Report }) {
  const { t } = useI18n()
  let changed = 0
  let same = 0
  for (const row of report.rows) {
    report.questions.forEach((_, i) => {
      const left = row.before?.answers[i]
      const right = row.after?.answers[i]
      if (left == null || right == null) return
      if (left === right) same += 1
      else changed += 1
    })
  }
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-xs font-semibold">
        <span className="rounded-full bg-emerald-100 px-3 py-1 text-emerald-800">{t('True', 'صح')}</span>
        <span className="rounded-full bg-red-100 px-3 py-1 text-red-800">{t('False', 'غلط')}</span>
        <span className="rounded-full bg-amber-100 px-3 py-1 text-amber-900">{t('Answer changed', 'الإجابة اختلفت')}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Summary label={t('Trainees', 'المتدربون')} value={report.rows.length} tone="bg-brand-800 text-white" />
        <Summary label={t('Same answer', 'نفس الإجابة')} value={same} tone="bg-emerald-600 text-white" />
        <Summary label={t('Changed', 'اختلفت')} value={changed} tone="bg-amber-500 text-white" />
        <Summary label={t('Questions', 'الأسئلة')} value={report.questions.length} tone="bg-slate-200 text-slate-700" />
      </div>
      <Card padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-separate border-spacing-0 text-sm">
            <thead className="sticky top-0 z-10 text-xs">
              <tr className="bg-brand-800 text-white">
                <th className="sticky start-0 z-20 bg-brand-800 px-4 py-3 text-start font-semibold" rowSpan={2}>{t('Code', 'الكود')}</th>
                <th className="sticky start-24 z-20 bg-brand-800 px-4 py-3 text-start font-semibold" rowSpan={2}>{t('Name', 'الاسم')}</th>
                {report.questions.map((q, i) => (
                  <th key={i} className="border-s border-white/15 px-3 py-3 text-center font-semibold" colSpan={2} title={q}>
                    <span className="me-1 inline-flex h-5 w-5 items-center justify-center rounded-full bg-white/15 text-[11px]">{i + 1}</span>
                    <span className="line-clamp-2 align-middle leading-snug">{q}</span>
                  </th>
                ))}
                <th className="px-4 py-3 text-center font-semibold" rowSpan={2}>{t('Differences', 'الاختلافات')}</th>
              </tr>
              <tr className="bg-brand-700 text-white">
                {report.questions.map((_, i) => (
                  <Fragment key={i}>
                    <th className="border-s border-white/10 px-3 py-2 text-center font-medium text-emerald-100">{t('Before', 'قبل')}</th>
                    <th className="px-3 py-2 text-center font-medium text-amber-100">{t('After', 'بعد')}</th>
                  </Fragment>
                ))}
              </tr>
            </thead>
            <tbody>
              {report.rows.map((row, n) => {
                let different = 0
                let comparable = false
                const cells = report.questions.map((_, i) => {
                  const left = row.before?.answers[i]
                  const right = row.after?.answers[i]
                  const diff = left != null && right != null && left !== right
                  if (left != null && right != null) {
                    comparable = true
                    if (diff) different += 1
                  }
                  return { left, right, diff }
                })
                const stripe = n % 2 === 0 ? 'bg-white' : 'bg-slate-50'
                return (
                  <tr key={row.badge_id}>
                    <td className={`num sticky start-0 px-4 py-3 font-mono font-semibold text-brand-800 ${stripe}`}>{row.badge_id}</td>
                    <td className={`sticky start-24 px-4 py-3 font-medium text-slate-900 ${stripe}`}>{row.full_name}</td>
                    {cells.map((cell, i) => (
                      <Fragment key={i}>
                        <td className={`border-s border-slate-100 px-2 py-3 text-center ${cell.diff ? 'bg-amber-50' : stripe}`}><Answer value={cell.left} /></td>
                        <td className={`px-2 py-3 text-center ${cell.diff ? 'bg-amber-50' : stripe}`}><Answer value={cell.right} /></td>
                      </Fragment>
                    ))}
                    <td className="px-4 py-3 text-center">
                      {comparable
                        ? <span className={`inline-flex h-8 min-w-8 items-center justify-center rounded-full px-2 text-sm font-bold ${different ? 'bg-amber-100 text-amber-900' : 'bg-emerald-100 text-emerald-800'}`}>{different}</span>
                        : <span className="text-slate-300">—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
