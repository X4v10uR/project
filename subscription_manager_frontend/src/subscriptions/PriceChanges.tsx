import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiError } from '../api'
import { buttonClass, currencyAmount, displayDate, ErrorBanner, Field, inputClass, panelClass, showError } from './shared'

type Change = { id: number; previous_cost: string; cost: string; effective_on: string }
type PriceHistory = { changes: Change[]; current_regular_cost: string; edit_revision?: string }
export function PriceChanges({ id, currency, disabled, onBusyChange, onCurrentCostChange, editRevision, onRevisionChange, onStale }: {
  id: number; currency: string; disabled: boolean;
  onBusyChange: (busy: boolean) => void; onCurrentCostChange: (cost: string) => void;
  editRevision?: string; onRevisionChange: (revision: string) => void; onStale: () => void;
}) {
  const [history, setHistory] = useState<PriceHistory>(); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setHistory(undefined); setError('')
    api<PriceHistory>(`/api/subscriptions/${id}/prices/`, { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setHistory(data) })
      .catch(e => { if (!controller.signal.aborted) setError(showError(e)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [id])
  useEffect(() => {
    if (window.location.hash === '#price-history') {
      document.getElementById('price-history')?.scrollIntoView({ block: 'start' })
    }
  }, [id])
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy || loading || disabled) return
    const form = event.currentTarget
    setError(''); setBusy(true); onBusyChange(true)
    try {
      const data = await api<PriceHistory>(`/api/subscriptions/${id}/prices/`, {
        method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(form))),
        headers: editRevision ? { 'If-Match': `"${editRevision}"` } : undefined,
      })
      if (data.current_regular_cost !== history?.current_regular_cost) onCurrentCostChange(data.current_regular_cost)
      if (data.edit_revision) onRevisionChange(data.edit_revision)
      setHistory(data)
      form.reset()
    } catch (e) {
      setError(showError(e))
      if (e instanceof ApiError && e.status === 412) onStale()
    } finally { setBusy(false); onBusyChange(false) }
  }
  return (
    <section id="price-history" className={`${panelClass} mt-5`}>
      <h2 className="text-lg font-bold">Price history & scheduled changes</h2>
      <p className="mt-2 text-sm text-slate-600">Set the provider’s new full price and effective date. Future renewals and forecasts use it automatically. Editing the main cost records a change effective today.</p>
      <ul className="my-4 divide-y divide-slate-100 text-sm">
        {history?.changes.map(change => <li key={change.id} className="flex flex-wrap justify-between gap-2 py-2"><span>{displayDate(change.effective_on)}</span><strong>{currencyAmount(change.previous_cost, currency)} → {currencyAmount(change.cost, currency)}</strong></li>)}
      </ul>
      <ErrorBanner message={error} />
      <form onSubmit={save} className="flex flex-wrap items-end gap-3">
        <Field label={`New full price (${currency})`}><input name="cost" type="number" min="0" step="0.01" required className={inputClass} /></Field>
        <Field label="Effective date"><input name="effective_on" type="date" required className={inputClass} /></Field>
        <button className={buttonClass} disabled={busy || loading || disabled}>Schedule price change</button>
      </form>
    </section>
  )
}

export function UsageReview({ id, initialRating, lastReviewed }: { id: number; initialRating: string; lastReviewed: string | null }) {
  const [rating, setRating] = useState(initialRating || 'sometimes'); const [error, setError] = useState(''); const [saved, setSaved] = useState(false); const [busy, setBusy] = useState(false)
  const [reviewedOn, setReviewedOn] = useState(lastReviewed)
  async function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const result = await api<{ last_reviewed_on: string }>('/api/subscriptions/review/action/', {
        method: 'POST', body: JSON.stringify({ action: 'review', ids: [id], usage_rating: rating }),
      })
      setReviewedOn(result.last_reviewed_on)
      setSaved(true)
    } catch (e) {
      setError(showError(e))
    } finally {
      setBusy(false)
    }
  }
  return <section className={`${panelClass} mt-5`}><h2 className="font-bold">Is this subscription still useful?</h2><p className="mt-2 text-sm text-slate-600">{reviewedOn ? `Last reviewed ${displayDate(reviewedOn)}.` : 'No review recorded yet.'} Low usage appears in your review inbox.</p><form onSubmit={review} className="mt-3 flex flex-wrap items-end gap-3"><Field label="How often do you use it?"><select className={inputClass} value={rating} onChange={e => { setRating(e.target.value); setSaved(false) }}><option value="often">Often</option><option value="sometimes">Sometimes</option><option value="rarely">Rarely</option><option value="never">Never</option></select></Field><button className={buttonClass} disabled={busy}>Save check-in</button></form><ErrorBanner message={error} />{saved && <p className="mt-2 text-sm text-green-700" role="status">Review saved.</p>}</section>
}
