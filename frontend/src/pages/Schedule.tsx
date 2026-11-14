import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileSpreadsheet, Pencil, Plus, QrCode, Trash2, Upload } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import ExamEditor from '../components/ExamEditor'
import ExamPanel from '../components/ExamPanel'
import SurveyPanel from '../components/SurveyPanel'
import { Button, Card, EmptyState, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, StatusChip, Tabs, useConfirm, useToast, errMsg } from '../components/ui'
import { api, download } from '../lib/api'
import { useAuth } from '../lib/auth'
import { addDays, fmtDay, todayLocal } from '../lib/format'
import { useI18n } from '../lib/i18n'
import type { Session, Trainer } from '../lib/types'

type Tab = 'sessions' | 'trainers'

// ------------------------------------------------------------------ sessions
interface SessionDraft {
  id?: number
  day: string
  start_time: string
  end_time: string
  title: string
  trainer_id: string
  template_id: string
  axis: string
  untilEnd: boolean
  openMinutes: string
  requireAttendance: boolean
}

function draftFrom(s: Session): SessionDraft {
  return {
    id: s.id,
    day: s.day,
    start_time: s.start_time,
    end_time: s.end_time,
    title: s.title,
    trainer_id: s.trainer_id?.toString() ?? '',
    template_id: s.template_id?.toString() ?? '',
    axis: s.axis ?? '',
    untilEnd: s.survey_until_end_of_day,
    openMinutes: s.survey_until_end_of_day || s.survey_duration_minutes == null ? '' : String(s.survey_duration_minutes),
    requireAttendance: s.require_attendance,
  }
}

