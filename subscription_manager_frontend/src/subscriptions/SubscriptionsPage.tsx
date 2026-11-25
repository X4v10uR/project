import { SavedRenewal } from './SavedRenewal'
import { ServiceIcon } from '../ServiceIcon'
import { Download, Plus, Search, Upload, Zap } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { CredentialReveal } from '../accounts/SecuritySettings'
import {
  billingCycles, buttonClass, currencyAmount, dangerClass, displayCycle, displayDate, ErrorBanner,
  Field, inputClass, Modal, panelClass, primaryClass, showError, subscriptionApi, subscriptionPath,
  subscriptionStatuses, type Subscription, type SubscriptionDetails,
} from './shared'

interface Portfolio {
  subscriptions: Subscription[]
  stats: { total: number; active: number; paused: number; monthly_spend_display: string }
  burn_metrics: {
    active_monthly_spend_display: string
    tracked_monthly_spend_display: string
    active_count: number
    tracked_count: number
    spend_is_mixed: boolean
    active_share_percent: number
  }
  details: Record<string, SubscriptionDetails>
}

const statusColors: Record<string, string> = {
  active: 'bg-emerald-50 text-emerald-800',
  paused: 'bg-amber-50 text-amber-800',
  cancelled: 'bg-slate-100 text-slate-600',
}

