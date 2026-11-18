import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, NavLink, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { buttonClass, currencyAmount as money, displayDate, ErrorBanner, Field, inputClass, panelClass, primaryClass, showError, subscriptionApi } from './shared'

type Scope = 'personal' | 'teams'
function PlanningLayout({ title, children }: { title: string; children: ReactNode }) {
  const [params, setParams] = useSearchParams()
  const scope = params.get('scope') === 'teams' ? 'teams' : 'personal'
  return <div className="mx-auto grid max-w-6xl gap-5 px-4 py-8 pb-28 sm:px-8">
    <header className="flex flex-wrap items-center justify-between gap-4"><div><p className="text-sm font-semibold text-indigo-700">Make room for what matters</p><h1 className="mt-1 text-3xl font-bold tracking-tight">{title}</h1></div><Link className={primaryClass} to="/subscriptions/quick-add/">Quick add</Link></header>
    <div className="flex flex-wrap items-center justify-between gap-4"><nav aria-label="Planning tools" className="flex flex-wrap gap-2">{[['insights', 'Insights'], ['calendar', 'Renewal calendar'], ['review', 'Review inbox'], ['settlements', 'Settlements']].map(([path, label]) => <NavLink className={({ isActive }) => `${buttonClass} ${isActive ? 'border-indigo-300 bg-indigo-50 text-indigo-800' : ''}`} key={path} to={`/planning/${path}/?scope=${scope}`}>{label}</NavLink>)}</nav>
    <Field label="Workspace"><select className={inputClass} value={scope} onChange={event => { const next = new URLSearchParams(params); next.set('scope', event.target.value); setParams(next) }}><option value="personal">Personal</option><option value="teams">Teams</option></select></Field></div>
    {children}
  </div>
}

function usePlanning<T>(path: string) {
  const [params] = useSearchParams()
  const scope: Scope = params.get('scope') === 'teams' ? 'teams' : 'personal'
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [version, setVersion] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setData(null); setError('')
    api<T>(`${subscriptionApi}${path}/?scope=${scope}`, { signal: controller.signal }).then(result => { if (!controller.signal.aborted) setData(result) }).catch(e => { if (!controller.signal.aborted) setError(showError(e)) })
    return () => controller.abort()
  }, [path, scope, version])
  return { data, error, scope, reload: () => setVersion(v => v + 1) }
}

type InsightData = { totals: { currency: string; monthly_commitment: string; annual_projection: string; month_scheduled: string; previous_scheduled: string; month_paid: string; previous_paid: string; change: string; reasons: { service: string; change: string }[] }[]; categories: { currency: string; category: string; monthly: string }[]; explanation: string }
export function InsightsPage() {
  const { data, error } = usePlanning<InsightData>('insights')
  return <PlanningLayout title="Spending insights"><ErrorBanner message={error} />{!data && !error && <p role="status">Loading insights…</p>}{data && <>
    {!data.totals.length && <div className={panelClass}><h2 className="text-xl font-bold">Start with your first subscription</h2><p className="mt-2 text-slate-600">Add a service to see your commitment and forecast.</p></div>}
    {data.totals.map(row => <section key={row.currency} className="grid gap-4"><h2 className="text-lg font-bold">{row.currency} spending</h2><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[['Monthly commitment', row.monthly_commitment], ['Next 12 months scheduled', row.annual_projection], ['This month scheduled', row.month_scheduled], ['This month confirmed paid', row.month_paid]].map(([label, value]) => <div className={panelClass} key={label}><p className="text-sm text-slate-600">{label}</p><p className="mt-2 text-2xl font-bold">{money(value, row.currency)}</p></div>)}</div>
    <div className="grid gap-4 md:grid-cols-2"><article className={panelClass}><h3 className="font-bold">Monthly category breakdown</h3><ul className="mt-4 grid gap-3">{data.categories.filter(c => c.currency === row.currency).map(c => <li key={c.category}><div className="flex justify-between gap-3 text-sm"><span>{c.category}</span><strong>{money(c.monthly, row.currency)}</strong></div><div className="mt-1 h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-indigo-500" style={{ width: `${Number(row.monthly_commitment) ? Number(c.monthly) / Number(row.monthly_commitment) * 100 : 0}%` }} /></div></li>)}</ul></article>
    <article className={panelClass}><h3 className="font-bold">What changed this month</h3><p className="mt-2 text-2xl font-bold">{Number(row.change) >= 0 ? '+' : ''}{money(row.change, row.currency)}</p><p className="mt-1 text-sm text-slate-600">Previous month: {money(row.previous_scheduled, row.currency)} scheduled · {money(row.previous_paid, row.currency)} paid</p><ul className="mt-4 grid gap-2 text-sm">{row.reasons.map(reason => <li className="flex justify-between gap-3" key={reason.service}><span>{reason.service}</span><strong>{Number(reason.change) >= 0 ? '+' : ''}{money(reason.change, row.currency)}</strong></li>)}</ul></article></div></section>)}
    <p className="text-sm text-slate-600">{data.explanation} Projections include known price changes and pauses. Currencies are kept separate.</p>
  </>}</PlanningLayout>
}

