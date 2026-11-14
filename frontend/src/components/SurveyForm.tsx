import clsx from 'clsx'
import { useMemo, useState } from 'react'
import { useI18n } from '../lib/i18n'
import type { SurveyQuestionDef } from '../lib/types'
import { Button, Textarea } from './ui'

export type Answers = Record<number, number | string | null>

function RatingCircles({ value, onChange, name }: { value: number | null | undefined; onChange: (n: number) => void; name: string }) {
  return (
    <div className="flex justify-between gap-2" role="radiogroup" aria-label={name}>
      {[1, 2, 3, 4, 5].map((n) => {
        const selected = value === n
        return (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-label={String(n)}
            onClick={() => onChange(n)}
            className={clsx(
              'num flex h-14 w-14 items-center justify-center rounded-full border-2 text-lg font-bold transition active:scale-95 sm:h-16 sm:w-16 sm:text-xl',
              selected ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white text-slate-700 hover:border-brand-400',
            )}
          >
            {n}
          </button>
        )
      })}
    </div>
  )
}

function hasAnswer(value: number | string | null | undefined): boolean {
  if (typeof value === 'string') return value.trim() !== ''
  return value !== undefined && value !== null
}

/** One question per screen, with a line showing how many are answered. Used by the public (QR) and badge portals. */
export default function SurveyForm({
  questions,
  answers,
  onChange,
  onSubmit,
  submitting = false,
  canSubmit = true,
  submitLabel,
  submitError,
}: {
  questions: SurveyQuestionDef[]
  answers: Answers
  onChange: (id: number, v: number | string | null) => void
  onSubmit?: () => void
  submitting?: boolean
  canSubmit?: boolean
  submitLabel?: string
  submitError?: string
}) {
  const { t } = useI18n()
  const ordered = useMemo(
    () => [...questions.filter((q) => q.type !== 'text'), ...questions.filter((q) => q.type === 'text')],
    [questions],
  )
  const [step, setStep] = useState(0)
  const total = ordered.length
  const index = total ? Math.min(step, total - 1) : 0
  const current = ordered[index]
  const answered = ordered.filter((q) => hasAnswer(answers[q.id])).length
  const currentMissing = !!current && !hasAnswer(answers[current.id])
  const last = index >= total - 1

  if (!current) return null

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-center text-sm font-semibold text-brand-900">
          {t(`Answered ${answered} of ${total}`, `جاوبت ${answered} من ${total}`)}
        </p>
        <div className="h-1.5 overflow-hidden rounded-full bg-slate-200" aria-hidden>
          <div className="h-full rounded-full bg-brand-600 transition-all" style={{ width: `${total ? (answered / total) * 100 : 0}%` }} />
        </div>
      </div>

      <section className="rounded-2xl bg-white p-4 shadow-md sm:p-5">
        <h3 className="flex gap-2.5 text-[15px] font-semibold leading-snug text-slate-900">
          <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-bold text-brand-800"><span className="num">{index + 1}</span></span>
          <span dir="auto" className="block flex-1">
            {current.text}
            <span className="text-red-500"> *</span>
          </span>
        </h3>
        <div className="mt-3">
          {current.type === 'rating' && <RatingCircles name={current.text} value={answers[current.id] as number | undefined} onChange={(n) => onChange(current.id, n)} />}
          {current.type === 'nps' && (
            <div className="grid grid-cols-6 gap-2 sm:grid-cols-11">
              {Array.from({ length: 11 }, (_, n) => (
                <button key={n} type="button" onClick={() => onChange(current.id, n)} className={clsx('num rounded-lg py-3 text-sm font-semibold transition active:scale-95', answers[current.id] === n ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-700')}>
                  {n}
                </button>
              ))}
            </div>
          )}
          {current.type === 'choice' && (
            <div className="space-y-2" role="radiogroup">
              {current.options?.map((o) => (
                <button key={o} type="button" role="radio" aria-checked={answers[current.id] === o} onClick={() => onChange(current.id, o)} className={clsx('w-full rounded-xl border-2 px-4 py-3 text-start text-sm font-medium transition active:scale-[0.99]', answers[current.id] === o ? 'border-brand-600 bg-brand-50 text-brand-700' : 'border-slate-200 text-slate-700')}>
                  {o}
                </button>
              ))}
            </div>
          )}
          {current.type === 'text' && (
            <>
              <Textarea rows={4} maxLength={2000} value={(answers[current.id] as string) ?? ''} onChange={(e) => onChange(current.id, e.target.value)} placeholder={t('Write your answer…', 'اكتب إجابتك هنا…')} />
              {currentMissing && <p className="mt-2 text-sm text-red-600">{t('This question is required before you can continue.', 'هذا السؤال مطلوب قبل المتابعة.')}</p>}
            </>
          )}
        </div>
      </section>

      {submitError && last && <div role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700">{submitError}</div>}

      <div className="flex gap-2">
        {index > 0 && (
          <Button variant="secondary" size="lg" className="flex-1" onClick={() => setStep(index - 1)}>{t('Previous', 'السابق')}</Button>
        )}
        {last ? (
          onSubmit && (
            <Button size="lg" className="flex-1" onClick={onSubmit} loading={submitting} disabled={!canSubmit}>
              {submitLabel || t('Submit feedback', 'إرسال التقييم')}
            </Button>
          )
        ) : (
          <Button size="lg" className="flex-1" onClick={() => setStep(index + 1)} disabled={currentMissing}>{t('Next', 'التالي')}</Button>
        )}
      </div>
    </div>
  )
}
