import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button, Card, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, Tabs, useToast, errMsg } from '../components/ui'
import { api } from '../lib/api'
import { fmtDateTime } from '../lib/format'
import { useI18n } from '../lib/i18n'
import type { AuditEntry, Role, Settings, Trainer, User } from '../lib/types'

type Tab = 'program' | 'users' | 'audit' | 'account'

function ProgramSettings() {
  const { t } = useI18n()
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['settings'], queryFn: () => api.get<Settings>('/settings') })
  const [form, setForm] = useState<Settings | null>(null)
  useEffect(() => { if (data) setForm(data) }, [data])

  const save = useMutation({
    mutationFn: () => api.put<Settings>('/settings', form),
    onSuccess: () => {
      toast.push('success', t('Settings saved', 'تم حفظ الإعدادات'))
      void qc.invalidateQueries({ queryKey: ['settings'] })
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  if (isLoading || !form) return error ? <ErrorBox error={error} onRetry={refetch} /> : <Spinner />
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setForm({ ...form, [k]: v })
  const days = [
    [6, t('Sun', 'الأحد')], [0, t('Mon', 'الإثنين')], [1, t('Tue', 'الثلاثاء')], [2, t('Wed', 'الأربعاء')], [3, t('Thu', 'الخميس')], [4, t('Fri', 'الجمعة')], [5, t('Sat', 'السبت')],
  ] as [number, string][]

  return (
    <div className="space-y-5">
      <Card title={t('Programme', 'البرنامج')}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label={t('Programme name (printed on badges)', 'اسم البرنامج (يُطبع على الباج)')} className="lg:col-span-3"><Input value={form.program_name} onChange={(e) => set('program_name', e.target.value)} /></Field>
          <Field label={t('Day starts', 'بداية اليوم')}><Input type="time" value={form.day_start_time} onChange={(e) => set('day_start_time', e.target.value)} /></Field>
          <Field label={t('Day ends', 'نهاية اليوم')}><Input type="time" value={form.day_end_time} onChange={(e) => set('day_end_time', e.target.value)} /></Field>
          <Field label={t('Late after (minutes)', 'التأخير بعد (دقائق)')} hint={t('After the day start', 'بعد بداية اليوم')}><Input type="number" min={0} value={form.late_after_minutes} onChange={(e) => set('late_after_minutes', Number(e.target.value))} /></Field>
          <Field label={t('Early leave before', 'انصراف مبكر قبل')}><Input type="time" value={form.checkout_from_time} onChange={(e) => set('checkout_from_time', e.target.value)} /></Field>
          <Field label={t('Double-scan guard (minutes)', 'حماية المسح المكرر (دقائق)')} hint={t('A second scan within this time is NOT treated as check-out', 'مسح ثانٍ خلال هذه المدة لا يُعتبر انصرافاً')}><Input type="number" min={0} value={form.min_checkout_gap_minutes} onChange={(e) => set('min_checkout_gap_minutes', Number(e.target.value))} /></Field>
        </div>
        <div className="mt-5">
          <div className="mb-2 text-sm font-medium text-slate-700">{t('Working days', 'أيام العمل')}</div>
          <div className="flex flex-wrap gap-2">
            {days.map(([n, label]) => {
              const on = form.working_weekdays.includes(n)
              return <button key={n} type="button" onClick={() => set('working_weekdays', on ? form.working_weekdays.filter((d) => d !== n) : [...form.working_weekdays, n])} className={`rounded-full border px-4 py-1.5 text-sm font-medium transition ${on ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white text-slate-600'}`}>{label}</button>
            })}
          </div>
        </div>
      </Card>

      <Card title={t('Surveys & alerts', 'الاستبيانات والتنبيهات')}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label={t('Programme name on the survey', 'اسم البرنامج في الاستبيان')} className="sm:col-span-2 lg:col-span-3"><Input value={form.survey_program_name} onChange={(e) => set('survey_program_name', e.target.value)} /></Field>
          <Field label={t('Survey opens (minutes before session ends)', 'يفتح الاستبيان (دقائق قبل نهاية المحاضرة)')}><Input type="number" min={0} value={form.survey_opens_minutes_before_end} onChange={(e) => set('survey_opens_minutes_before_end', Number(e.target.value))} /></Field>
          <Field label={t('Default survey duration (minutes)', 'مدة إتاحة الاستبيان الافتراضية (دقائق)')} hint={t('After this the survey closes by itself. Each session can override it, and you can re-open it.', 'بعدها يُغلق الاستبيان تلقائياً. يمكن تغييرها لكل محاضرة، ويمكنك إعادة فتحه.')}><Input type="number" min={1} value={form.survey_duration_minutes} onChange={(e) => set('survey_duration_minutes', Number(e.target.value))} /></Field>
          <Field label={t('Alert after N absences', 'تنبيه بعد عدد غيابات')}><Input type="number" min={0} value={form.absence_alert_threshold} onChange={(e) => set('absence_alert_threshold', Number(e.target.value))} /></Field>
          <Field label={t('Low rating threshold', 'حد التقييم المنخفض')}><Input type="number" step="0.1" min={1} max={5} value={form.low_rating_threshold} onChange={(e) => set('low_rating_threshold', Number(e.target.value))} /></Field>
          <label className="flex items-center gap-2 self-end pb-2 text-sm text-slate-700 lg:col-span-2"><input type="checkbox" checked={form.require_attendance_for_survey} onChange={(e) => set('require_attendance_for_survey', e.target.checked)} />{t('Only trainees who attended that day can rate its sessions', 'فقط من حضر في اليوم يمكنه تقييم محاضراته')}</label>
        </div>
      </Card>
      <div className="flex justify-end"><Button size="lg" onClick={() => save.mutate()} loading={save.isPending}>{t('Save settings', 'حفظ الإعدادات')}</Button></div>
    </div>
  )
}

function Users() {
  const { t } = useI18n()
  const toast = useToast()
  const qc = useQueryClient()
  const users = useQuery({ queryKey: ['users'], queryFn: () => api.get<User[]>('/users') })
  const trainers = useQuery({ queryKey: ['trainers'], queryFn: () => api.get<Trainer[]>('/trainers') })
  const [draft, setDraft] = useState<{ id?: number; username: string; full_name: string; role: Role; trainer_id: string; password: string; is_active: boolean } | null>(null)

  const save = useMutation({
    mutationFn: () => {
      const d = draft!
      if (d.id) {
        return api.patch(`/users/${d.id}`, { full_name: d.full_name, role: d.role, trainer_id: d.role === 'trainer' && d.trainer_id ? Number(d.trainer_id) : null, is_active: d.is_active, ...(d.password ? { password: d.password } : {}) })
      }
      return api.post('/users', { username: d.username, full_name: d.full_name, role: d.role, password: d.password, trainer_id: d.role === 'trainer' && d.trainer_id ? Number(d.trainer_id) : null })
    },
    onSuccess: () => {
      setDraft(null)
      void qc.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  return (
    <>
      <div className="mb-4 flex justify-end"><Button onClick={() => setDraft({ username: '', full_name: '', role: 'staff', trainer_id: '', password: '', is_active: true })}><Plus className="h-4 w-4" />{t('Add user', 'إضافة مستخدم')}</Button></div>
      {users.isLoading ? <Spinner /> : users.error ? <ErrorBox error={users.error} onRetry={users.refetch} /> : (
        <Card padded={false}>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr><th className="px-5 py-3 text-start">{t('User', 'المستخدم')}</th><th className="px-2 py-3 text-start">{t('Role', 'الدور')}</th><th className="hidden px-2 py-3 text-start md:table-cell">{t('Last sign-in', 'آخر دخول')}</th><th className="px-2 py-3 text-start">{t('Status', 'الحالة')}</th><th /></tr></thead>
            <tbody className="divide-y divide-slate-100">
              {users.data?.map((u) => (
                <tr key={u.id}>
                  <td className="px-5 py-2.5"><div className="font-medium">{u.full_name}</div><div className="text-xs text-slate-500">{u.username}</div></td>
                  <td className="px-2 capitalize">{u.role}</td>
                  <td className="num hidden px-2 text-xs text-slate-500 md:table-cell">{fmtDateTime(u.last_login_at)}</td>
                  <td className="px-2"><span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${u.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'}`}>{u.is_active ? t('Active', 'نشط') : t('Disabled', 'معطل')}</span></td>
                  <td className="px-5 text-end"><Button size="sm" variant="ghost" onClick={() => setDraft({ id: u.id, username: u.username, full_name: u.full_name, role: u.role, trainer_id: u.trainer_id?.toString() ?? '', password: '', is_active: u.is_active })}>{t('Edit', 'تعديل')}</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      <Modal open={!!draft} title={draft?.id ? t('Edit user', 'تعديل مستخدم') : t('Add user', 'إضافة مستخدم')} onClose={() => setDraft(null)}
        footer={<><Button variant="secondary" onClick={() => setDraft(null)}>{t('Cancel', 'إلغاء')}</Button><Button onClick={() => save.mutate()} loading={save.isPending} disabled={!draft?.full_name.trim() || (!draft.id && (draft.username.length < 3 || draft.password.length < 8)) || (draft.role === 'trainer' && !draft.trainer_id)}>{t('Save', 'حفظ')}</Button></>}>
        {draft && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t('Username', 'اسم المستخدم')}><Input value={draft.username} disabled={!!draft.id} onChange={(e) => setDraft({ ...draft, username: e.target.value })} /></Field>
            <Field label={t('Full name', 'الاسم الكامل')}><Input value={draft.full_name} onChange={(e) => setDraft({ ...draft, full_name: e.target.value })} /></Field>
            <Field label={t('Role', 'الدور')} hint={t('Staff run the gate; trainers only see their own feedback.', 'الموظف يدير البوابة؛ والمحاضر يرى تقييماته فقط.')}>
              <Select value={draft.role} onChange={(e) => setDraft({ ...draft, role: e.target.value as Role })}><option value="staff">Staff</option><option value="admin">Admin</option><option value="trainer">Trainer</option></Select>
            </Field>
            {draft.role === 'trainer' && (
              <Field label={t('Trainer profile', 'ملف المحاضر')}>
                <Select value={draft.trainer_id} onChange={(e) => setDraft({ ...draft, trainer_id: e.target.value })}><option value="">—</option>{trainers.data?.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</Select>
              </Field>
            )}
            <Field label={draft.id ? t('New password (optional)', 'كلمة مرور جديدة (اختياري)') : t('Password (min 8)', 'كلمة المرور (8 أحرف على الأقل)')}><Input type="password" autoComplete="new-password" value={draft.password} onChange={(e) => setDraft({ ...draft, password: e.target.value })} /></Field>
            {draft.id && <label className="flex items-center gap-2 self-end pb-2 text-sm"><input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />{t('Active', 'نشط')}</label>}
          </div>
        )}
      </Modal>
    </>
  )
}

function Audit() {
  const { t } = useI18n()
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ['audit'], queryFn: () => api.get<AuditEntry[]>('/audit-logs?limit=300') })
  if (isLoading) return <Spinner />
  if (error || !data) return <ErrorBox error={error} onRetry={refetch} />
  return (
    <Card padded={false} title={t('Audit log (latest 300)', 'سجل المراجعة (آخر 300)')}>
      <div className="max-h-[70vh] overflow-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-slate-50 uppercase text-slate-500"><tr><th className="px-4 py-2 text-start">{t('When', 'الوقت')}</th><th className="px-2 py-2 text-start">{t('Who', 'من')}</th><th className="px-2 py-2 text-start">{t('Action', 'الإجراء')}</th><th className="px-2 py-2 text-start">{t('Details', 'التفاصيل')}</th><th className="px-4 py-2 text-start">IP</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((a) => (
              <tr key={a.id}>
                <td className="num whitespace-nowrap px-4 py-2 text-slate-500">{fmtDateTime(a.at)}</td>
                <td className="px-2 py-2 font-medium">{a.username ?? '—'}</td>
                <td className="px-2 py-2 font-mono">{a.action}</td>
                <td className="max-w-[360px] truncate px-2 py-2 text-slate-500" title={JSON.stringify(a.details)}>{a.entity}{a.entity_id && ` #${a.entity_id}`} {a.details ? JSON.stringify(a.details) : ''}</td>
                <td className="num px-4 py-2 text-slate-400">{a.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function Account() {
  const { t } = useI18n()
  const toast = useToast()
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const change = useMutation({
    mutationFn: () => api.post('/auth/change-password', { current_password: cur, new_password: next }),
    onSuccess: () => {
      toast.push('success', t('Password changed', 'تم تغيير كلمة المرور'))
      setCur('')
      setNext('')
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })
  return (
    <Card title={<span className="flex items-center gap-2"><KeyRound className="h-4 w-4" />{t('Change my password', 'تغيير كلمة المرور')}</span>} className="max-w-md">
      <div className="space-y-4">
        <Field label={t('Current password', 'كلمة المرور الحالية')}><Input type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
        <Field label={t('New password (min 8)', 'كلمة المرور الجديدة (8 على الأقل)')}><Input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
        <Button onClick={() => change.mutate()} loading={change.isPending} disabled={!cur || next.length < 8}>{t('Change password', 'تغيير كلمة المرور')}</Button>
      </div>
    </Card>
  )
}

export default function SettingsPage() {
  const { t } = useI18n()
  const [tab, setTab] = useState<Tab>('program')
  return (
    <>
      <PageHeader title={t('Settings', 'الإعدادات')} />
      <Tabs<Tab> value={tab} onChange={setTab} tabs={[{ id: 'program', label: t('Programme', 'البرنامج') }, { id: 'users', label: t('Users', 'المستخدمون') }, { id: 'audit', label: t('Audit log', 'سجل المراجعة') }, { id: 'account', label: t('My account', 'حسابي') }]} />
      {tab === 'program' && <ProgramSettings />}
      {tab === 'users' && <Users />}
      {tab === 'audit' && <Audit />}
      {tab === 'account' && <Account />}
    </>
  )
}
