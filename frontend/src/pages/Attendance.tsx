import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ChevronLeft, ChevronRight, Download, Pencil, Search } from 'lucide-react'
import { useState } from 'react'
import { Avatar, Button, Card, EmptyState, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, StatusChip, Tabs, useToast, errMsg } from '../components/ui'
import { api, download } from '../lib/api'
import { useAuth } from '../lib/auth'
import { addDays, fmtDay, fmtHours, fmtTime, sourceLabel, todayLocal } from '../lib/format'
import { useI18n } from '../lib/i18n'
import type { AttendanceDayResponse, AttendanceReport, AttendanceRow } from '../lib/types'

type Tab = 'daily' | 'overview'

const cellColors: Record<string, string> = {
  present: 'bg-emerald-500',
  late: 'bg-amber-400',
  absent: 'bg-red-500',
  excused: 'bg-indigo-400',
  not_arrived: 'bg-slate-300',
  upcoming: 'bg-slate-100',
}

function Daily() {
  const { t } = useI18n()
  const toast = useToast()
  const qc = useQueryClient()
  const { user } = useAuth()
  const [day, setDay] = useState(todayLocal())
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState('all')
  const [edit, setEdit] = useState<AttendanceRow | null>(null)
  const [form, setForm] = useState({ check_in: '', check_out: '', excused: false, note: '' })

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['attendance-day', day],
    queryFn: () => api.get<AttendanceDayResponse>(`/attendance?day=${day}`),
    refetchInterval: day === todayLocal() ? 10000 : false,
  })

  const save = useMutation({
    mutationFn: () =>
      api.put(`/attendance/${edit!.trainee.id}/${day}`, {
        check_in_time: form.check_in || null,
        check_out_time: form.check_out || null,
        excused: form.excused,
        note: form.note.trim() || null,
      }),
    onSuccess: () => {
      toast.push('success', t('Attendance updated', 'تم تحديث الحضور'))
      setEdit(null)
      void qc.invalidateQueries({ queryKey: ['attendance-day'] })
      void qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  const clear = useMutation({
    mutationFn: () => api.del(`/attendance/${edit!.trainee.id}/${day}`),
    onSuccess: () => {
      setEdit(null)
      void qc.invalidateQueries({ queryKey: ['attendance-day'] })
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  function open(r: AttendanceRow) {
    setForm({ check_in: r.check_in_at ? fmtTime(r.check_in_at) : '', check_out: r.check_out_at ? fmtTime(r.check_out_at) : '', excused: r.excused, note: r.note ?? '' })
    setEdit(r)
  }

  const rows = (data?.rows ?? []).filter((r) => {
    if (filter !== 'all' && r.status !== filter && !(filter === 'incomplete' && r.incomplete)) return false
    if (!q.trim()) return true
    const s = q.toLowerCase()
    return r.trainee.full_name.toLowerCase().includes(s) || r.trainee.badge_id.toLowerCase().includes(s)
  })

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Button variant="secondary" size="sm" onClick={() => setDay(addDays(day, -1))}><ChevronLeft className="h-4 w-4 rtl:rotate-180" /></Button>
        <Input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} className="!w-40" />
        <Button variant="secondary" size="sm" onClick={() => setDay(addDays(day, 1))}><ChevronRight className="h-4 w-4 rtl:rotate-180" /></Button>
        <div className="relative min-w-[200px] flex-1">
          <Search className="pointer-events-none absolute start-3 top-2.5 h-4 w-4 text-slate-400" />
          <Input className="ps-9" placeholder={t('Search…', 'بحث…')} value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <Select value={filter} onChange={(e) => setFilter(e.target.value)} className="!w-44">
          <option value="all">{t('All statuses', 'كل الحالات')}</option>
          <option value="present">{t('Present', 'حاضر')}</option>
          <option value="late">{t('Late', 'متأخر')}</option>
          <option value="absent">{t('Absent', 'غائب')}</option>
          <option value="not_arrived">{t('Not arrived', 'لم يصل بعد')}</option>
          <option value="excused">{t('Excused', 'بعذر')}</option>
          <option value="incomplete">{t('Missing check-out', 'بدون انصراف')}</option>
        </Select>
      </div>

      {data && !data.training_day && <div className="mb-4 rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-700">{t('No training day on this date.', 'لا يوجد يوم تدريب في هذا التاريخ.')}</div>}

      {isLoading ? <Spinner /> : error ? <ErrorBox error={error} onRetry={refetch} /> : rows.length === 0 ? (
        <Card><EmptyState title={t('Nothing to show', 'لا توجد بيانات')} /></Card>
      ) : (
        <Card padded={false}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 text-start">{t('Trainee', 'المتدرب')}</th>
                  <th className="px-2 py-3 text-start">{t('Status', 'الحالة')}</th>
                  <th className="px-2 py-3 text-start">{t('Check-in', 'الحضور')}</th>
                  <th className="px-2 py-3 text-start">{t('Check-out', 'الانصراف')}</th>
                  <th className="hidden px-2 py-3 text-start md:table-cell">{t('Time in', 'المدة')}</th>
                  <th className="hidden px-2 py-3 text-start lg:table-cell">{t('Note', 'ملاحظة')}</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.trainee.id}>
                    <td className="px-5 py-2.5">
                      <div className="flex items-center gap-3">
                        <Avatar name={r.trainee.full_name} src={r.trainee.photo_url} size={32} />
                        <div>
                          <div className="font-medium text-slate-900">{r.trainee.full_name}</div>
                          <div className="num font-mono text-xs text-slate-500">{r.trainee.badge_id}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-2 py-2.5">
                      <div className="flex flex-wrap items-center gap-1">
                        <StatusChip status={r.status} />
                        {r.early_leave && <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-800">{t('Early', 'مبكر')}</span>}
                        {r.incomplete && <span className="rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-800">{t('No check-out', 'بدون انصراف')}</span>}
                      </div>
                    </td>
                    <td className="num px-2 py-2.5">{fmtTime(r.check_in_at)}{r.check_in_source && <span className="ms-1 text-[10px] uppercase text-slate-400">{sourceLabel(r.check_in_source)}</span>}</td>
                    <td className="num px-2 py-2.5">{fmtTime(r.check_out_at)}</td>
                    <td className="num hidden px-2 py-2.5 md:table-cell">{fmtHours(r.worked_minutes)}</td>
                    <td className="hidden max-w-[220px] truncate px-2 py-2.5 text-slate-500 lg:table-cell">{r.note}{r.is_manual && !r.note && <em className="text-xs">{t('manual entry', 'إدخال يدوي')}</em>}</td>
                    <td className="px-5 py-2.5 text-end"><Button size="sm" variant="ghost" onClick={() => open(r)} disabled={!data?.training_day}><Pencil className="h-4 w-4" /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Modal
        open={!!edit}
        title={edit ? `${edit.trainee.full_name} · ${fmtDay(day)}` : ''}
        onClose={() => setEdit(null)}
        footer={
          <>
            {user?.role === 'admin' && edit && (edit.check_in_at || edit.excused) && <Button variant="danger" className="me-auto" onClick={() => clear.mutate()} loading={clear.isPending}>{t('Clear record', 'مسح السجل')}</Button>}
            <Button variant="secondary" onClick={() => setEdit(null)}>{t('Cancel', 'إلغاء')}</Button>
            <Button onClick={() => save.mutate()} loading={save.isPending}>{t('Save', 'حفظ')}</Button>
          </>
        }
      >
        <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">{t('Manual changes are recorded in the audit log with your name.', 'يتم تسجيل التعديلات اليدوية في سجل المراجعة باسمك.')}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t('Check-in time', 'وقت الحضور')}><Input type="time" value={form.check_in} onChange={(e) => setForm({ ...form, check_in: e.target.value })} /></Field>
          <Field label={t('Check-out time', 'وقت الانصراف')}><Input type="time" value={form.check_out} onChange={(e) => setForm({ ...form, check_out: e.target.value })} /></Field>
          <label className="flex items-center gap-2 text-sm text-slate-700 sm:col-span-2"><input type="checkbox" checked={form.excused} onChange={(e) => setForm({ ...form, excused: e.target.checked })} />{t('Excused (does not count against attendance)', 'بعذر (لا يُحتسب ضد نسبة الحضور)')}</label>
          <Field label={t('Reason / note', 'السبب / ملاحظة')} className="sm:col-span-2"><Input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} maxLength={500} /></Field>
        </div>
      </Modal>
    </>
  )
}

function Overview() {
  const { t } = useI18n()
  const toast = useToast()
  const [from, setFrom] = useState(addDays(todayLocal(), -30))
  const [to, setTo] = useState(todayLocal())
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['attendance-report', from, to],
    queryFn: () => api.get<AttendanceReport>(`/reports/attendance?date_from=${from}&date_to=${to}`),
  })

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label={t('From', 'من')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('To', 'إلى')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Button variant="secondary" className="ms-auto" onClick={() => download(`/reports/attendance.xlsx?date_from=${from}&date_to=${to}`, `attendance_${from}_${to}.xlsx`).catch((e) => toast.push('error', errMsg(e)))}>
          <Download className="h-4 w-4" />{t('Export Excel', 'تصدير Excel')}
        </Button>
      </div>
      {isLoading ? <Spinner /> : error || !data ? <ErrorBox error={error} onRetry={refetch} /> : data.days.length === 0 ? (
        <Card><EmptyState title={t('No training days in this range', 'لا توجد أيام تدريب في هذه الفترة')} /></Card>
      ) : (
        <Card padded={false}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 text-start">{t('Trainee', 'المتدرب')}</th>
                  <th className="px-2 py-3 text-center">{t('Present', 'حاضر')}</th>
                  <th className="px-2 py-3 text-center">{t('Late', 'متأخر')}</th>
                  <th className="px-2 py-3 text-center">{t('Absent', 'غائب')}</th>
                  <th className="px-2 py-3 text-center">{t('Excused', 'بعذر')}</th>
                  <th className="px-2 py-3 text-start">{t('Attendance', 'نسبة الحضور')}</th>
                  <th className="hidden px-2 py-3 text-start xl:table-cell">{t('Timeline', 'الخط الزمني')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.trainees.map(({ trainee, summary, cells }) => {
                  const pct = summary.attendance_pct
                  return (
                    <tr key={trainee.id}>
                      <td className="px-5 py-2.5">
                        <div className="flex items-center gap-3">
                          <Avatar name={trainee.full_name} src={trainee.photo_url} size={32} />
                          <div><div className="font-medium text-slate-900">{trainee.full_name}</div><div className="num font-mono text-xs text-slate-500">{trainee.badge_id}</div></div>
                        </div>
                      </td>
                      <td className="px-2 text-center tabular-nums text-emerald-700">{summary.present}</td>
                      <td className="px-2 text-center tabular-nums text-amber-700">{summary.late}</td>
                      <td className="px-2 text-center font-semibold tabular-nums text-red-700">{summary.absent}</td>
                      <td className="px-2 text-center tabular-nums text-indigo-700">{summary.excused}</td>
                      <td className="px-2">
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-100">
                            <div className={clsx('h-full rounded-full', (pct ?? 100) >= 85 ? 'bg-emerald-500' : (pct ?? 100) >= 70 ? 'bg-amber-400' : 'bg-red-500')} style={{ width: `${pct ?? 0}%` }} />
                          </div>
                          <span className="num w-12 text-xs font-medium text-slate-700">{pct == null ? '—' : `${pct}%`}</span>
                        </div>
                      </td>
                      <td className="hidden px-2 xl:table-cell">
                        <div className="flex flex-wrap gap-[3px]">
                          {cells.map((c) => <span key={c.date} title={`${c.date}: ${c.status}`} className={clsx('h-3 w-3 rounded-sm', cellColors[c.status] ?? 'bg-slate-100')} />)}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <p className="mt-3 text-xs text-slate-500">{t('Attendance % = (present + late) ÷ (present + late + absent). Excused days are not counted for or against.', 'نسبة الحضور = (حاضر + متأخر) ÷ (حاضر + متأخر + غائب). الأيام بعذر لا تُحتسب.')}</p>
    </>
  )
}

export default function Attendance() {
  const { t } = useI18n()
  const [tab, setTab] = useState<Tab>('daily')
  return (
    <>
      <PageHeader title={t('Attendance', 'الحضور')} subtitle={t('Check-in and check-out, once per day', 'الحضور والانصراف مرة واحدة يومياً')} />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: 'daily', label: t('Daily', 'يومي') }, { id: 'overview', label: t('Overview', 'ملخص') }]} />
      {tab === 'daily' ? <Daily /> : <Overview />}
    </>
  )
}

