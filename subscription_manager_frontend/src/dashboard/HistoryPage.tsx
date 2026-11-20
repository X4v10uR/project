import { ServiceIcon } from '../ServiceIcon'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { buttonClass, currencyAmount, displayDate, ErrorBanner, Field, inputClass, panelClass, showError } from '../subscriptions/shared'

const paymentLabels = { scheduled: 'Scheduled', paid: 'Paid', failed: 'Failed', refunded: 'Refunded' } as const
type Payment = keyof typeof paymentLabels
type Share = { id: number; name: string; amount: string; reimbursed: boolean; has_repayments: boolean }
type Charge = { shares_captured: boolean; payment_status: Payment; shares: Share[]; can_edit: boolean; id: number; service: string; date: string; amount: string; currency: string; source: 'renewal'; team: string | null }
type History = { results: Charge[]; count: number; totals_by_currency: Record<string, string>; paid_by_currency: Record<string, string>; previous: string | null; next: string | null }

function ChargeControls({ charge, reload }: { charge: Charge; reload: () => void }) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [shareChanges, setShareChanges] = useState<Record<number, boolean>>({})
  useEffect(() => setShareChanges({}), [charge.shares])
  async function update(endpoint: string, body: Record<string, unknown>, method = 'PATCH') {
    setSaving(true)
    setError('')
    try {
      await api(`/api/dashboard/history/${charge.id}/${endpoint}/`, { method, body: JSON.stringify(body) })
      reload()
      return true
    } catch (failure) {
      setError(showError(failure))
      return false
    } finally {
      setSaving(false)
    }
  }
  return <div className="grid min-w-32 gap-2">
    {charge.can_edit ? <select aria-label={`Payment status for ${charge.service}`} className={inputClass}
      value={charge.payment_status} disabled={saving} onChange={(event) => void update('payment', { payment_status: event.target.value })}>
      {Object.entries(paymentLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
    </select> : <span>{paymentLabels[charge.payment_status]}</span>}
    {charge.shares.length > 0 && <details><summary className="cursor-pointer">Reimbursements</summary>
      {charge.shares.map((share) => <label key={share.id} className="mt-2 flex items-center gap-2">
        <input type="checkbox" checked={shareChanges[share.id] ?? share.reimbursed} disabled={saving || !charge.can_edit || share.has_repayments}
          onChange={(event) => { const reimbursed = event.target.checked; setShareChanges(changes => ({ ...changes, [share.id]: reimbursed })); void update(`shares/${share.id}`, { reimbursed }).then(saved => { if (!saved) setShareChanges(changes => { const next = { ...changes }; delete next[share.id]; return next }) }) }} />
        {share.name} · {currencyAmount(share.amount, charge.currency)} reimbursed
      </label>)}
    </details>}
    {charge.shares.length > 0 && <Link className="text-sm font-semibold text-indigo-700 underline" to={`/planning/settlements/?scope=${charge.team ? 'teams' : 'personal'}`}>Manage repayments</Link>}
    {!charge.shares_captured && charge.can_edit && <details>
      <summary className="cursor-pointer">Add historical share</summary>
      <form className="mt-2 grid gap-2" onSubmit={(event) => {
        event.preventDefault()
        const fields = Object.fromEntries(new FormData(event.currentTarget))
        void update('shares', fields, 'POST')
      }}>
        <Field label="Participant name"><input className={inputClass} name="name" required maxLength={100} /></Field>
        <Field label={`Share (${charge.currency})`}><input className={inputClass} name="amount" type="number" step="0.01" min="0.01" required /></Field>
        <button className={buttonClass} disabled={saving}>Add share</button>
      </form>
    </details>}
    <ErrorBanner message={error} />
  </div>
}

export function HistoryPage() {
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const [result, setResult] = useState<{ query: string; data?: History; error?: string }>()
  const [retry, setRetry] = useState(0)
  const current = result?.query === query ? result : undefined
  const page = Number(params.get('page') || 1)

  useEffect(() => {
    const controller = new AbortController()
    api<History>(`/api/dashboard/history/?${query}`, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setResult({ query, data }) })
      .catch((error) => { if (!controller.signal.aborted) setResult({ query, error: showError(error) }) })
    return () => controller.abort()
  }, [query, retry])

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = new URLSearchParams()
    for (const [key, value] of new FormData(event.currentTarget)) {
      if (typeof value === 'string' && value.trim()) next.set(key, value.trim())
    }
    setParams(next)
  }

  function goToPage(number: number) {
    const next = new URLSearchParams(params)
    next.set('page', String(number))
    setParams(next)
  }

  return (
    <section className="mx-auto grid max-w-5xl gap-5 px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3"><h1 className="text-3xl font-bold tracking-tight">Charge history</h1><Link className={buttonClass} to={`/planning/reports/?${query}`}>Export charge history</Link></div>
      {params.has('charge') && <Link className="text-sm font-semibold underline" to={`/dashboard/history/?scope=${params.get('scope') === 'teams' ? 'teams' : 'personal'}`}>View all charges in this workspace</Link>}
      <form key={query} className={`${panelClass} grid items-end gap-3 sm:grid-cols-2 lg:grid-cols-5`} onSubmit={filter}>
        <Field label="Scope"><select className={inputClass} name="scope" defaultValue={params.get('scope') || 'personal'}><option value="personal">Personal</option><option value="teams">My teams</option></select></Field>
        <Field label="Service"><input className={inputClass} name="service" type="search" maxLength={100} defaultValue={params.get('service') || ''} /></Field>
        <Field label="From"><input className={inputClass} name="start" type="date" defaultValue={params.get('start') || ''} /></Field>
        <Field label="Through"><input className={inputClass} name="end" type="date" defaultValue={params.get('end') || ''} /></Field>
        <button className={buttonClass}>Apply filters</button>
      </form>
      {!current && <p role="status">Loading charges…</p>}
      {current?.error && <div className="grid justify-items-start gap-2"><ErrorBanner message={current.error} /><button className={buttonClass} onClick={() => setRetry(retry + 1)}>Try again</button></div>}
      {current?.data && <div className={panelClass}>
        {current.data.count === 0 ? <p>No charges match these filters.</p> : <>
          <h2 className="text-sm font-semibold text-slate-600">Total scheduled for these filters</h2>
          <ul className="mb-3 flex flex-wrap gap-4 text-2xl font-bold">
            {Object.entries(current.data.totals_by_currency).sort(([a], [b]) => a.localeCompare(b)).map(([code, total]) => (
              <li key={code}>{code} {total}</li>
            ))}
          </ul>
          {Object.keys(current.data.paid_by_currency).length > 0 && <p className="mb-3 text-sm font-semibold">Confirmed paid · {Object.entries(current.data.paid_by_currency).map(([code, value]) => currencyAmount(value, code)).join(' + ')}</p>}
          <p className="pb-3 text-sm text-slate-600">Charges are recorded from subscription schedules. Dates refer to the scheduled renewal.</p>
          <div className="overflow-x-auto"><table className="w-full text-left text-sm">
            <thead className="border-b text-slate-600"><tr><th className="p-2">Date</th><th className="p-2">Service</th><th className="p-2">Source</th><th className="p-2 text-right">Your amount</th><th className="p-2">Payment status</th></tr></thead>
            <tbody className="divide-y divide-slate-100">{current.data.results.map((charge) => <tr key={charge.id}>
              <td className="p-2"><time dateTime={charge.date}>{displayDate(charge.date)}</time></td>
              <td className="p-2 font-semibold"><span className="inline-flex items-center gap-2"><ServiceIcon name={charge.service} className="size-6" />{charge.service}</span>{charge.team && <span className="block text-xs font-normal">{charge.team}</span>}<Link className="mt-1 block text-xs font-medium text-indigo-700 underline" to={`/planning/receipts/?charge=${charge.id}`}>Receipts</Link></td>
              <td className="p-2">Scheduled renewal</td>
              <td className="whitespace-nowrap p-2 text-right font-semibold">{currencyAmount(charge.amount, charge.currency)} <small>{charge.currency}</small></td>
              <td className="p-2"><ChargeControls charge={charge} reload={() => setRetry((value) => value + 1)} /></td>
            </tr>)}</tbody>
          </table></div>
          {(current.data.previous || current.data.next) && <nav aria-label="History pages" className="mt-4 flex items-center justify-between gap-3">
            <button className={buttonClass} disabled={!current.data.previous} onClick={() => goToPage(page - 1)}>Previous</button>
            <span>Page {page}</span><button className={buttonClass} disabled={!current.data.next} onClick={() => goToPage(page + 1)}>Next</button>
          </nav>}
        </>}
      </div>}
    </section>
  )
}
