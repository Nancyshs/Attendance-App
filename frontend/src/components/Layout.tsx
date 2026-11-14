import clsx from 'clsx'
import {
  CalendarDays,
  ChevronDown,
  GraduationCap,
  ClipboardCheck,
  ClipboardList,
  GitCompare,
  ListChecks,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  ScanLine,
  Settings as SettingsIcon,
  Users,
  WifiOff,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import logo from '../assets/logo.png'
import { useAuth } from '../lib/auth'
import { fmtDayLong, todayLocal } from '../lib/format'
import { useI18n, type Lang } from '../lib/i18n'
import type { Role } from '../lib/types'
import { Avatar } from './ui'

function useOnline() {
  const [online, setOnline] = useState(navigator.onLine)
  useEffect(() => {
    const on = () => setOnline(true)
    const off = () => setOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])
  return online
}

export function LanguageSwitch({ dark = false }: { dark?: boolean }) {
  const { lang, setLang } = useI18n()
  const opts: { id: Lang; label: string; aria: string }[] = [
    { id: 'ar', label: 'ع', aria: 'العربية' },
    { id: 'en', label: 'EN', aria: 'English' },
  ]
  return (
    <div role="group" aria-label="Language / اللغة" className={clsx('inline-flex rounded-lg p-0.5 text-xs font-semibold', dark ? 'bg-white/10' : 'bg-slate-100')}>
      {opts.map((o) => (
        <button
          key={o.id}
          type="button"
          lang={o.id}
          aria-label={o.aria}
          aria-pressed={lang === o.id}
          title={o.aria}
          onClick={() => setLang(o.id)}
          className={clsx(
            'min-w-9 rounded-md px-2.5 py-1.5 transition',
            lang === o.id
              ? dark
                ? 'bg-white text-navy-900 shadow-xs'
                : 'bg-white text-brand-700 shadow-xs'
              : dark
                ? 'text-white/75 hover:text-white'
                : 'text-slate-500 hover:text-slate-800',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  if (!user) return null
  const roleLabel: Record<string, string> = {
    admin: t('Administrator', 'مدير النظام'),
    staff: t('Staff', 'موظف'),
    trainer: t('Trainer', 'محاضر'),
  }
  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2.5 rounded-lg py-1 ps-1 pe-2 transition hover:bg-slate-100"
      >
        <Avatar name={user.full_name} size={32} />
        <span className="hidden text-start sm:block">
          <span className="block text-[13px] font-semibold leading-tight text-slate-900">{user.full_name}</span>
          <span className="block text-xs leading-tight text-slate-500">{roleLabel[user.role] ?? user.role}</span>
        </span>
        <ChevronDown className={clsx('h-4 w-4 text-slate-400 transition', open && 'rotate-180')} />
      </button>
      {open && (
        <div role="menu" className="pop absolute end-0 top-full z-50 mt-2 w-64 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-pop">
          <div className="border-b border-slate-100 px-4 py-3">
            <div className="text-sm font-semibold text-slate-900">{user.full_name}</div>
            <div className="text-xs text-slate-500">
              <span dir="ltr">@{user.username}</span> · {roleLabel[user.role] ?? user.role}
            </div>
          </div>
          <button
            role="menuitem"
            onClick={logout}
            className="flex w-full items-center gap-2.5 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-red-50 hover:text-red-700"
          >
            <LogOut className="h-4 w-4" />
            {t('Sign out', 'تسجيل الخروج')}
          </button>
        </div>
      )}
    </div>
  )
}

type NavItem = { to: string; label: string; icon: typeof Users; roles: Role[]; on?: (path: string, search: string) => boolean }

export default function Layout() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const online = useOnline()
  const loc = useLocation()

  useEffect(() => setOpen(false), [loc.pathname])

  const groupDefs: { title: string; items: NavItem[] }[] = [
    {
      title: t('Overview', 'نظرة عامة'),
      items: [{ to: '/', label: t('Dashboard', 'لوحة التحكم'), icon: LayoutDashboard, roles: ['admin', 'staff'] }],
    },
    {
      title: t('Daily operations', 'العمليات اليومية'),
      items: [
        { to: '/scanner', label: t('Scanner', 'ماسح الباج'), icon: ScanLine, roles: ['admin', 'staff'] },
        { to: '/attendance', label: t('Attendance', 'الحضور والانصراف'), icon: ClipboardCheck, roles: ['admin', 'staff'] },
        { to: '/trainees', label: t('Trainees', 'المتدربون'), icon: Users, roles: ['admin', 'staff'] },
        { to: '/schedule', label: t('Schedule', 'جدول المحاضرات'), icon: CalendarDays, roles: ['admin', 'staff'], on: (path, search) => path === '/schedule' && new URLSearchParams(search).get('tab') !== 'trainers' },
        { to: '/schedule?tab=trainers', label: t('Trainers', 'المحاضرون'), icon: GraduationCap, roles: ['admin', 'staff'], on: (path, search) => path === '/schedule' && new URLSearchParams(search).get('tab') === 'trainers' },
      ],
    },
    {
      title: t('Insights', 'التقارير'),
      items: [
        { to: '/feedback', label: t('Feedback', 'التقييمات'), icon: MessageSquareText, roles: ['admin', 'staff', 'trainer'] },
        { to: '/exams/before', label: t('Exam before', 'امتحان قبل المحاضرة'), icon: ClipboardList, roles: ['admin', 'staff'] },
        { to: '/exams/after', label: t('Exam after', 'امتحان بعد المحاضرة'), icon: ListChecks, roles: ['admin', 'staff'] },
        { to: '/exams/compare', label: t('Exam comparison', 'مقارنة الامتحان'), icon: GitCompare, roles: ['admin', 'staff'] },
      ],
    },
    {
      title: t('Administration', 'الإدارة'),
      items: [{ to: '/settings', label: t('Settings', 'الإعدادات'), icon: SettingsIcon, roles: ['admin'] }],
    },
  ]
  const groups = groupDefs
    .map((g) => ({ ...g, items: g.items.filter((i) => user && i.roles.includes(user.role)) }))
    .filter((g) => g.items.length)

  const brand = (
    <div className="flex items-center gap-3 px-5 py-5">
      <img src={logo} alt="" className="h-11 w-11 shrink-0 rounded-full bg-white object-contain p-0.5 shadow-md ring-2 ring-white/20" />
      <div className="min-w-0">
        <div className="text-sm font-bold leading-snug text-white">{t('Attendance & Feedback', 'الحضور والتقييم')}</div>
        <div className="mt-0.5 truncate text-xs text-white/60">{t('Ertekaa Training', 'ارتقاء للتدريب')}</div>
      </div>
    </div>
  )

  const nav = (
    <nav aria-label={t('Main', 'القائمة الرئيسية')} className="flex-1 overflow-y-auto px-3 pb-4">
      {groups.map((g) => (
        <div key={g.title} className="mt-4 first:mt-1">
          <div className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-white/50">{g.title}</div>
          <div className="space-y-0.5">
            {g.items.map(({ to, label, icon: Icon, on }) => {
              const isActive = on ? on(loc.pathname, loc.search) : undefined
              return (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive: routeActive }) => {
                  const active = isActive ?? routeActive
                  return clsx(
                    'group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                    active ? 'bg-white/12 text-white' : 'text-white/70 hover:bg-white/8 hover:text-white',
                  )
                }}
              >
                {({ isActive: routeActive }) => {
                  const active = isActive ?? routeActive
                  return (
                  <>
                    {active && <span className="absolute inset-y-2 start-0 w-[3px] rounded-full bg-olive-300" />}
                    <Icon className={clsx('h-[18px] w-[18px] shrink-0', active ? 'text-olive-300' : 'text-white/55 group-hover:text-white/80')} />
                    {label}
                  </>
                  )
                }}
              </NavLink>
              )
            })}
          </div>
        </div>
      ))}
    </nav>
  )

  const sidebarFooter = (
    <div className="border-t border-white/10 px-5 py-3.5 text-xs text-white/55">
      <div className="flex items-center gap-2">
        <span className={clsx('h-2 w-2 rounded-full', online ? 'bg-emerald-400' : 'bg-amber-400')} />
        {online ? t('Connected', 'متصل بالسيرفر') : t('Offline', 'غير متصل')}
      </div>
    </div>
  )

  return (
    <div className="flex min-h-full bg-slate-50">
      {/* desktop sidebar */}
      <aside className="no-print sidebar-bg sticky top-0 hidden h-screen w-64 shrink-0 flex-col lg:flex">
        {brand}
        {nav}
        {sidebarFooter}
      </aside>

      {/* mobile drawer */}
      {open && (
        <div className="no-print fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy-950/50 backdrop-blur-[2px]" onClick={() => setOpen(false)} />
          <aside className="sidebar-bg absolute inset-y-0 start-0 flex w-72 max-w-[85vw] flex-col shadow-pop">
            <button onClick={() => setOpen(false)} aria-label={t('Close menu', 'إغلاق القائمة')} className="absolute end-3 top-4 rounded-lg p-1.5 text-white/70 hover:bg-white/10 hover:text-white">
              <X className="h-5 w-5" />
            </button>
            {brand}
            {nav}
            {sidebarFooter}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex h-16 items-center justify-between gap-3 border-b border-slate-200 bg-white/85 px-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <button className="-ms-1 rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(true)} aria-label={t('Open menu', 'فتح القائمة')}>
              <Menu className="h-5 w-5" />
            </button>
            <div className="hidden whitespace-nowrap text-sm text-slate-500 md:block">{fmtDayLong(todayLocal())}</div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {!online && (
              <span className="flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
                <WifiOff className="h-3.5 w-3.5" />
                {t('Offline', 'غير متصل')}
              </span>
            )}
            <UserMenu />
          </div>
        </header>
        {!online && (
          <div className="no-print bg-amber-50 px-4 py-2 text-center text-xs font-medium text-amber-900">
            {t('You are offline. Scans are saved on this device and sent automatically when the connection returns.', 'أنت غير متصل. يتم حفظ المسح على هذا الجهاز وإرساله تلقائياً عند عودة الاتصال.')}
          </div>
        )}
        <main key={loc.pathname} className="page-in mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