type CalendarEvent = { id: string; subscription_id: number; team_id: number | null; service: string; date: string; kind: string; amount: string | null; currency: string }
const eventLabels: Record<string, string> = { payment: 'Payment', trial: 'Trial ends', deadline: 'Cancel by', pause: 'Pause begins', resume: 'Resume' }
function dateKey(date: Date) { return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }
export function RenewalCalendarPage() {
  const { data, error, scope } = usePlanning<{ events: CalendarEvent[] }>('calendar')
  const [month, setMonth] = useState(() => { const now = new Date(); return new Date(now.getFullYear(), now.getMonth(), 1) })
  const [selected, setSelected] = useState('')
  const start = new Date(month.getFullYear(), month.getMonth(), 1 - month.getDay())
  const monthEvents = data?.events.filter(e => e.date.startsWith(dateKey(month).slice(0, 7))) ?? []
  const shown = selected ? monthEvents.filter(e => e.date === selected) : monthEvents
  function move(delta: number) { setMonth(new Date(month.getFullYear(), month.getMonth() + delta, 1)); setSelected('') }
  return <PlanningLayout title="Renewal calendar"><ErrorBanner message={error} /><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm text-slate-600">Payments, trials, and cancellation deadlines for the next 12 months.</p><a className={buttonClass} href={`${subscriptionApi}calendar/export/?scope=${scope}`}>Export calendar (.ics)</a></div>
  <section className={panelClass}><div className="mb-5 flex items-center justify-between gap-2"><button className={buttonClass} aria-label="Previous month" disabled={month <= new Date(new Date().getFullYear(), new Date().getMonth(), 1)} onClick={() => move(-1)}>←</button><h2 className="text-xl font-bold">{month.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</h2><button className={buttonClass} aria-label="Next month" disabled={month >= new Date(new Date().getFullYear() + 1, new Date().getMonth(), 1)} onClick={() => move(1)}>→</button></div><div className="grid grid-cols-7">{['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => <div key={day} className="pb-2 text-center text-xs font-bold text-slate-500">{day}</div>)}{Array.from({ length: 42 }, (_, index) => { const day = new Date(start.getFullYear(), start.getMonth(), start.getDate() + index); const key = dateKey(day); const events = data?.events.filter(e => e.date === key) ?? []; return <button key={key} aria-label={`${displayDate(key)}, ${events.length} events`} aria-pressed={selected === key} onClick={() => setSelected(selected === key ? '' : key)} className={`min-h-20 min-w-0 border border-slate-100 p-1 text-left sm:p-2 ${day.getMonth() !== month.getMonth() ? 'text-slate-300' : ''} ${selected === key ? 'bg-indigo-50 ring-1 ring-indigo-400' : ''}`}><span className="text-sm">{day.getDate()}</span>{events.slice(0, 2).map(event => <span key={event.id} className={`mt-1 block truncate rounded px-1 text-[10px] sm:text-xs ${event.kind === 'payment' ? 'bg-indigo-50 text-indigo-800' : 'bg-amber-50 text-amber-800'}`}>{event.service}</span>)}{events.length > 2 && <span className="text-xs">+{events.length - 2}</span>}</button> })}</div></section>
  <section className={panelClass}><h2 className="mb-3 font-bold">{selected ? displayDate(selected) : 'This month'}</h2>{!data && !error && <p role="status">Loading renewals…</p>}{data && !shown.length && <p className="text-sm text-slate-600">No scheduled events in this selection.</p>}<ul className="divide-y divide-slate-100">{shown.map(event => <li key={event.id} className="flex flex-wrap items-center justify-between gap-3 py-3"><div><Link className="font-semibold underline" to={event.team_id ? `/accounts/teams/${event.team_id}/` : `/subscriptions/${event.subscription_id}/edit/`}>{event.service}</Link><p className="text-sm text-slate-500">{displayDate(event.date)} · {eventLabels[event.kind]}</p></div>{event.amount !== null && <strong>{money(event.amount, event.currency)}</strong>}</li>)}</ul></section></PlanningLayout>
}

type ReviewItem = { id: number; service: string; currency: string; reasons: string[]; monthly_saving: string; can_edit: boolean }
export function ReviewInboxPage() {
  const { data, error, reload, scope } = usePlanning<{ items: ReviewItem[] }>('review')
  const [selected, setSelected] = useState<number[]>([])
  const [failure, setFailure] = useState('')
  const [busy, setBusy] = useState(false)
  const [usage, setUsage] = useState('sometimes')
  useEffect(() => setSelected([]), [scope])
  const totals: Record<string, number> = {}
  data?.items.filter(item => selected.includes(item.id)).forEach(item => { totals[item.currency] = (totals[item.currency] ?? 0) + Number(item.monthly_saving) })
  async function act(action: 'pause' | 'review', ids: number[]) {
    setBusy(true); setFailure('')
    try { await api(`${subscriptionApi}review/action/`, { method: 'POST', body: JSON.stringify({ action, ids, usage_rating: usage }) }); setSelected([]); reload() } catch (e) { setFailure(showError(e)) } finally { setBusy(false) }
  }
  return <PlanningLayout title="Subscription review inbox"><ErrorBanner message={error || failure} /><div className={panelClass}><h2 className="font-bold">Turn upcoming renewals into decisions</h2><p className="mt-2 text-sm text-slate-600">Review trials, duplicates, old subscriptions, and services you rarely use. Pausing here updates your tracking; arrange the pause with your provider too.</p><div className="mt-4 flex flex-wrap items-end gap-3"><Field label="Usage check-in"><select className={inputClass} value={usage} onChange={event => setUsage(event.target.value)}><option value="often">Often</option><option value="sometimes">Sometimes</option><option value="rarely">Rarely</option><option value="never">Never</option></select></Field><button className={buttonClass} disabled={!selected.length || busy} onClick={() => void act('review', selected)}>Mark selected reviewed</button><button className={primaryClass} disabled={!selected.length || busy} onClick={() => void act('pause', selected)}>Pause selected</button></div><p className="mt-3 text-sm font-semibold" aria-live="polite">Monthly commitment reduced by: {Object.entries(totals).map(([code, value]) => money(value, code)).join(' · ') || 'Select subscriptions to preview savings'}</p></div>
  {!data && !error && <p role="status">Loading review tasks…</p>}{data && !data.items.length && <p className={panelClass}>You’re all caught up. New review tasks appear as deadlines approach.</p>}{data?.items.map(item => <article className={panelClass} key={item.id}><div className="flex items-start gap-3"><input aria-label={`Select ${item.service}`} type="checkbox" disabled={!item.can_edit || busy} checked={selected.includes(item.id)} onChange={event => setSelected(ids => event.target.checked ? [...ids, item.id] : ids.filter(id => id !== item.id))} className="mt-1 size-4" /><div className="flex-1"><h2 className="text-lg font-bold">{item.service}</h2><ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-600">{item.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul><p className="mt-3 text-sm font-semibold">{money(item.monthly_saving, item.currency)} / month potential saving</p><div className="mt-3 flex flex-wrap gap-2">{item.can_edit && <><Link className={buttonClass} to={`/subscriptions/${item.id}/edit/`}>Manage subscription</Link><button className={buttonClass} disabled={busy} onClick={() => void act('review', [item.id])}>Mark reviewed</button></>}</div></div></div></article>)}</PlanningLayout>
}

type Balance = { debtor: string; creditor: string; team: string | null; currency: string; total: string; repaid: string; outstanding: string; shares: { id: number; service: string; date: string; outstanding: string; can_edit: boolean; repayments: { amount: string; note: string; date: string }[] }[] }
function RepaymentForm({ share, currency, reload }: { share: Balance['shares'][number]; currency: string; reload: () => void }) {
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  async function repay(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setBusy(true); setError(''); const form = event.currentTarget; try { await api(`${subscriptionApi}settlements/${share.id}/repay/`, { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(form))) }); reload() } catch (e) { setError(showError(e)) } finally { setBusy(false) } }
  return <form onSubmit={repay} className="mt-3 grid gap-2"><div className="flex flex-wrap items-end gap-2"><Field label={`Repayment (${currency})`}><input name="amount" className={inputClass} type="number" min="0.01" max={share.outstanding} step="0.01" required /></Field><Field label="Note (optional)"><input name="note" maxLength={255} className={inputClass} /></Field><button className={buttonClass} disabled={busy}>Record repayment</button></div><ErrorBanner message={error} /></form>
}
export function SettlementsPage() {
  const { data, error, reload } = usePlanning<{ balances: Balance[] }>('settlements')
  return <PlanningLayout title="Shared settlement balances"><ErrorBanner message={error} /><p className="text-sm text-slate-600">Balances combine participant shares across confirmed-paid charges. Record partial repayments as money comes in. Payers, teams, and currencies stay separate.</p>{!data && !error && <p role="status">Loading settlements…</p>}{data && !data.balances.length && <p className={panelClass}>No shared paid charges yet. Confirm a shared charge as paid in History to start tracking repayments.</p>}{data?.balances.map((row, index) => <section key={index} className={panelClass}><div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-lg font-bold">{row.debtor} owes {row.creditor}</h2><p className="text-sm text-slate-500">{row.team ?? 'Personal'} · Total {money(row.total, row.currency)} · Repaid {money(row.repaid, row.currency)}</p></div><strong className="text-xl">{money(row.outstanding, row.currency)}</strong></div><div className="mt-4 grid gap-3">{row.shares.map(share => <details key={share.id} className="rounded-xl border border-slate-200 p-3"><summary className="cursor-pointer text-sm font-semibold">{share.service} · {displayDate(share.date)} · {money(share.outstanding, row.currency)} remaining</summary>{share.can_edit && Number(share.outstanding) > 0 && <RepaymentForm share={share} currency={row.currency} reload={reload} />}<ul className="mt-2 space-y-2 text-sm text-slate-600">{share.repayments.map((repayment, i) => <li key={i}>{money(repayment.amount, row.currency)} · {new Date(repayment.date).toLocaleDateString()} {repayment.note && `· ${repayment.note}`}</li>)}</ul></details>)}</div></section>)}</PlanningLayout>
}
