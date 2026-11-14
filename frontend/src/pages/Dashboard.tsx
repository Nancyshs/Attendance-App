import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Clock, DoorOpen, GraduationCap, LogOut as LogOutIcon, ScanLine, Star, UserCheck, UserX, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, EmptyState, ErrorBox, Input, PageHeader, PageSkeleton, Stat, StatusChip } from '../components/ui'
import { api } from '../lib/api'
import { addDays, fmtDayLong, fmtTime, sourceLabel, todayLocal } from '../lib/format'
import { useI18n } from '../lib/i18n'
import type { Dashboard as DashboardData } from '../lib/types'

export default function Dashboard() {
  const { t } = useI18n()
  const [day, setDay] = useState(todayLocal())
  const isToday = day === todayLocal()
  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ['dashboard', day],
    queryFn: () => api.get<DashboardData>(`/reports/dashboard?day=${day}`),
    refetchInterval: isToday ? 8000 : false,
  })

  if (isLoading) return <PageSkeleton stats={7} />
  if (error || !data) return <ErrorBox error={error} onRetry={refetch} />
  const tt = data.totals
  const pct = tt.active ? Math.round((tt.arrived / tt.active) * 100) : 0

  return (
    <>
      <PageHeader
        title={t('Dashboard', 'لوحة التحكم')}
        subtitle={`${data.program_name} · ${fmtDayLong(data.date)}`}
        actions={
          <>
            <Button variant="secondary" size="sm" onClick={() => setDay(addDays(day, -1))} aria-label={t('Previous day', 'اليوم السابق')}>
              <ChevronLeft className="h-4 w-4 rtl:rotate-180" />
            </Button>
            <Input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} className="!w-40" />
            <Button variant="secondary" size="sm" onClick={() => setDay(addDays(day, 1))} aria-label={t('Next day', 'اليوم التالي')}>
              <ChevronRight className="h-4 w-4 rtl:rotate-180" />
            </Button>
            <Link to="/schedule?tab=trainers">
              <Button variant="secondary">
                <GraduationCap className="h-4 w-4" />
                {t('Trainers', 'المحاضرون')}
              </Button>
            </Link>
            {isToday && (
              <Link to="/scanner">
                <Button>
                  <ScanLine className="h-4 w-4" />
                  {t('Open scanner', 'فتح الماسح')}
                </Button>
              </Link>
            )}
          </>
        }
      />

      {!data.has_training_day && (
        <div className="mb-4 flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 shadow-xs">
          {t('No training is scheduled for this day.', 'لا يوجد تدريب مجدول في هذا اليوم.')}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Stat label={t('Registered', 'المسجلون')} value={tt.active} icon={<Users />} />
        <Stat label={t('Arrived', 'وصلوا')} value={tt.arrived} tone="green" sub={`${pct}%`} icon={<UserCheck />} />
        <Stat label={t('On time', 'في الموعد')} value={tt.on_time} tone="green" icon={<CheckCircle2 />} />
        <Stat label={t('Late', 'متأخرون')} value={tt.late} tone="amber" icon={<Clock />} />
        <Stat label={t('Not arrived', 'لم يصلوا')} value={tt.not_arrived} tone={data.day?.is_over ? 'red' : 'slate'} sub={data.day?.is_over ? t('absent', 'غياب') : undefined} icon={<UserX />} />
        <Stat label={t('In the room', 'داخل القاعة')} value={tt.present_now} tone="blue" icon={<DoorOpen />} />
        <Stat label={t('Checked out', 'انصرفوا')} value={tt.checked_out} tone="indigo" sub={tt.early_leave ? t(`${tt.early_leave} early`, `${tt.early_leave} مبكراً`) : undefined} icon={<LogOutIcon />} />
      </div>

      <div className="mt-4 flex items-center gap-3"><span className="text-xs font-medium text-slate-500">{t('Arrival progress', 'نسبة الوصول')}</span><div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200">
        <div className="h-2 rounded-full bg-gradient-to-r from-brand-600 to-olive-400 transition-all duration-700" style={{ width: `${pct}%` }} /></div><span className="num text-xs font-semibold text-slate-700">{pct}%</span></div>

      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        <Card title={t("Today's sessions & surveys", 'محاضرات اليوم والاستبيانات')} className="lg:col-span-2" padded={false}>
          {data.sessions.length === 0 ? (
            <EmptyState title={t('No sessions scheduled', 'لا توجد محاضرات')} hint={t('Add sessions in the Schedule page.', 'أضف المحاضرات من صفحة الجدول.')} />
          ) : (
            <div className="divide-y divide-slate-100">
              {data.sessions.map((s) => {
                const rate = tt.arrived ? Math.min(100, Math.round((s.submissions / tt.arrived) * 100)) : 0
                return (
                  <div key={s.id} className="px-5 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="font-medium text-slate-900">{s.title}</div>
                        <div className="text-xs text-slate-500">
                          <span className="num">{s.start_time}–{s.end_time}</span>
                          {s.trainer_name && ` · ${s.trainer_name}`}
                          {s.room && ` · ${s.room}`}
                        </div>
                      </div>
                      <StatusChip status={s.survey_state} />
                    </div>
                    {s.survey_state !== 'cancelled' && (
                      <div className="mt-2 flex items-center gap-3">
                        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                          <div className="h-full rounded-full bg-brand-500 transition-all" style={{ width: `${rate}%` }} />
                        </div>
                        <span className="num text-xs text-slate-500">{t(`${s.submissions} responses`, `${s.submissions} ردّ`)}</span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </Card>

        <Card title={t('Needs attention', 'يحتاج انتباهك')} padded={false}>
          {data.alerts.length === 0 ? (
            <p className="p-5 text-sm text-slate-500">{t('Nothing to flag. 🎉', 'لا توجد تنبيهات. 🎉')}</p>
          ) : (
            <ul className="max-h-[360px] divide-y divide-slate-100 overflow-y-auto">
              {data.alerts.map((a, i) => (
                <li key={i} className="flex items-start gap-3 px-5 py-3">
                  <span className={clsx('mt-0.5 rounded-full p-1.5', a.severity === 'high' ? 'bg-red-100 text-red-600' : 'bg-amber-100 text-amber-600')}>
                    {a.type === 'absences' ? <UserX className="h-4 w-4" /> : <Star className="h-4 w-4" />}
                  </span>
                  <div className="min-w-0 text-sm">
                    <div className="truncate font-medium text-slate-900">{a.title}</div>
                    <div className="text-xs text-slate-500">
                      {a.type === 'absences'
                        ? t(`${a.value} absences · ${a.badge_id}`, `${a.value} غياب · ${a.badge_id}`)
                        : t(`Average rating ${a.value} · ${a.trainer_name ?? ''}`, `متوسط التقييم ${a.value} · ${a.trainer_name ?? ''}`)}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title={t('Live activity', 'النشاط المباشر')} className="lg:col-span-3" padded={false}>
          {data.recent_scans.length === 0 ? (
            <EmptyState title={t('No scans yet', 'لا توجد عمليات مسح بعد')} />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <tbody className="divide-y divide-slate-100">
                  {data.recent_scans.map((s) => (
                    <tr key={s.id}>
                      <td className="num w-20 px-5 py-2 text-slate-500">{fmtTime(s.at)}</td>
                      <td className="px-2 py-2 font-medium text-slate-800">{s.trainee_name ?? '—'}</td>
                      <td className="num px-2 py-2 font-mono text-slate-500">{s.badge_id ?? ''}</td>
                      <td className="px-2 py-2">
                        <span className={clsx('inline-flex items-center gap-1', s.ok ? 'text-slate-700' : 'text-red-600')}>
                          {!s.ok && <AlertTriangle className="h-3.5 w-3.5" />}
                          {s.message}
                        </span>
                      </td>
                      <td className="px-5 py-2 text-end text-xs capitalize text-slate-400">{sourceLabel(s.source)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

