import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, Download, FileSpreadsheet, Pencil, Plus, Printer, Search, Trash2, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Avatar, Button, Card, EmptyState, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, useConfirm, useToast, errMsg } from '../components/ui'
import { api, download, fetchBlobUrl } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { isTripleName } from '../lib/name'
import type { Trainee } from '../lib/types'

interface GovernorateOption {
  name: string
  letter: string
}

interface Draft {
  full_name: string
  governorate: string
  job_title: string
  national_id: string
  phone: string
  organization: string
}
const emptyDraft: Draft = { full_name: '', governorate: '', job_title: '', national_id: '', phone: '', organization: '' }

function digitsOnly(value: string, max: number) {
  const mapped = value.replace(/[٠-٩۰-۹]/g, (ch) => String('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹'.indexOf(ch) % 10))
  return mapped.replace(/\D/g, '').slice(0, max)
}

export default function Trainees() {
  const { t } = useI18n()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const qc = useQueryClient()
  const toast = useToast()
  const { confirm, dialog } = useConfirm()
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState<Trainee | 'new' | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [issued, setIssued] = useState<Trainee | null>(null)
  const [importResult, setImportResult] = useState<{ created: number; skipped: number; errors: { row: number; error: string }[] } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const photoRef = useRef<HTMLInputElement>(null)
  const [photoFor, setPhotoFor] = useState<number | null>(null)

  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['trainees'],
    queryFn: () => api.get<Trainee[]>('/trainees'),
  })
  const { data: governorates = [] } = useQuery({
    queryKey: ['governorates'],
    queryFn: () => api.get<GovernorateOption[]>('/trainees/governorates'),
  })
  const [qrUrl, setQrUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!issued) return
    let url: string | null = null
    let cancelled = false
    setQrUrl(null)
    fetchBlobUrl(`/trainees/${issued.id}/qr.svg`)
      .then((u) => {
        url = u
        if (!cancelled) setQrUrl(u)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [issued])

  const filtered = (data ?? []).filter((x) => {
    if (!q.trim()) return true
    const s = q.trim().toLowerCase()
    return [x.full_name, x.badge_id, x.governorate, x.job_title, x.organization, x.national_id, x.phone].some((v) => (v ?? '').toLowerCase().includes(s))
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['trainees'] })

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        full_name: draft.full_name.trim(),
        governorate: draft.governorate.trim() || null,
        job_title: draft.job_title.trim() || null,
        national_id: draft.national_id,
        phone: draft.phone,
        organization: draft.organization.trim() || null,
      }
      const creating = editing === 'new'
      const saved = creating ? await api.post<Trainee>('/trainees', body) : await api.patch<Trainee>(`/trainees/${(editing as Trainee).id}`, body)
      return { saved, creating }
    },
    onSuccess: ({ saved, creating }) => {
      toast.push('success', creating ? t('Trainee added', 'تمت إضافة المتدرب') : t('Saved', 'تم الحفظ'))
      setEditing(null)
      if (creating) setIssued(saved)
      void refresh()
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  const importFile = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.upload<{ created: number; skipped: number; errors: { row: number; error: string }[] }>('/trainees/import', form)
    },
    onSuccess: (r) => {
      setImportResult(r)
      void refresh()
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  const uploadPhoto = useMutation({
    mutationFn: async ({ id, file }: { id: number; file: File }) => {
      const form = new FormData()
      form.append('file', file)
      return api.upload<Trainee>(`/trainees/${id}/photo`, form)
    },
    onSuccess: () => {
      toast.push('success', t('Photo updated', 'تم تحديث الصورة'))
      void refresh()
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  async function toggleActive(x: Trainee) {
    try {
      await api.patch(`/trainees/${x.id}`, { is_active: !x.is_active })
      void refresh()
    } catch (e) {
      toast.push('error', errMsg(e))
    }
  }

  async function remove(x: Trainee) {
    if (!(await confirm(t(`Delete ${x.full_name}? This cannot be undone.`, `حذف ${x.full_name}؟ لا يمكن التراجع.`)))) return
    try {
      await api.del(`/trainees/${x.id}`)
      void refresh()
    } catch (e) {
      toast.push('error', errMsg(e))
    }
  }

  async function printBadges(ids?: number[]) {
    try {
      await download(`/trainees/badges.pdf${ids?.length ? `?ids=${ids.join(',')}` : ''}`, 'badges.pdf', true)
    } catch (e) {
      toast.push('error', errMsg(e))
    }
  }

  function openEdit(x: Trainee | 'new') {
    setDraft(
      x === 'new'
        ? emptyDraft
        : {
            full_name: x.full_name,
            governorate: x.governorate ?? '',
            job_title: x.job_title ?? '',
            national_id: x.national_id ?? '',
            phone: x.phone ?? '',
            organization: x.organization ?? '',
          },
    )
    setEditing(x)
  }

  const allSelected = filtered.length > 0 && filtered.every((x) => selected.has(x.id))

  return (
    <>
      <PageHeader
        title={t('Trainees', 'المتدربون')}
        subtitle={t(`${data?.length ?? 0} registered`, `${data?.length ?? 0} مسجل`)}
        actions={
          <>
            <Button variant="secondary" onClick={() => printBadges(selected.size ? [...selected] : undefined)}>
              <Printer className="h-4 w-4" />
              {selected.size ? t(`Print ${selected.size} codes`, `طباعة ${selected.size} كود`) : t('Print all codes', 'طباعة كل الأكواد')}
            </Button>
            {isAdmin && (
              <>
                <Button variant="secondary" onClick={() => fileRef.current?.click()} loading={importFile.isPending}>
                  <Upload className="h-4 w-4" />
                  {t('Import Excel', 'استيراد Excel')}
                </Button>
                <Button onClick={() => openEdit('new')}>
                  <Plus className="h-4 w-4" />
                  {t('Add trainee', 'إضافة متدرب')}
                </Button>
              </>
            )}
          </>
        }
      />
      <input ref={fileRef} type="file" accept=".xlsx,.csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importFile.mutate(f); e.target.value = '' }} />
      <input ref={photoRef} type="file" accept="image/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f && photoFor) uploadPhoto.mutate({ id: photoFor, file: f }); e.target.value = '' }} />

      <Card padded={false}>
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-4">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute start-3 top-2.5 h-4 w-4 text-slate-400" />
            <Input className="ps-9" placeholder={t('Search name, code, governorate, ID or phone…', 'ابحث بالاسم أو الكود أو المحافظة أو البطاقة أو التليفون…')} value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          {isAdmin && (
            <Button variant="ghost" size="sm" onClick={() => download('/trainees/import-template.xlsx', 'trainees_template.xlsx')}>
              <FileSpreadsheet className="h-4 w-4" />
              {t('Excel template', 'نموذج Excel')}
            </Button>
          )}
        </div>

        {isLoading ? (
          <Spinner />
        ) : error ? (
          <div className="p-4"><ErrorBox error={error} onRetry={refetch} /></div>
        ) : filtered.length === 0 ? (
          <EmptyState title={t('No trainees yet', 'لا يوجد متدربون بعد')} hint={t('Add trainees one by one or import an Excel sheet. Each one gets a code from their governorate and a QR of that same code.', 'أضف المتدربين واحداً واحداً أو استورد ملف Excel. كل متدرب يأخذ كوداً من محافظته ورمز QR يحمل نفس الكود.')} />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="w-10 px-4 py-3 text-start">
                    <input type="checkbox" checked={allSelected} onChange={() => setSelected(allSelected ? new Set() : new Set(filtered.map((x) => x.id)))} aria-label={t('Select all', 'تحديد الكل')} />
                  </th>
                  <th className="px-2 py-3 text-start">{t('Trainee', 'المتدرب')}</th>
                  <th className="px-2 py-3 text-start">{t('Code', 'الكود')}</th>
                  <th className="hidden px-2 py-3 text-start md:table-cell">{t('Governorate', 'المحافظة')}</th>
                  <th className="hidden px-2 py-3 text-start lg:table-cell">{t('Organization', 'الجهة')}</th>
                  <th className="hidden px-2 py-3 text-start lg:table-cell">{t('Job', 'الوظيفة')}</th>
                  <th className="hidden px-2 py-3 text-start xl:table-cell">{t('Phone', 'التليفون')}</th>
                  <th className="hidden px-2 py-3 text-start xl:table-cell">{t('National ID', 'رقم البطاقة')}</th>
                  <th className="px-2 py-3 text-start">{t('Status', 'الحالة')}</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((x) => (
                  <tr key={x.id} className={x.is_active ? '' : 'bg-slate-50 text-slate-400'}>
                    <td className="px-4 py-2.5">
                      <input type="checkbox" checked={selected.has(x.id)} onChange={() => setSelected((s) => { const n = new Set(s); if (n.has(x.id)) n.delete(x.id); else n.add(x.id); return n })} aria-label={`${t('Select', 'تحديد')} ${x.full_name}`} />
                    </td>
                    <td className="px-2 py-2.5">
                      <div className="flex items-center gap-3">
                        <Avatar name={x.full_name} src={x.photo_url} />
                        <div className="min-w-0">
                          <div className="truncate font-medium text-slate-900">{x.full_name}</div>
                          <div className="truncate text-xs text-slate-500 md:hidden">{[x.governorate, x.organization, x.phone].filter(Boolean).join(' · ')}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-2 py-2.5">
                      <button
                        type="button"
                        className="num font-mono font-semibold text-brand-700 underline-offset-2 hover:underline"
                        title={t('Show code and QR', 'عرض الكود ورمز QR')}
                        onClick={() => setIssued(x)}
                      >
                        {x.badge_id}
                      </button>
                    </td>
                    <td className="hidden px-2 py-2.5 md:table-cell">{x.governorate ?? '—'}</td>
                    <td className="hidden max-w-[10rem] truncate px-2 py-2.5 lg:table-cell">{x.organization ?? '—'}</td>
                    <td className="hidden max-w-[10rem] truncate px-2 py-2.5 lg:table-cell">{x.job_title ?? '—'}</td>
                    <td className="num hidden px-2 py-2.5 font-mono xl:table-cell" dir="ltr">{x.phone ?? '—'}</td>
                    <td className="num hidden px-2 py-2.5 font-mono xl:table-cell" dir="ltr">{x.national_id ?? '—'}</td>
                    <td className="px-2 py-2.5">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${x.is_active ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'}`}>
                        {x.is_active ? t('Active', 'نشط') : t('Inactive', 'غير نشط')}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" title={t('Print code', 'طباعة الكود')} onClick={() => printBadges([x.id])}><Download className="h-4 w-4" /></Button>
                        {isAdmin && (
                          <>
                            <Button size="sm" variant="ghost" title={t('Photo', 'الصورة')} onClick={() => { setPhotoFor(x.id); photoRef.current?.click() }}><Camera className="h-4 w-4" /></Button>
                            <Button size="sm" variant="ghost" title={t('Edit', 'تعديل')} onClick={() => openEdit(x)}><Pencil className="h-4 w-4" /></Button>
                            <Button size="sm" variant="ghost" onClick={() => toggleActive(x)}>{x.is_active ? t('Deactivate', 'إيقاف') : t('Activate', 'تفعيل')}</Button>
                            <Button size="sm" variant="ghost" title={t('Delete', 'حذف')} onClick={() => remove(x)}><Trash2 className="h-4 w-4 text-red-500" /></Button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal
        open={!!editing}
        title={editing === 'new' ? t('Add trainee', 'إضافة متدرب') : t('Edit trainee', 'تعديل متدرب')}
        onClose={() => setEditing(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditing(null)}>{t('Cancel', 'إلغاء')}</Button>
            <Button
              onClick={() => save.mutate()}
              loading={save.isPending}
              disabled={!isTripleName(draft.full_name) || (editing === 'new' && !draft.governorate) || draft.national_id.length !== 14 || draft.phone.length !== 11 || !draft.organization.trim()}
            >
              {t('Save', 'حفظ')}
            </Button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="الاسم الكامل" hint={t('Three names: first, father and grandfather. Example: Mohamed Ahmed Ali', 'الاسم ثلاثي: الاسم واسم الأب واسم الجد. مثال: محمد أحمد علي')} className="sm:col-span-2"><Input value={draft.full_name} onChange={(e) => setDraft({ ...draft, full_name: e.target.value })} autoFocus /></Field>
          <Field label="المحافظة" hint={editing === 'new' ? 'الكود يبدأ بحرف المحافظة ثم رقمين، مثل C01' : undefined}>
            <Select value={draft.governorate} onChange={(e) => setDraft({ ...draft, governorate: e.target.value })}>
              <option value="">{t('Choose governorate', 'اختر المحافظة')}</option>
              {governorates.map((g) => (
                <option key={g.name} value={g.name}>{g.name} — {g.letter}</option>
              ))}
              {draft.governorate && !governorates.some((g) => g.name === draft.governorate) && (
                <option value={draft.governorate}>{draft.governorate}</option>
              )}
            </Select>
          </Field>
          <Field label="الوظيفة"><Input value={draft.job_title} onChange={(e) => setDraft({ ...draft, job_title: e.target.value })} /></Field>
          <Field label="رقم البطاقة" hint={`${draft.national_id.length}/14`}>
            <Input inputMode="numeric" dir="ltr" maxLength={14} value={draft.national_id} onChange={(e) => setDraft({ ...draft, national_id: digitsOnly(e.target.value, 14) })} placeholder="14 رقماً" />
          </Field>
          <Field label="رقم التليفون" hint={`${draft.phone.length}/11`}>
            <Input inputMode="numeric" dir="ltr" maxLength={11} value={draft.phone} onChange={(e) => setDraft({ ...draft, phone: digitsOnly(e.target.value, 11) })} placeholder="11 رقماً" />
          </Field>
          <Field label="الجهة" className="sm:col-span-2"><Input value={draft.organization} onChange={(e) => setDraft({ ...draft, organization: e.target.value })} /></Field>
        </div>
        {editing === 'new' && (
          <p className="mt-4 text-xs text-slate-500">
            {draft.governorate
              ? `هيبدأ الكود بالحرف ${governorates.find((g) => g.name === draft.governorate)?.letter ?? ''}، ومعاه رمز QR فيه نفس الكود.`
              : 'اختَر المحافظة عشان يتحدد حرف الكود، وبعد الحفظ يظهر الكود ورمز QR.'}
          </p>
        )}
      </Modal>

      <Modal open={!!issued} title="الكود ورمز QR" onClose={() => setIssued(null)} footer={
        <>
          <Button variant="secondary" onClick={() => setIssued(null)}>إغلاق</Button>
          <Button onClick={() => issued && printBadges([issued.id])}><Printer className="h-4 w-4" />طباعة الكود</Button>
        </>
      }>
        {issued && (
          <div className="text-center">
            <div className="text-sm text-slate-500">{issued.full_name}</div>
            {!!(issued.governorate || issued.organization || issued.job_title) && (
              <div className="mt-0.5 text-xs text-slate-500">{[issued.governorate, issued.organization, issued.job_title].filter(Boolean).join(' · ')}</div>
            )}
            <div className="num mt-1 font-mono text-4xl font-bold tracking-widest text-brand-800">{issued.badge_id}</div>
            <div className="mt-2 flex justify-center">
              {qrUrl ? (
                <img src={qrUrl} alt={`QR ${issued.badge_id}`} className="h-32 w-32 rounded-lg border border-slate-200 bg-white p-1.5" />
              ) : (
                <div className="h-32 w-32 animate-pulse rounded-lg bg-slate-100" />
              )}
            </div>
            <p className="mt-2 text-xs text-slate-500">رمز QR يحمل نفس الكود {issued.badge_id}</p>
          </div>
        )}
      </Modal>

      <Modal open={!!importResult} title={t('Import finished', 'اكتمل الاستيراد')} onClose={() => setImportResult(null)} footer={<Button onClick={() => setImportResult(null)}>{t('Done', 'تم')}</Button>}>
        {importResult && (
          <div className="space-y-3 text-sm">
            <div className="flex gap-6">
              <div><div className="text-2xl font-bold text-emerald-600">{importResult.created}</div><div className="text-slate-500">{t('created', 'تمت إضافتهم')}</div></div>
              <div><div className="text-2xl font-bold text-amber-600">{importResult.errors.length}</div><div className="text-slate-500">{t('rows with issues', 'صفوف بها مشاكل')}</div></div>
            </div>
            {importResult.errors.length > 0 && (
              <ul className="max-h-48 space-y-1 overflow-y-auto rounded-lg bg-slate-50 p-3 text-xs">
                {importResult.errors.map((e, i) => <li key={i}><b>{t('Row', 'صف')} {e.row}:</b> {e.error}</li>)}
              </ul>
            )}
          </div>
        )}
      </Modal>
      {dialog}
    </>
  )
}