function FilterSelect({ label, name, selection, choices }: {
  label: string; name: string; selection: URLSearchParams; choices: string[][]
}) {
  return (
    <label>
      <span className="sr-only">{label}</span>
      <select className={inputClass} name={name} defaultValue={selection.get(name) ?? ''}>
        {choices.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
      </select>
    </label>
  )
}

function SubscriptionCard({ subscription, details, onSelect }: { subscription: Subscription; details: SubscriptionDetails; onSelect: () => void }) {
  const foreground = details.card_text_is_light ? 'text-white' : 'text-slate-950'
  return (
    <button type="button" onClick={onSelect} className={`flex min-h-43 w-full flex-col rounded-2xl p-5 text-left transition hover:-translate-y-0.5 hover:shadow-md ${foreground}`} style={{ backgroundColor: details.card_color }}>
      <span className="flex w-full items-center justify-between gap-3">
        <ServiceIcon name={subscription.service_name} />
        <span className={`rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${statusColors[subscription.current_status] ?? 'bg-white/60'}`}>{subscription.current_status}</span>
      </span>
      <span className="mt-4 text-lg font-bold">{subscription.service_name}</span>
      <span className="text-sm font-medium opacity-85">{subscription.plan_name || subscription.category}</span>
      <span className="mt-4 flex w-full flex-wrap items-end justify-between gap-x-4 gap-y-1">
        <span className="text-xl font-bold">{currencyAmount(subscription.current_user_cost, subscription.currency)} <span className="text-xs font-medium opacity-85">{displayCycle(subscription.billing_cycle)}</span></span>
        <span className="text-xs font-medium opacity-85">{displayDate(details.renewal_date || null)}</span>
      </span>
    </button>
  )
}

function Detail({ subscription, details, onClose, onUpdated, initiallyDeleting }: {
  subscription: Subscription; details: SubscriptionDetails; onClose: () => void; onUpdated: () => void; initiallyDeleting: boolean
}) {
  const [deleting, setDeleting] = useState(initiallyDeleting)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const url = `${subscriptionApi}${subscription.id}/`

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (error) {
      setError(showError(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal title={deleting ? `Delete ${subscription.service_name}?` : <span className="flex items-center gap-2"><ServiceIcon name={subscription.service_name} className="size-8" />{subscription.service_name}</span>} onClose={onClose}>
      <div className="grid gap-4">
        <ErrorBanner message={error} />
        {deleting ? (
          <>
            <p className="text-sm text-slate-600">This will remove the subscription and its renewal reminders.</p>
            <div className="flex justify-end gap-2">
              <button className={buttonClass} disabled={busy} onClick={() => setDeleting(false)}>Cancel</button>
              <button className={dangerClass} disabled={busy} onClick={() => void run(async () => {
                await api(url, { method: 'DELETE' })
                onUpdated()
                onClose()
              })}>Delete subscription</button>
            </div>
          </>
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-4 rounded-2xl bg-slate-50 p-4 text-sm">
              {subscription.trial_end_date && <div><dt>First paid date</dt><dd>{displayDate(subscription.trial_end_date)}</dd></div>}
              {subscription.cancel_by_date && <div><dt>Cancel by</dt><dd>{displayDate(subscription.cancel_by_date)}</dd></div>}
              <div><dt className="text-slate-500">Your cost</dt><dd className="font-semibold">{currencyAmount(subscription.current_user_cost, subscription.currency)}</dd></div>
              <div><dt className="text-slate-500">Billing cycle</dt><dd className="font-semibold">{details.billing_cycle_detail}</dd></div>
              <div><dt className="text-slate-500">Renewal date</dt><dd className="font-semibold">{displayDate(details.renewal_date || null)}</dd></div>
              <div><dt className="text-slate-500">Payment card</dt><dd className="font-semibold">{details.card_last4 ? `${subscription.card_nickname} · ${details.card_last4}` : 'Unassigned'}</dd></div>
              {subscription.is_shared && <div><dt className="text-slate-500">Total cost</dt><dd className="font-semibold">{currencyAmount(subscription.current_cost, subscription.currency)}</dd></div>}
              {subscription.account_email && <div><dt className="text-slate-500">Account email</dt><dd className="break-all font-semibold">{subscription.account_email}</dd></div>}
            </dl>
            {subscription.cancellation_state !== 'none' && <div className="rounded-xl bg-amber-50 p-3 text-sm"><p className="font-semibold">Cancellation {subscription.cancellation_state}</p>{subscription.access_until && <p>Access continues until {displayDate(subscription.access_until)}</p>}{subscription.cancellation_notes && <p className="mt-1 whitespace-pre-wrap">{subscription.cancellation_notes}</p>}</div>}
            {subscription.cancellation_url && <a className={buttonClass} href={subscription.cancellation_url} target="_blank" rel="noreferrer">Open provider cancellation page ↗</a>}
            {subscription.is_shared && (
              <div className="text-sm"><h3 className="font-bold">Participants</h3><ul className="mt-1 divide-y divide-slate-100">{subscription.participants.map((person, index) => <li key={`${person.name}-${index}`} className="flex justify-between gap-3 py-1.5"><span>{person.name}</span><span>{currencyAmount(person.share_amount ?? '0', subscription.currency)}</span></li>)}</ul></div>
            )}
            {subscription.notes && <p className="whitespace-pre-wrap break-words text-sm text-slate-600">{subscription.notes}</p>}
            {subscription.has_password && (
              <CredentialReveal url={`${url}password/`} />
            )}
            <div>
              <h3 className="mb-1 text-sm font-bold">Payment history</h3>
              {details.history.length ? <ul className="divide-y divide-slate-100 text-sm">{details.history.map((payment) => <li key={payment.charged_for_date} className="flex justify-between gap-3 py-2"><span>{payment.charged_for_date_display} · {payment.payment_status}</span><span className="font-semibold">{payment.amount_display}</span></li>)}</ul> : <p className="text-sm text-slate-500">No recorded payments yet.</p>}
            </div>
            <Field label="Status">
              <select className={inputClass} value={subscription.current_status} disabled={busy} onChange={(event) => {
                const status = event.target.value
                void run(async () => {
                  await api(`${url}status/`, { method: 'POST', body: JSON.stringify({ status }) })
                  onUpdated()
                })
              }}>
                {subscriptionStatuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </Field>
            <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 pt-4">
              <button className={buttonClass} disabled={busy} onClick={() => setDeleting(true)}>Delete</button>
              <Link className={primaryClass} to={`${subscriptionPath}${subscription.id}/edit/`}>Edit subscription</Link>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}

export function SubscriptionsPage() {
  const [query, setQuery] = useSearchParams()
  const location = useLocation()
  const navigate = useNavigate()
  const [result, setResult] = useState<{ filters: string; portfolio?: Portfolio; error?: string }>()
  const [revision, setRevision] = useState(0)
  const selectedId = Number(query.get('subscription'))
  const filters = new URLSearchParams(query)
  filters.delete('subscription')
  filters.delete('action')
  const queryString = filters.toString()
  const portfolio = result?.filters === queryString ? result.portfolio : undefined
  const error = result?.filters === queryString ? result.error : undefined

  useEffect(() => {
    const controller = new AbortController()
    api<Portfolio>(`${subscriptionApi}?${queryString}`, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ filters: queryString, portfolio: data })
      })
      .catch((error) => {
        if (!controller.signal.aborted) setResult({ filters: queryString, error: showError(error) })
      })
    return () => controller.abort()
  }, [queryString, revision])

  function openSubscription(id: number) {
    const params = new URLSearchParams(filters)
    params.set('subscription', String(id))
    setQuery(params, { state: { ...location.state, openedFromList: true } })
  }

  function closeSubscription() {
    if (location.state?.openedFromList) navigate(-1)
    else setQuery(filters, { replace: true, state: location.state })
  }

  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const params = new URLSearchParams()
    for (const [name, value] of new FormData(event.currentTarget)) {
      if (typeof value === 'string' && value.trim()) params.set(name, value.trim())
    }
    setQuery(params)
  }

  const selected = portfolio?.subscriptions.find((subscription) => subscription.id === selectedId)

  return (
    <section className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">Subscriptions</h1>
        <div className="flex flex-wrap gap-2">
          <a className={`${buttonClass} gap-2`} href={`${subscriptionApi}export/csv/?${queryString}`}><Download size={16} /> Export CSV</a>
          <Link className={`${buttonClass} gap-2`} to={`${subscriptionPath}import/`}><Upload size={18} aria-hidden />Import CSV</Link>
          <Link className={`${primaryClass} gap-2`} to={`${subscriptionPath}add/`}><Plus size={18} /> Add subscription</Link>
          <Link className={`${buttonClass} gap-2`} to="/subscriptions/quick-add/"><Zap size={18} aria-hidden />Quick add</Link>
        </div>
      </header>
      {error && (
        <div className="grid justify-items-start gap-2">
          <ErrorBanner message={error} />
          <button className={buttonClass} onClick={() => setRevision((value) => value + 1)}>Try again</button>
        </div>
      )}
      {typeof location.state?.notice === 'string' && <p role="status" className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">{location.state.notice}</p>}
      {portfolio?.subscriptions.some(item => item.id === location.state?.savedSubscriptionId) && <SavedRenewal subscriptionId={location.state.savedSubscriptionId} />}
      {portfolio && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Subscription summary">
          {[
            ['Total', portfolio.stats.total], ['Active', portfolio.stats.active],
            ['Paused', portfolio.stats.paused], ['Monthly spend', portfolio.stats.monthly_spend_display],
          ].map(([label, value]) => (
            <div className={panelClass} key={label}><p className="text-sm font-semibold text-slate-600">{label}</p><p className="mt-2 text-2xl font-bold tracking-tight text-slate-950">{value}</p></div>
          ))}
        </div>
      )}
      <form key={queryString} onSubmit={filter} className={`${panelClass} grid gap-3 sm:grid-cols-2 xl:grid-cols-[1.45fr_repeat(5,minmax(0,1fr))_auto]`}>
        <label className="relative">
          <span className="sr-only">Search subscriptions</span>
          <Search size={17} className="pointer-events-none absolute top-3 left-3 text-slate-400" />
          <input className={`${inputClass} pl-9`} name="q" type="search" defaultValue={query.get('q') ?? ''} placeholder="Search subscriptions" />
        </label>
        <FilterSelect label="Status" name="status" selection={query} choices={[["", "All statuses"], ...subscriptionStatuses]} />
        <FilterSelect label="Billing cycle" name="cycle" selection={query} choices={[["", "All cycles"], ...billingCycles]} />
        <FilterSelect label="Sharing" name="shared" selection={query} choices={[["", "All access"], ["false", "Personal"], ["true", "Shared"]]} />
        <FilterSelect label="Renewal window" name="due_within" selection={query} choices={[["", "Any renewal"], ["7", "Next 7 days"], ["14", "Next 14 days"], ["30", "Next 30 days"]]} />
        <FilterSelect label="Sort by" name="sort" selection={query} choices={[["", "By renewal"], ["cost", "By cost"], ["service_name", "By name"]]} />
        <button className={buttonClass}>Apply</button>
      </form>
      {!portfolio && !error && <p role="status" className="text-sm text-slate-600">Loading subscriptions…</p>}
      {portfolio && (
        <>
          {portfolio.subscriptions.length ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {portfolio.subscriptions.map((subscription) => (
                <SubscriptionCard key={subscription.id} subscription={subscription} details={portfolio.details[subscription.id]} onSelect={() => openSubscription(subscription.id)} />
              ))}
            </div>
          ) : (
            <div className={`${panelClass} grid justify-items-center gap-3 py-12`}>
              <h2 className="text-lg font-bold">{queryString ? 'No matching subscriptions' : 'No subscriptions yet'}</h2>
              {queryString ? <button className={buttonClass} onClick={() => setQuery({})}>Clear filters</button> : <Link className={primaryClass} to={`${subscriptionPath}add/`}>Add subscription</Link>}
            </div>
          )}
          {portfolio.burn_metrics.tracked_count > 0 && (
            <div className={panelClass}>
              <div className="flex flex-wrap items-baseline justify-between gap-4">
                <h2 className="font-bold">Monthly burn rate</h2>
                <p className="text-sm text-slate-600">{portfolio.burn_metrics.active_monthly_spend_display} active of {portfolio.burn_metrics.tracked_monthly_spend_display} tracked</p>
              </div>
              <progress aria-label="Active share of monthly burn rate" className="mt-3 h-3 w-full overflow-hidden rounded-full accent-indigo-600" max={100} value={portfolio.burn_metrics.active_share_percent} />
              <p className="mt-2 text-xs text-slate-600">{portfolio.burn_metrics.active_count} of {portfolio.burn_metrics.tracked_count} subscriptions active</p>
            </div>
          )}
        </>
      )}
      {selected && portfolio?.details[selected.id] && <Detail key={selected.id} subscription={selected} details={portfolio.details[selected.id]} initiallyDeleting={query.get('action') === 'delete'} onClose={closeSubscription} onUpdated={() => setRevision((value) => value + 1)} />}
    </section>
  )
}
