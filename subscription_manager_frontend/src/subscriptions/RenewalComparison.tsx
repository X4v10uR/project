import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { buttonClass, currencyAmount as money, displayDate, ErrorBanner, Field, inputClass, panelClass, showError, subscriptionApi } from './shared'

export type ComparisonOption = { id: number; service_name: string; plan_name: string; currency: string }
type Scenario = { next_date: string | null; next_amount: string; total: string }
type Comparison = {
  option: 'annual' | 'downgrade' | 'cancel'
  currency: string
  from_date: string
  until_date: string
  effective_on: string
  cancel_by_date: string | null
  keep: Scenario
  alternative: Scenario
  next_payment_change: string
  total_savings: string
}

const labels = { annual: 'Switch to annual billing', downgrade: 'Downgrade to a lower monthly plan', cancel: 'Cancel' } as const

export function RenewalComparison({ options }: { options: ComparisonOption[] }) {
  const [id, setId] = useState('')
  const [option, setOption] = useState<Comparison['option']>('annual')
  const [price, setPrice] = useState('')
  const [result, setResult] = useState<Comparison | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const selected = options.find(item => String(item.id) === id)
  const missedCancellationDeadline = result?.option === 'cancel' && result.cancel_by_date !== null &&
    result.cancel_by_date < result.from_date

  function resetResult() { setResult(null); setError('') }

  async function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected || busy) return
    resetResult()
    setBusy(true)
    try {
      setResult(await api<Comparison>(`${subscriptionApi}${selected.id}/renewal-comparison/`, {
        method: 'POST',
        body: JSON.stringify({ option, ...(option === 'cancel' ? {} : { quoted_price: price }) }),
      }))
    } catch (e) { setError(showError(e)) } finally { setBusy(false) }
  }

  function difference(value: string, currency: string, positive: string, negative: string) {
    const delta = Number(value)
    return delta === 0 ? 'No difference' : `${money(Math.abs(delta), currency, 2)} ${delta > 0 ? positive : negative}`
  }

  return <section className={panelClass} aria-labelledby="renewal-comparison-title">
    <h2 id="renewal-comparison-title" className="font-bold">Compare renewal options</h2>
    <p className="mt-2 text-sm text-slate-600">Preview an active personal monthly subscription without changing it. Enter a quote in the subscription’s currency. This assumes the change starts at the next unrecorded renewal, without an immediate charge, fee, or credit.</p>
    {options.length === 0 ? <p className="mt-3 text-sm text-slate-600">No eligible personal monthly subscriptions. Shared subscriptions aren’t included.</p> :
      <form onSubmit={compare} className="mt-4 flex flex-wrap items-end gap-3">
        <Field label="Subscription to compare"><select className={inputClass} value={id} disabled={busy} required onChange={event => { setId(event.target.value); setPrice(''); resetResult() }}>
          <option value="">Choose a subscription</option>
          {options.map(item => <option key={item.id} value={item.id}>{item.service_name}{item.plan_name ? ` · ${item.plan_name}` : ''} ({item.currency})</option>)}
        </select></Field>
        <Field label="Alternative"><select className={inputClass} value={option} disabled={busy} onChange={event => { setOption(event.target.value as Comparison['option']); setPrice(''); resetResult() }}>
          {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></Field>
        {option !== 'cancel' && <Field label={`Quoted ${option === 'annual' ? 'annual' : 'monthly'} price${selected ? ` (${selected.currency})` : ''}`}><input className={inputClass} type="number" min="0" max="99999999.99" step="0.01" value={price} disabled={busy} required onChange={event => { setPrice(event.target.value); resetResult() }} /></Field>}
        <button className={buttonClass} disabled={busy || !selected}>{busy ? 'Comparing…' : 'Compare costs'}</button>
      </form>}
    <ErrorBanner message={error} />
    {result && <div className="mt-4 grid gap-3" role="status">
      <p className="text-sm text-slate-600">From {displayDate(result.from_date)} up to (not including) {displayDate(result.until_date)}.
        {!missedCancellationDeadline && <> Assumed change date: {displayDate(result.effective_on)}.</>}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">{([['Keep current plan', result.keep], [labels[result.option], result.alternative]] as const)
        .slice(0, missedCancellationDeadline ? 1 : 2).map(([label, scenario]) =>
        <div className="rounded-xl border border-slate-200 p-3" key={label}><h3 className="font-semibold">{label}</h3>
          <p className="text-sm">Next payment: {scenario.next_date ? `${money(scenario.next_amount, result.currency, 2)} on ${displayDate(scenario.next_date)}` : 'None in this preview'}</p>
          <p className="text-sm">12-month scheduled cost: <strong>{money(scenario.total, result.currency, 2)}</strong></p>
        </div>)}
        {missedCancellationDeadline && <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-amber-950">
          <h3 className="font-semibold">Cancellation timing unconfirmed</h3>
          <p className="text-sm">The recorded cancellation deadline has passed ({displayDate(result.cancel_by_date)}). Your next payment of {money(result.keep.next_amount, result.currency, 2)} on {displayDate(result.effective_on)} may still be due. Confirm the cancellation date with your provider before counting on any savings.</p>
        </div>}
      </div>
      {!missedCancellationDeadline && <>
        <p className="text-sm"><strong>Next payment:</strong> {difference(result.next_payment_change, result.currency, 'more', 'less')}. <strong>Over 12 months:</strong> {difference(result.total_savings, result.currency, 'less', 'more')}.</p>
        <p className="text-sm text-slate-600">{result.cancel_by_date ? `Recorded cancellation deadline: ${displayDate(result.cancel_by_date)}. ` : 'No cancellation deadline recorded. '}Confirm actual timing, fees, and eligibility with your provider.</p>
      </>}
    </div>}
  </section>
}
