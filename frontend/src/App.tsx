import { lazy, Suspense, useEffect, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import { useAuth } from './lib/auth'
import { setTimezone } from './lib/format'
import type { Role } from './lib/types'
import Login from './pages/Login'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Scanner = lazy(() => import('./pages/Scanner'))
const Attendance = lazy(() => import('./pages/Attendance'))
const Trainees = lazy(() => import('./pages/Trainees'))
const Schedule = lazy(() => import('./pages/Schedule'))
const Feedback = lazy(() => import('./pages/Feedback'))
const ExamReport = lazy(() => import('./pages/ExamReport'))
const SettingsPage = lazy(() => import('./pages/Settings'))
const PortalEntry = lazy(() => import('./pages/portal/PortalEntry'))
const PortalHome = lazy(() => import('./pages/portal/PortalHome'))
const PortalSurvey = lazy(() => import('./pages/portal/PortalSurvey'))
const PublicSurvey = lazy(() => import('./pages/portal/PublicSurvey'))
const PublicExam = lazy(() => import('./pages/portal/PublicExam'))
const PrintSurvey = lazy(() => import('./pages/PrintSurvey'))

function Protected({ roles, children }: { roles?: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth()
  const loc = useLocation()
  if (loading) return <Spinner />
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />
  if (roles && !roles.includes(user.role)) return <Navigate to={user.role === 'trainer' ? '/feedback' : '/'} replace />
  return <>{children}</>
}

export default function App() {
  // use the programme timezone (set on the server) for every displayed time
  useEffect(() => {
    fetch('/api/public/config')
      .then((r) => (r.ok ? r.json() : null))
      .then((c: { timezone?: string; program_name?: string } | null) => {
        if (c?.timezone) setTimezone(c.timezone)
        if (c?.program_name) document.title = c.program_name
      })
      .catch(() => undefined)
  }, [])

  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        {/* trainee portal (opened by scanning the badge with a phone) */}
        <Route path="/t/:token" element={<PortalEntry />} />
        <Route path="/me" element={<PortalHome />} />
        <Route path="/me/survey/:id" element={<PortalSurvey />} />
        {/* per-session QR survey: anonymous, no login */}
        <Route path="/s/:token" element={<PublicSurvey />} />
        <Route path="/x/:token" element={<PublicExam />} />
        <Route path="/print/survey/:token" element={<Protected roles={['admin', 'staff']}><PrintSurvey /></Protected>} />

        <Route path="/login" element={<Login />} />
        <Route
          element={
            <Protected>
              <Layout />
            </Protected>
          }
        >
          <Route path="/" element={<Protected roles={['admin', 'staff']}><Dashboard /></Protected>} />
          <Route path="/scanner" element={<Protected roles={['admin', 'staff']}><Scanner /></Protected>} />
          <Route path="/attendance" element={<Protected roles={['admin', 'staff']}><Attendance /></Protected>} />
          <Route path="/trainees" element={<Protected roles={['admin', 'staff']}><Trainees /></Protected>} />
          <Route path="/schedule" element={<Protected roles={['admin', 'staff']}><Schedule /></Protected>} />
          <Route path="/feedback" element={<Feedback />} />
          <Route path="/exams/before" element={<Protected roles={['admin', 'staff']}><ExamReport part="before" /></Protected>} />
          <Route path="/exams/after" element={<Protected roles={['admin', 'staff']}><ExamReport part="after" /></Protected>} />
          <Route path="/exams/compare" element={<Protected roles={['admin', 'staff']}><ExamReport part="compare" /></Protected>} />
          <Route path="/settings" element={<Protected roles={['admin']}><SettingsPage /></Protected>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  )
}
