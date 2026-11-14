import type { ReactNode } from 'react'
import logo from '../../assets/logo.png'
/** Mobile-first frame shared by the trainee pages. */
export default function PortalShell({ title, subtitle, children }: { title?: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="min-h-full bg-slate-100 pb-12">
      <header className="brand-hero px-5 pb-14 pt-[max(1rem,env(safe-area-inset-top))] text-white">
        <div className="mx-auto max-w-xl">
          <div className="flex items-center justify-between">
            <img src={logo} alt="" className="h-11 w-11 shrink-0 rounded-full bg-white object-contain p-0.5 shadow-md" />
          </div>
          <div className="mt-5">
            {subtitle && <div className="text-xs font-semibold uppercase tracking-wider text-brand-200">{subtitle}</div>}
            {title && <h1 className="mt-1 text-2xl font-bold leading-tight tracking-tight">{title}</h1>}
          </div>
        </div>
      </header>
      <main className="page-in mx-auto -mt-8 max-w-xl space-y-4 px-4">{children}</main>
    </div>
  )
}
