import { useMutation } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '../lib/api'
import { fmtDay } from '../lib/format'
import { useI18n } from '../lib/i18n'
import type { Session } from '../lib/types'
import { Button, Modal, useToast, errMsg } from './ui'

interface QuestionDraft {
  key: string
  text: string
}

let nextKey = 0
const fresh = (text = ''): QuestionDraft => ({ key: `q${nextKey++}`, text })

/** One pasted line is one question. A leading number or dash is dropped. */
function linesOf(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/^(?:\d+\s*[\.\)\-]|[-•*])\s*/, '').slice(0, 500))
    .filter(Boolean)
}

/** A lecture's exam: the organiser writes the questions, and each one is answered صح or غلط. */
export default function ExamEditor({ session, onClose, onSaved }: { session: Session | null; onClose: () => void; onSaved: () => void }) {
  const { t } = useI18n()
  const toast = useToast()
  const [questions, setQuestions] = useState<QuestionDraft[]>(() =>
    session && session.exam_questions.length ? session.exam_questions.map((q) => fresh(q.text)) : [fresh()],
  )
  const [bulk, setBulk] = useState('')

  const save = useMutation({
    mutationFn: () => {
      if (!session) throw new Error('no session')
      const written = questions.map((q) => q.text.trim()).filter(Boolean)
      return api.put<Session>(`/sessions/${session.id}`, {
        day: session.day,
        start_time: session.start_time,
        end_time: session.end_time,
        title: session.title,
        exam_questions: written.map((text) => ({ text })),
      })
    },
    onSuccess: () => {
      toast.push('success', t('Exam saved', 'تم حفظ الامتحان'))
      onSaved()
      onClose()
    },
    onError: (e) => toast.push('error', errMsg(e)),
  })

  if (!session) return null
  const canSave = questions.some((q) => q.text.trim())

  function update(key: string, text: string) {
    setQuestions((list) => list.map((q) => (q.key === key ? { ...q, text } : q)))
  }

  function addLines(raw: string) {
    const lines = linesOf(raw)
    if (!lines.length) return
    setQuestions((list) => {
      const kept = list.filter((q) => q.text.trim())
      return [...kept, ...lines.map((text) => fresh(text))]
    })
    setBulk('')
  }

  function pasteInto(key: string, raw: string) {
    const lines = linesOf(raw)
    if (lines.length <= 1) return
    setQuestions((list) => {
      const index = list.findIndex((q) => q.key === key)
      if (index < 0) return list
      const next = [...list]
      next[index] = { ...next[index], text: lines[0] }
      next.splice(index + 1, 0, ...lines.slice(1).map((text) => fresh(text)))
      return next
    })
  }

  return (
    <Modal
      open
      wide
      title={session.exam_questions.length ? t('Edit exam', 'تعديل الامتحان') : t('Add exam', 'إضافة امتحان')}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t('Cancel', 'إلغاء')}</Button>
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!canSave}>{t('Save exam', 'حفظ الامتحان')}</Button>
        </>
      }
    >
      <div className="mb-5">
        <p className="text-lg font-bold text-slate-900">{session.title}</p>
        <p className="mt-1 text-sm text-slate-500">{fmtDay(session.day)} · {session.start_time}–{session.end_time}</p>
        <p className="mt-2 text-sm text-slate-600">{t('Write the questions only. Trainees answer each one with True or False. You open the exam, and choose its duration, from the QR screen.', 'اكتبي الأسئلة فقط. المتدرب يجاوب بصح أو غلط. فتح الامتحان ومدته من شاشة الرمز، في الوقت اللي تختاريه.')}</p>
      </div>

      <div className="mb-4 rounded-2xl border border-brand-200 bg-brand-50 p-4">
        <p className="text-sm font-bold text-brand-900">{t('Paste several questions', 'لصق عدة أسئلة مع بعض')}</p>
        <p className="mt-1 text-xs text-slate-600">{t('Each line becomes its own question.', 'كل سطر يبقى سؤال لوحده.')}</p>
        <textarea
          value={bulk}
          rows={4}
          placeholder={t('Paste the questions here, one per line', 'الصقي الأسئلة هنا، كل سؤال في سطر')}
          onChange={(e) => setBulk(e.target.value)}
          onPaste={(e) => {
            const text = e.clipboardData.getData('text')
            const combined = bulk.trim() ? `${bulk}\n${text}` : text
            if (linesOf(combined).length <= 1) return
            e.preventDefault()
            addLines(combined)
          }}
          className="mt-3 block w-full resize-none rounded-xl border border-brand-200 bg-white px-3 py-2.5 text-sm leading-relaxed text-slate-900 outline-none placeholder:text-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
        />
        <Button className="mt-3" size="sm" variant="secondary" disabled={!linesOf(bulk).length} onClick={() => addLines(bulk)}>
          {t('Add these questions', 'إضافة هذه الأسئلة')}
        </Button>
      </div>

      <div className="space-y-3">
        {questions.map((q, i) => (
          <div key={q.key} className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4">
            <div className="mb-2 flex items-center justify-between">
              <span className="num flex h-7 min-w-7 items-center justify-center rounded-full bg-brand-700 px-2 text-sm font-bold text-white">{i + 1}</span>
              <button
                type="button"
                className="rounded-lg p-1.5 text-slate-400 hover:bg-white hover:text-red-600"
                aria-label={t('Remove question', 'حذف السؤال')}
                onClick={() => setQuestions((list) => (list.length === 1 ? [fresh()] : list.filter((item) => item.key !== q.key)))}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
            <textarea
              value={q.text}
              autoFocus={i === 0}
              rows={2}
              placeholder={t('Write the question here', 'اكتبي السؤال هنا')}
              onChange={(e) => update(q.key, e.target.value)}
              onPaste={(e) => {
                const text = e.clipboardData.getData('text')
                if (linesOf(text).length <= 1) return
                e.preventDefault()
                pasteInto(q.key, text)
              }}
              className="block w-full resize-none rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm leading-relaxed text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-brand-500 focus:ring-4 focus:ring-brand-500/15"
            />
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs text-slate-500">{t('The trainee answers', 'المتدرب يجاوب')}</span>
              <span className="rounded-full bg-brand-700 px-3 py-1 text-xs font-bold text-white">{t('True', 'صح')}</span>
              <span className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-bold text-slate-600">{t('False', 'غلط')}</span>
            </div>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setQuestions((list) => [...list, fresh()])}
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-2xl border border-dashed border-brand-300 bg-brand-50 py-3 text-sm font-semibold text-brand-800 hover:bg-brand-100"
      >
        <Plus className="h-4 w-4" />
        {t('Add a question', 'إضافة سؤال')}
      </button>
    </Modal>
  )
}

