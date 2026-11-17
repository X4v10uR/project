import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { buttonClass, currencyAmount, displayDate, ErrorBanner, Field, inputClass, panelClass, showError } from '../subscriptions/shared'

type Charge = { id: number; service: string; date: string; amount: string; currency: string; source: 'renewal'; team: string | null }
type History = { results: Charge[]; count: number; totals_by_currency: Record<string, string>; previous: string | null; next: string | null }

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
      <h1 className="text-3xl font-bold tracking-tight">Charge history</h1>
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
          <p className="pb-3 text-sm text-slate-600">Charges are recorded from subscription schedules. Dates refer to the scheduled renewal.</p>
          <div className="overflow-x-auto"><table className="w-full text-left text-sm">
            <thead className="border-b text-slate-600"><tr><th className="p-2">Date</th><th className="p-2">Service</th><th className="p-2">Source</th><th className="p-2 text-right">Amount</th></tr></thead>
            <tbody className="divide-y divide-slate-100">{current.data.results.map((charge) => <tr key={charge.id}>
              <td className="p-2"><time dateTime={charge.date}>{displayDate(charge.date)}</time></td>
              <td className="p-2 font-semibold">{charge.service}{charge.team && <span className="block text-xs font-normal">{charge.team}</span>}</td>
              <td className="p-2">Scheduled renewal</td>
              <td className="whitespace-nowrap p-2 text-right font-semibold">{currencyAmount(charge.amount, charge.currency)} <small>{charge.currency}</small></td>
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