function SessionsTab({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const toast = useToast()
  const { confirm, dialog } = useConfirm()
  const [from, setFrom] = useState(addDays(todayLocal(), -1))
  const [to, setTo] = useState(addDays(todayLocal(), 30))
  const [draft, setDraft] = useState<SessionDraft | null>(null)
  const [panel, setPanel] = useState<Session | null>(null)
  const [exam, setExam] = useState<Session | null>(null)
  const [examEditor, setExamEditor] = useState<Session | null>(null)
  const [result, setResult] = useState<{ created: number; errors: { row: number; error: string }[] } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const sessions = useQuery({ queryKey: ['sessions', from, to], queryFn: () => api.get<Session[]>(`/sessions?date_from=${from}&date_to=${to}`) })
  const trainers = useQuery({ queryKey: ['trainers'], queryFn: () => api.get<Trainer[]>('/trainers') })
  const refresh = () => qc.invalidateQueries({ queryKey: ['sessions'] })

  const grouped = useMemo(() => {
    const m = new Map<string, Session[]>()
    for (const s of sessions.data ?? []) m.set(s.day, [...(m.get(s.day) ?? []), s])
    return [...m.entries()]
  }, [sessions.data])

  const save = useMutation({
    mutationFn: () => {
      if (!draft) throw new Error('no draft')
      const body = {
        day: draft.day,
        start_time: draft.start_time,
        end_time: draft.end_time,
        title: draft.title.trim(),
        trainer_id: draft.trainer_id ? Number(draft.trainer_id) : null,
        room: null,
        template_id: draft.template_id ? Number(draft.template_id) : null,
        axis: draft.axis.trim() || null,
        survey_until_end_of_day: draft.untilEnd,
        survey_duration_minutes: draft.untilEnd || !draft.openMinutes.trim() ? null : Number(draft.openMinutes),
        require_attendance: draft.requireAttendance,
      }
      return draft.id ? api.put(`/sessions/${draft.id}`, body) : api.post('/sessions', body)
    },
    onSuccess: () => {
      toast.push('success', t('Saved', 'تم الحفظ'))
      setDraft(null)
      void refresh()
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  const importFile = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.upload<{ created: number; errors: { row: number; error: string }[] }>('/sessions/import', form)
    },
    onSuccess: (r) => {
      setResult(r)
      void refresh()
      void qc.invalidateQueries({ queryKey: ['trainers'] })
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  async function remove(s: Session) {
    if (!(await confirm(t(`Delete "${s.title}"?`, `حذف "${s.title}"؟`)))) return
    try {
      await api.del(`/sessions/${s.id}`)
      void refresh()
    } catch (e) {
      toast.push('error', errMsg(e))
    }
  }

  const newDraft = (): SessionDraft => ({ day: todayLocal(), start_time: '09:30', end_time: '10:30', title: '', trainer_id: '', template_id: '', axis: '', untilEnd: false, openMinutes: '', requireAttendance: false })

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <Field label={t('From', 'من')}><Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label={t('To', 'إلى')}><Input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        {isAdmin && (
          <div className="ms-auto flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={() => download('/sessions/import-template.xlsx', 'sessions_template.xlsx')}><FileSpreadsheet className="h-4 w-4" />{t('Excel template', 'نموذج Excel')}</Button>
            <Button variant="secondary" onClick={() => fileRef.current?.click()} loading={importFile.isPending}><Upload className="h-4 w-4" />{t('Import Excel', 'استيراد Excel')}</Button>
            <Button onClick={() => setDraft(newDraft())}><Plus className="h-4 w-4" />{t('Add session', 'إضافة محاضرة')}</Button>
          </div>
        )}
      </div>
      <input ref={fileRef} type="file" accept=".xlsx,.csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile.mutate(f); e.target.value = '' }} />

      {sessions.isLoading ? <Spinner /> : sessions.error ? <ErrorBox error={sessions.error} onRetry={sessions.refetch} /> : grouped.length === 0 ? (
        <Card><EmptyState title={t('No sessions in this range', 'لا توجد محاضرات في هذه الفترة')} hint={t('Add sessions one by one, or import the whole programme from Excel.', 'أضف المحاضرات واحدة واحدة أو استورد البرنامج كاملاً من Excel.')} /></Card>
      ) : (
        <div className="space-y-4">
          {grouped.map(([day, items]) => (
            <Card key={day} title={fmtDay(day)} padded={false}>
              <div className="divide-y divide-slate-100">
                {items.map((s) => (
                  <div key={s.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                    <div className="num w-28 shrink-0 font-mono text-sm text-slate-600">{s.start_time}–{s.end_time}</div>
                    <div className="min-w-0 flex-1">
                      <div className={`font-medium ${s.is_cancelled ? 'text-slate-400 line-through' : 'text-slate-900'}`}>{s.title}</div>
                      <div className="text-xs text-slate-500">{s.trainer_name}</div>
                    </div>
                    <div className="num text-xs text-slate-500">{t(`${s.submissions} responses`, `${s.submissions} ردّ`)}</div>
                    <StatusChip status={s.survey_state} />
                    <Button size="sm" variant="secondary" onClick={() => setPanel(s)} title={t("Survey & QR code", "الاستبيان ورمز QR")}><QrCode className="h-4 w-4" />{t("Survey", "الاستبيان")}</Button>
                    {isAdmin && (
                      <Button size="sm" onClick={() => setExamEditor(s)}>
                        <Plus className="h-4 w-4" />
                        {s.exam_questions.length ? t('Edit exam', 'تعديل الامتحان') : t('Add exam', 'إضافة امتحان')}
                      </Button>
                    )}
                    {s.exam_questions.length > 0 && (
                      <Button size="sm" variant="secondary" onClick={() => setExam(s)} title={t("Exam & QR code", "الامتحان ورمز QR")}><QrCode className="h-4 w-4" />{t("Exam QR", "رمز الامتحان")}</Button>
                    )}
                    {isAdmin && (
                      <div className="flex gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setDraft(draftFrom(s))}><Pencil className="h-4 w-4" /></Button>
                        <Button size="sm" variant="ghost" onClick={() => remove(s)}><Trash2 className="h-4 w-4 text-red-500" /></Button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal open={!!draft} title={draft?.id ? t('Edit session', 'تعديل محاضرة') : t('Add session', 'إضافة محاضرة')} onClose={() => setDraft(null)}
        footer={<><Button variant="secondary" onClick={() => setDraft(null)}>{t('Cancel', 'إلغاء')}</Button><Button onClick={() => save.mutate()} loading={save.isPending} disabled={!draft?.title.trim()}>{t('Save', 'حفظ')}</Button></>}>
        {draft && (
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t('Session title', 'عنوان الجلسة')} className="sm:col-span-3"><Input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} autoFocus /></Field>
            <Field label={t('Training axis', 'المحور التدريبي')} className="sm:col-span-3"><Input value={draft.axis} onChange={(e) => setDraft({ ...draft, axis: e.target.value })} /></Field>
            <Field label={t('Date', 'التاريخ')}><Input type="date" value={draft.day} onChange={(e) => setDraft({ ...draft, day: e.target.value })} /></Field>
            <Field label={t('Start', 'البداية')}><Input type="time" value={draft.start_time} onChange={(e) => setDraft({ ...draft, start_time: e.target.value })} /></Field>
            <Field label={t('End', 'النهاية')}><Input type="time" value={draft.end_time} onChange={(e) => setDraft({ ...draft, end_time: e.target.value })} /></Field>
            <Field label={t('Trainer', 'المحاضر')} className="sm:col-span-2">
              <Select value={draft.trainer_id} onChange={(e) => setDraft({ ...draft, trainer_id: e.target.value })}>
                <option value="">—</option>
                {trainers.data?.filter((x) => x.is_active).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              </Select>
            </Field>
            <label className="flex items-center gap-2 self-end pb-2 text-sm text-slate-700 sm:col-span-3">
              <input
                type="checkbox"
                checked={draft.requireAttendance}
                onChange={(e) => setDraft({ ...draft, requireAttendance: e.target.checked })}
              />
              {t('Survey and exam only for trainees who checked in', 'الاستبيان والامتحان لمن سجّل حضوره فقط')}
            </label>
            <label className="flex items-center gap-2 self-end pb-2 text-sm text-slate-700 sm:col-span-3">
              <input
                type="checkbox"
                checked={draft.untilEnd}
                onChange={(e) => setDraft({ ...draft, untilEnd: e.target.checked, openMinutes: e.target.checked ? '' : draft.openMinutes })}
              />
              {t('Stay open until the end of the day', 'مفتوح لآخر اليوم')}
            </label>
            <Field label={t('Stays open for (minutes)', 'يفضل مفتوح (دقائق)')} hint={t('Choose either the end of the day or a number of minutes.', 'اختاري واحدة: إما لآخر اليوم أو عدد الدقائق.')} className="sm:col-span-3">
              <Input
                type="number"
                min={1}
                disabled={draft.untilEnd}
                value={draft.untilEnd ? '' : draft.openMinutes}
                onChange={(e) => setDraft({ ...draft, untilEnd: false, openMinutes: e.target.value })}
                placeholder={t('For example 30', 'مثال: 30')}
              />
            </Field>
          </div>
        )}
      </Modal>

      {panel && <SurveyPanel session={sessions.data?.find((x) => x.id === panel.id) ?? panel} onClose={() => setPanel(null)} onChanged={() => void refresh()} />}
      {exam && <ExamPanel session={sessions.data?.find((x) => x.id === exam.id) ?? exam} onClose={() => setExam(null)} onChanged={() => void refresh()} />}
      {examEditor && <ExamEditor session={sessions.data?.find((x) => x.id === examEditor.id) ?? examEditor} onClose={() => setExamEditor(null)} onSaved={() => void refresh()} />}

      <Modal open={!!result} title={t('Import finished', 'اكتمل الاستيراد')} onClose={() => setResult(null)} footer={<Button onClick={() => setResult(null)}>{t('Done', 'تم')}</Button>}>
        {result && (
          <div className="space-y-3 text-sm">
            <div className="text-2xl font-bold text-emerald-600">{result.created} <span className="text-sm font-normal text-slate-500">{t('sessions created', 'محاضرة تمت إضافتها')}</span></div>
            {result.errors.length > 0 && (
              <ul className="max-h-48 space-y-1 overflow-y-auto rounded-lg bg-slate-50 p-3 text-xs">
                {result.errors.map((e, i) => <li key={i}><b>{t('Row', 'صف')} {e.row}:</b> {e.error}</li>)}
              </ul>
            )}
          </div>
        )}
      </Modal>
      {dialog}
    </>
  )
}

// ------------------------------------------------------------------ trainers
function TrainersTab({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useI18n()
  const qc = useQueryClient()
  const toast = useToast()
  const [edit, setEdit] = useState<{ id?: number; name: string; is_active: boolean } | null>(null)
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['trainers'], queryFn: () => api.get<Trainer[]>('/trainers') })
  const save = useMutation({
    mutationFn: () => {
      const body = { name: edit!.name.trim(), email: null, is_active: edit!.is_active }
      return edit!.id ? api.put(`/trainers/${edit!.id}`, body) : api.post('/trainers', body)
    },
    onSuccess: () => {
      setEdit(null)
      void qc.invalidateQueries({ queryKey: ['trainers'] })
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })
  return (
    <>
      {isAdmin && <div className="mb-4 flex justify-end"><Button onClick={() => setEdit({ name: '', is_active: true })}><Plus className="h-4 w-4" />{t('Add trainer', 'إضافة محاضر')}</Button></div>}
      {isLoading ? <Spinner /> : error ? <ErrorBox error={error} onRetry={refetch} /> : !data?.length ? (
        <Card><EmptyState title={t('No trainers yet', 'لا يوجد محاضرون بعد')} /></Card>
      ) : (
        <Card padded={false}>
          <ul className="divide-y divide-slate-100">
            {data.map((x) => (
              <li key={x.id} className="flex items-center gap-3 px-5 py-3">
                <div className={`min-w-0 flex-1 font-medium ${x.is_active ? 'text-slate-900' : 'text-slate-400'}`}>{x.name}</div>
                {isAdmin && <Button size="sm" variant="ghost" onClick={() => setEdit({ id: x.id, name: x.name, is_active: x.is_active })}><Pencil className="h-4 w-4" /></Button>}
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Modal open={!!edit} title={edit?.id ? t('Edit trainer', 'تعديل محاضر') : t('Add trainer', 'إضافة محاضر')} onClose={() => setEdit(null)} footer={<><Button variant="secondary" onClick={() => setEdit(null)}>{t('Cancel', 'إلغاء')}</Button><Button onClick={() => save.mutate()} loading={save.isPending} disabled={!edit?.name.trim()}>{t('Save', 'حفظ')}</Button></>}>
        {edit && (
          <div className="space-y-4">
            <Field label={t('Name', 'الاسم')}><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} autoFocus /></Field>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />{t('Active', 'نشط')}</label>
          </div>
        )}
      </Modal>
    </>
  )
}

export default function Schedule() {
  const { t } = useI18n()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const raw = params.get('tab')
  const tab: Tab = raw === 'trainers' ? raw : 'sessions'
  const setTab = (id: Tab) => setParams(id === 'sessions' ? {} : { tab: id }, { replace: true })
  const isAdmin = user?.role === 'admin'
  return (
    <>
      <PageHeader title={t('Schedule', 'الجدول')} subtitle={t('Sessions and trainers', 'المحاضرات والمحاضرون')} />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: 'sessions', label: t('Sessions', 'المحاضرات') }, { id: 'trainers', label: t('Trainers', 'المحاضرون') }]} />
      {tab === 'sessions' && <SessionsTab isAdmin={isAdmin} />}
      {tab === 'trainers' && <TrainersTab isAdmin={isAdmin} />}
    </>
  )
}
