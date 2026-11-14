import { useQuery } from '@tanstack/react-query'
import { Printer, X } from 'lucide-react'
import { useEffect } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import logo from '../assets/logo.png'
import { Button, ErrorBox, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import type { PublicSurvey } from '../lib/types'

const PAPER_PROGRAM = 'البرنامج التدريبي المتكامل لتنمية القدرات الفنية والإدارية في مجالات إدارة المخلفات الصلبة والتغيرات المناخية والاقتصاد الدائري'
const PAPER_AXIS = 'إدارة المخلفات الصلبة والتغيرات المناخية والاقتصاد الدائري'

const Dots = ({ lines = 2 }: { lines?: number }) => (
  <div className="mt-2 space-y-5">
    {Array.from({ length: lines }, (_, i) => <div key={i} className="border-b border-dotted border-slate-500" />)}
  </div>
)

/** A4 paper survey. Programme name and training axis are fixed on every form. */
export default function PrintSurvey() {
  const { token = '' } = useParams()
  const [params] = useSearchParams()
  const { t } = useI18n()
  const { data, error, isLoading, refetch } = useQuery({ queryKey: ['print-survey', token], queryFn: () => api.get<PublicSurvey>(`/public/surveys/${token}`, 'none') })

  useEffect(() => {
    if (data && params.get('print') === '1') {
      const h = setTimeout(() => window.print(), 400)
      return () => clearTimeout(h)
    }
  }, [data, params])

  if (isLoading) return <Spinner />
  if (error || !data) return <ErrorBox error={error} onRetry={refetch} />

  const ratings = data.questions.filter((q) => q.type === 'rating')
  const others = data.questions.filter((q) => q.type !== 'rating')
  const field = (label: string, value?: string | null, size = '') => (
    <div className={`border-b border-dotted border-slate-500 pb-1 leading-relaxed ${size}`}>
      <span className="font-semibold text-slate-800">{label}: </span>
      <span className="text-slate-900">{value}</span>
    </div>
  )

  return (
    <div className="min-h-full bg-slate-200 py-6 print:bg-white print:py-0">
      <div className="no-print mx-auto mb-4 flex max-w-[210mm] items-center justify-between gap-3 px-2">
        <p className="text-sm text-slate-600">{t('Preview of the paper form (A4).', 'معاينة النسخة الورقية (A4).')}</p>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={() => window.close()}><X className="h-4 w-4" />{t('Close', 'إغلاق')}</Button>
          <Button onClick={() => window.print()}><Printer className="h-4 w-4" />{t('Print', 'طباعة')}</Button>
        </div>
      </div>

      <article className="print-page mx-auto flex min-h-[297mm] w-[210mm] max-w-full flex-col bg-white p-[12mm] text-[13px] leading-snug text-slate-900 shadow-lg print:min-h-[281mm]">
        <header className="flex items-center gap-4 border-b-2 border-brand-700 pb-3">
          <img src={logo} alt="" className="h-16 w-16 shrink-0 object-contain" />
          <div className="min-w-0 flex-1 text-center">
            <p className="text-[16px] font-normal leading-snug text-slate-700">{t('Integrated training programme for technical and administrative capacity in solid waste, climate change and the circular economy', PAPER_PROGRAM)}</p>
            <h1 className="mt-3 text-[30px] font-bold leading-snug text-brand-800">{t('Training Session Quality Survey', 'استبيان تقييم جودة الجلسة التدريبية')}</h1>
          </div>
        </header>

        <section className="mt-4 space-y-3">
          {field(t('Programme', 'اسم البرنامج'), PAPER_PROGRAM)}
          {field(t('Training axis', 'المحور التدريبي'), PAPER_AXIS)}
          {field(t('Session title', 'عنوان الجلسة'))}
          <div className="grid grid-cols-2 gap-6">
            {field(t('Trainer', 'المدرب'), undefined, 'text-[11px]')}
            {field(t('Date', 'التاريخ'))}
          </div>
        </section>

        <p className="mt-5 font-semibold">{t('Please rate the session according to the following criteria. Note that 5 is the best rating.', 'يرجى تقييم الجلسة طبقًا للمعايير التالية، علمًا بأن 5 أفضل تقييم.')}</p>

        {ratings.length > 0 && (
          <table className="mt-3 w-full table-fixed border-collapse text-[13px]">
            <colgroup>
              <col className="w-9" />
              <col />
              <col className="w-[15mm]" />
              <col className="w-[15mm]" />
              <col className="w-[15mm]" />
              <col className="w-[15mm]" />
              <col className="w-[15mm]" />
            </colgroup>
            <thead>
              <tr className="bg-brand-700 text-white print:[-webkit-print-color-adjust:exact] print:[print-color-adjust:exact]">
                <th className="border border-brand-800 px-1 py-1.5">{t('No.', 'م')}</th>
                <th className="border border-brand-800 px-2 py-1.5 text-start">{t('Evaluation criterion', 'معيار التقييم')}</th>
                {[1, 2, 3, 4, 5].map((n) => (
                  <th key={n} className="border border-brand-800 px-0.5 py-1.5 text-sm font-semibold">
                    <span className="num">{n}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ratings.map((q, i) => (
                <tr key={q.id}>
                  <td className="border border-slate-400 px-1 py-2.5 text-center font-semibold"><span className="num">{i + 1}</span></td>
                  <td className="border border-slate-400 px-2 py-2.5">{q.text}</td>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <td key={n} className="border border-slate-400 py-2.5 text-center"><span className="inline-block h-4 w-4 rounded-full border-[1.5px] border-slate-600 align-middle" /></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {others.length > 0 && <h2 className="mt-6 text-base font-bold text-brand-800">{t('Open questions', 'أسئلة مفتوحة')}</h2>}
        {others.map((q, i) => (
          <div key={q.id} className="mt-3">
            <p className="font-semibold"><span className="num me-1.5 text-brand-700">{i + 1}</span>{q.text}</p>
            {q.type === 'choice' ? (
              <p className="mt-2 flex flex-wrap gap-x-6 gap-y-1">{q.options?.map((o) => <span key={o}><span className="me-1.5 inline-block h-3.5 w-3.5 border-[1.5px] border-slate-600 align-middle" />{o}</span>)}</p>
            ) : q.type === 'nps' ? (
              <p className="num mt-2 flex gap-2">{Array.from({ length: 11 }, (_, n) => <span key={n} className="flex h-6 w-6 items-center justify-center rounded-full border-[1.5px] border-slate-600 text-[11px]">{n}</span>)}</p>
            ) : (
              <Dots lines={3} />
            )}
          </div>
        ))}

        <footer className="mt-auto pt-8 text-[13px] font-semibold leading-relaxed text-slate-900" style={{ textAlign: 'left' }}>
          <p>{t('With sincere wishes for continued success', 'خالص التمنيات بدوام التوفيق')}</p>
          <p>{t('Ertekaa Integrated Services', 'شركة ارتقاء للخدمات المتكاملة')}</p>
        </footer>
      </article>
    </div>
  )
}
