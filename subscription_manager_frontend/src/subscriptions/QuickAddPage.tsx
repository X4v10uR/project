import { ArrowLeft } from 'lucide-react'
import { ServiceIcon } from '../ServiceIcon'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../accounts/auth'
import { billingCycles, buttonClass, ErrorBanner, Field, inputClass, panelClass, primaryClass, showError } from './shared'

const presets = [['Netflix', 'Streaming'], ['Spotify', 'Music'], ['YouTube Premium', 'Streaming'], ['iCloud', 'Cloud'], ['Microsoft 365', 'Productivity'], ['Adobe Creative Cloud', 'Software'], ['GitHub', 'Software'], ['Gym membership', 'Fitness']]
export function QuickAddPage() {
  const navigate = useNavigate(); const { user } = useAuth(); const [params] = useSearchParams()
  const [service, setService] = useState(''); const [category, setCategory] = useState('Other')
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const team = params.get('team')
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('')
    const fields = Object.fromEntries(new FormData(event.currentTarget))
    try { await api('/api/subscriptions/', { method: 'POST', body: JSON.stringify({ ...fields, service_name: service, category, currency: user?.preferred_currency || 'USD', ...(team ? { team_id: Number(team) } : {}) }) }); navigate(team ? `/accounts/teams/${team}/` : '/subscriptions/', { state: { notice: 'Subscription added. You can add sharing, reminders, and other details anytime.' } }) } catch (e) { setError(showError(e)) } finally { setBusy(false) }
  }
  return <div className="mx-auto grid max-w-2xl gap-5 px-4 py-8 pb-28"><Link className="inline-flex items-center gap-2 justify-self-start text-sm font-semibold text-slate-500" to={team ? `/accounts/teams/${team}/` : '/subscriptions/'}><ArrowLeft size={16} aria-hidden />Back</Link><header><p className="text-sm font-semibold text-indigo-700">A small first step</p><h1 className="mt-1 text-3xl font-bold">Quick add a subscription</h1><p className="mt-3 text-slate-600">Choose a service, enter what you pay, and set the next payment. You can fill in the rest later.</p></header><section className={panelClass}><h2 className="mb-3 text-sm font-bold">Start with a common service</h2><div className="flex flex-wrap gap-2">{presets.map(([name, group]) => <button key={name} className={`${buttonClass} gap-2`} aria-pressed={service === name} onClick={() => { setService(name); setCategory(group) }}><ServiceIcon name={name} className="size-6" />{name}</button>)}</div></section><form className={`${panelClass} grid gap-4`} onSubmit={save}><ErrorBanner message={error} /><Field label="Service"><span className="relative"><ServiceIcon name={service} className="pointer-events-none absolute top-1/2 left-2 size-7 -translate-y-1/2" /><input className={`${inputClass} pl-11`} value={service} onChange={e => setService(e.target.value)} maxLength={100} required autoFocus /></span></Field><Field label={`Cost (${user?.preferred_currency || 'USD'})`}><input className={inputClass} name="cost" type="number" required min="0" step="0.01" placeholder="0.00" /></Field><Field label="Billing cycle"><select name="billing_cycle" className={inputClass} defaultValue="monthly">{billingCycles.map(([code, name]) => <option value={code} key={code}>{name}</option>)}</select></Field><Field label="Next payment"><input className={inputClass} type="date" name="start_date" required /></Field><button disabled={busy} className={primaryClass}>{busy ? 'Adding…' : 'Add subscription'}</button><Link className="text-center text-sm font-semibold text-indigo-700 underline" to={`/subscriptions/add/${team ? `?team=${team}` : ''}`}>Use the full form for currency, trials, sharing, and reminders</Link></form></div>
}
