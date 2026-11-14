import { Loader2, QrCode } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '../../components/ui'
import { api, ApiError, TRAINEE_KEY } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import PortalShell from './PortalShell'

/** Landing page of the badge QR code: exchanges the badge token for a session and moves on. */
export default function PortalEntry() {
  const { token = '' } = useParams()
  const nav = useNavigate()
  const { t } = useI18n()
  const [error, setError] = useState<{ message: string; network: boolean } | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    api
      .post<{ access_token: string }>('/portal/auth', { token }, 'none')
      .then((r) => {
        localStorage.setItem(TRAINEE_KEY, r.access_token)
        if (!cancelled) nav('/me', { replace: true })
      })
      .catch((e) => !cancelled && setError({ message: e instanceof Error ? e.message : t('Something went wrong', 'حدث خطأ'), network: e instanceof ApiError && e.isNetwork }))
    return () => {
      cancelled = true
    }
  }, [token, nav, attempt])

  return (
    <PortalShell subtitle={t('Trainee portal', 'بوابة المتدرب')} title={t('Welcome', 'أهلاً بك')}>
      <div className="rounded-2xl bg-white p-8 text-center shadow-md">
        {error ? (
          <>
            <QrCode className="mx-auto h-10 w-10 text-red-500" />
            <p className="mt-4 text-sm text-slate-700" role="alert">{error.message}</p>
            {error.network && <Button className="mt-5" onClick={() => { setError(null); setAttempt((a) => a + 1) }}>{t('Try again', 'حاول مرة أخرى')}</Button>}
          </>
        ) : (
          <>
            <Loader2 className="mx-auto h-8 w-8 animate-spin text-brand-600" />
            <p className="mt-4 text-sm text-slate-600">{t('Signing you in…', 'جارٍ تسجيل دخولك…')}</p>
          </>
        )}
      </div>
    </PortalShell>
  )
}
