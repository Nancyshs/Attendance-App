import { CheckCircle2, Lock, QrCode, User as UserIcon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import logo from '../assets/logo.png'
import { Button, Field, Input } from '../components/ui'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'

export default function Login() {
  const { user, login } = useAuth()
  const { t } = useI18n()
  const nav = useNavigate()
  const loc = useLocation() as { state?: { from?: string } }
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to={user.role === 'trainer' ? '/feedback' : '/'} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const u = await login(username.trim(), password)
      nav(loc.state?.from ?? (u.role === 'trainer' ? '/feedback' : '/'), { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : t('Sign in failed', 'فشل تسجيل الدخول'))
    } finally {
      setBusy(false)
    }
  }

  const points = [
    t('One scan a day for check-in and check-out', 'مسح واحد يومياً للحضور والانصراف'),
    t('USB reader and phone camera supported', 'يدعم قارئ USB وكاميرا الموبايل'),
    t('Anonymous feedback for every lecture', 'استبيان مجهول الهوية لكل محاضرة'),
  ]

  return (
    <div className="grid min-h-full lg:grid-cols-[1.05fr_1fr]">
      {/* brand panel */}
      <section className="brand-hero relative hidden flex-col justify-between p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <img src={logo} alt="" className="h-12 w-12 rounded-full bg-white object-contain p-0.5 shadow-lg" />
          <span className="text-lg font-semibold">{t('Ertekaa Training', 'ارتقاء للتدريب')}</span>
        </div>
        <div className="max-w-md">
          <div className="mb-5 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/20">
            <QrCode className="h-6 w-6 text-olive-300" />
          </div>
          <h2 className="text-4xl font-bold leading-tight tracking-tight">{t('Attendance & feedback, done right.', 'الحضور والتقييم بشكل احترافي.')}</h2>
          <p className="mt-4 text-base leading-relaxed text-white/70">
            {t('A reliable system for tracking trainee attendance and collecting feedback on every lecture.', 'نظام موثوق لمتابعة حضور المتدربين وجمع آرائهم في كل محاضرة.')}
          </p>
          <ul className="mt-8 space-y-3">
            {points.map((p) => (
              <li key={p} className="flex items-start gap-3 text-sm text-white/85">
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-olive-300" />
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div className="text-xs text-white/40">© {new Date().getFullYear()} Ertekaa</div>
      </section>

      {/* form */}
      <section className="relative flex flex-col bg-white">
        <div className="flex flex-1 items-center justify-center px-6 py-16">
          <form onSubmit={submit} className="page-in w-full max-w-sm">
            <img src={logo} alt="" className="mb-6 h-16 w-16 rounded-full object-contain ring-1 ring-slate-200 lg:hidden" />
            <h1 className="text-3xl font-bold tracking-tight text-slate-900">{t('Welcome back', 'أهلاً بعودتك')}</h1>
            <p className="mt-2 text-sm text-slate-500">{t('Sign in to manage attendance and feedback.', 'سجّل الدخول لإدارة الحضور والتقييمات.')}</p>

            <div className="mt-8 space-y-5">
              <Field label={t('Username', 'اسم المستخدم')}>
                <div className="relative">
                  <UserIcon className="pointer-events-none absolute start-3 top-3 h-4 w-4 text-slate-400" />
                  <Input className="ps-9" autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)} required dir="ltr" style={{ textAlign: 'start' }} />
                </div>
              </Field>
              <Field label={t('Password', 'كلمة المرور')}>
                <div className="relative">
                  <Lock className="pointer-events-none absolute start-3 top-3 h-4 w-4 text-slate-400" />
                  <Input className="ps-9" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required dir="ltr" style={{ textAlign: 'start' }} />
                </div>
              </Field>
            </div>

            {error && (
              <div role="alert" className="mt-5 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-700">
                {error}
              </div>
            )}
            <Button type="submit" size="lg" className="mt-7 w-full" loading={busy}>
              {t('Sign in', 'تسجيل الدخول')}
            </Button>
          </form>
        </div>
      </section>
    </div>
  )
}
