import { ArrowLeft, Plus, Trash2 } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import {
  buttonClass, ErrorBanner, Field, inputClass, panelClass, primaryClass, showError,
  subscriptionApi, subscriptionPath, type Card, type Subscription,
} from './shared'

interface Options {
  cards: Card[]
  default_reminder_offset: number
  statuses: [string, string][]
  cycles: [string, string][]
  categories: string[]
  colors: string[]
  prefill: Partial<Pick<Subscription, 'service_name' | 'category' | 'billing_cycle' | 'plan_name'>>
  team: { id: number; name: string; can_create: boolean } | null
}

function localDate() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function SubscriptionEditor({ options, subscription }: { options: Options; subscription: Subscription | null }) {
  const navigate = useNavigate()
  const [shared, setShared] = useState(subscription?.is_shared ?? false)
  const [split, setSplit] = useState(subscription?.split_type ?? 'equal')
  const [color, setColor] = useState(subscription?.display_color ?? '')
  const [remindersEnabled, setRemindersEnabled] = useState(subscription?.reminders_enabled ?? true)
  const [offsets, setOffsets] = useState<number[]>(subscription?.reminder_offsets ?? [])
  const [offsetInput, setOffsetInput] = useState('3')
  const [participants, setParticipants] = useState(() => (subscription?.participants ?? []).map((person, id) => ({ id, name: person.name, share: person.share_amount ?? '' })))
  const [nextParticipantId, setNextParticipantId] = useState(participants.length)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const teamId = subscription?.team ?? options.team?.id
  const pending = !subscription && options.team && !options.team.can_create
  const backPath = teamId ? `/accounts/teams/${teamId}/` : subscriptionPath

  function addParticipant() {
    setParticipants((people) => [...people, { id: nextParticipantId, name: '', share: '' }])
    setNextParticipantId((id) => id + 1)
  }

  function updateParticipant(id: number, field: 'name' | 'share', value: string) {
    setParticipants((people) => people.map((person) => person.id === id ? { ...person, [field]: value } : person))
  }

  function addOffset() {
    const days = Number(offsetInput)
    if (Number.isInteger(days) && days >= 1 && days <= 30 && !offsets.includes(days)) {
      setOffsets((current) => [...current, days])
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSaving(true)
    const fields = Object.fromEntries(new FormData(event.currentTarget))
    const payload = {
      ...fields,
      team_id: teamId,
      display_color: color,
      is_shared: shared,
      split_type: split,
      reminders_enabled: remindersEnabled,
      reminder_offsets: offsets,
      participants: shared ? participants.map(({ name, share }) => ({ name, share: split === 'custom' ? share || '0' : '0' })) : [],
    }

    try {
      const response = await api<Subscription | { request_id: number }>(
        subscription ? `${subscriptionApi}${subscription.id}/` : subscriptionApi,
        { method: subscription ? 'PUT' : 'POST', body: JSON.stringify(payload) },
      )
      navigate(backPath, { state: { notice: 'request_id' in response ? 'Subscription request submitted.' : 'Subscription saved.' } })
    } catch (error) {
      setError(showError(error))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={save} className="grid gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-indigo-700" to={backPath}><ArrowLeft size={16} /> {teamId ? 'Back to team' : 'Back to subscriptions'}</Link>
          <h1 className="text-3xl font-bold tracking-tight text-slate-950">{subscription ? 'Edit subscription' : 'Add subscription'}</h1>
          {options.team && <p className="mt-1 text-sm text-slate-600">{options.team.name}</p>}
        </div>
        <button disabled={saving} className={primaryClass}>{saving ? 'Saving…' : pending ? 'Submit request' : 'Save subscription'}</button>
      </div>
      {pending && <p className="rounded-xl bg-indigo-50 p-3 text-sm text-indigo-800">A team owner must approve your subscription request.</p>}
      <ErrorBanner message={error} />

      <section className={`${panelClass} grid gap-4`}>
        <h2 className="text-lg font-bold">Subscription details</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Service name"><input autoComplete="off" name="service_name" className={inputClass} required maxLength={100} defaultValue={subscription?.service_name ?? options.prefill.service_name} placeholder="e.g. Netflix" /></Field>
          <Field label="Plan name"><input name="plan_name" className={inputClass} maxLength={100} defaultValue={subscription?.plan_name ?? options.prefill.plan_name ?? ''} placeholder="e.g. Premium" /></Field>
          <Field label="Category"><input list="subscription-categories" name="category" className={inputClass} required maxLength={50} defaultValue={subscription?.category ?? options.prefill.category} placeholder="e.g. Streaming" /></Field>
          <datalist id="subscription-categories">{options.categories.map((category) => <option key={category} value={category} />)}</datalist>
          <Field label="Status"><select name="status" className={inputClass} defaultValue={subscription?.status ?? 'active'}>{options.statuses.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
        </div>
        <fieldset className="grid gap-2 text-sm">
          <legend className="mb-2 font-semibold text-slate-700">Card color</legend>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className={`${buttonClass} px-3 py-1.5`} aria-pressed={!color} onClick={() => setColor('')}>Default</button>
            {options.colors.map((value) => <button key={value} type="button" aria-label={`Use ${value}`} aria-pressed={color === value} className={`size-8 rounded-full border border-black/15 ${color === value ? 'ring-2 ring-indigo-600 ring-offset-2' : ''}`} style={{ backgroundColor: value }} onClick={() => setColor(value)} />)}
            <label className="inline-flex items-center gap-2 font-medium"><input type="color" aria-label="Custom color" value={color || options.colors[0]} onChange={(event) => setColor(event.target.value.toUpperCase())} className="size-8 cursor-pointer rounded-lg" /> Custom</label>
          </div>
        </fieldset>
      </section>

      <section className={`${panelClass} grid gap-4`}>
        <h2 className="text-lg font-bold">Billing</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Cost"><input name="cost" className={inputClass} type="number" required min="0" step="0.01" defaultValue={subscription?.cost} placeholder="0.00" /></Field>
          <Field label="Currency code"><input name="currency" className={inputClass} maxLength={3} pattern="[A-Za-z]{3}" required defaultValue={subscription?.currency ?? 'USD'} /></Field>
          <Field label="Billing cycle"><select className={inputClass} name="billing_cycle" defaultValue={subscription?.billing_cycle ?? options.prefill.billing_cycle ?? 'monthly'}>{options.cycles.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
          <Field label="Start date"><input type="date" name="start_date" className={inputClass} required defaultValue={subscription?.start_date ?? localDate()} /></Field>
          <Field label="Renewal time"><input type="time" name="renewal_time" className={inputClass} defaultValue={subscription?.renewal_time?.slice(0, 5) ?? '15:00'} /></Field>
          <Field label="Payment card">
            <select name="card" className={inputClass} defaultValue={subscription?.card ?? ''}>
              <option value="">No card</option>
              {options.cards.map((card) => <option key={card.id} value={card.id}>{card.nickname} · {card.last4}</option>)}
              {subscription?.card && !options.cards.some((card) => Number(card.id) === subscription.card) && <option value={subscription.card}>{subscription.card_nickname} · Assigned by team owner</option>}
            </select>
          </Field>
        </div>
      </section>

      <section className={`${panelClass} grid gap-4`}>
        <h2 className="text-lg font-bold">Sharing</h2>
        <label className="flex gap-3 text-sm font-medium"><input type="checkbox" className="size-4 accent-indigo-600" checked={shared} onChange={(event) => { setShared(event.target.checked); if (event.target.checked && participants.length === 0) addParticipant() }} /> Split the cost with others</label>
        {shared && (
          <>
            <Field label="Split type"><select value={split} className={inputClass} onChange={(event) => setSplit(event.target.value)}><option value="equal">Equal split</option><option value="custom">Custom shares</option></select></Field>
            <div className="grid gap-3">
              {participants.map((participant, index) => (
                <div className="flex items-end gap-2" key={participant.id}>
                  <div className="min-w-0 flex-1"><Field label={`Participant ${index + 1}`}><input className={inputClass} value={participant.name} required maxLength={100} onChange={(event) => updateParticipant(participant.id, 'name', event.target.value)} /></Field></div>
                  {split === 'custom' && <div className="w-20 sm:w-28"><Field label="Share"><input className={inputClass} type="number" min="0" step="0.01" value={participant.share} onChange={(event) => updateParticipant(participant.id, 'share', event.target.value)} /></Field></div>}
                  <button type="button" className={buttonClass} aria-label={`Remove participant ${index + 1}`} onClick={() => setParticipants((people) => people.filter((person) => person.id !== participant.id))}><Trash2 size={16} /></button>
                </div>
              ))}
            </div>
            <button type="button" className={`${buttonClass} w-fit gap-2`} onClick={addParticipant}><Plus size={16} /> Add participant</button>
          </>
        )}
      </section>

      <section className={`${panelClass} grid gap-4`}>
        <h2 className="text-lg font-bold">Renewal reminders</h2>
        <label className="flex gap-3 text-sm font-medium"><input type="checkbox" className="size-4 accent-indigo-600" checked={remindersEnabled} onChange={(event) => setRemindersEnabled(event.target.checked)} /> Enable renewal reminders</label>
        {remindersEnabled && (
          <>
            <div className="flex flex-wrap items-end gap-2">
              <Field label="Days before renewal"><input className={inputClass} type="number" value={offsetInput} onChange={(event) => setOffsetInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') { event.preventDefault(); addOffset() } }} /></Field>
              <button type="button" className={buttonClass} onClick={addOffset} disabled={!Number.isInteger(Number(offsetInput)) || Number(offsetInput) < 1 || Number(offsetInput) > 30 || offsets.includes(Number(offsetInput))}>Add reminder</button>
            </div>
            <div className="flex flex-wrap gap-2">
              {[...offsets].sort((a, b) => a - b).map((days) => <button type="button" key={days} className="rounded-full bg-indigo-50 px-3 py-1.5 text-sm font-semibold text-indigo-800 hover:bg-indigo-100" aria-label={`Remove ${days}-day reminder`} onClick={() => setOffsets((current) => current.filter((day) => day !== days))}>{days} {days === 1 ? 'day' : 'days'} before ×</button>)}
              {offsets.length === 0 && <p className="text-sm text-slate-600">Default reminder {options.default_reminder_offset} {options.default_reminder_offset === 1 ? 'day' : 'days'} before renewal.</p>}
            </div>
          </>
        )}
      </section>

      <section className={`${panelClass} grid gap-4`}>
        <h2 className="text-lg font-bold">Account and notes</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Account email"><input type="email" autoComplete="off" name="account_email" className={inputClass} maxLength={255} defaultValue={subscription?.account_email ?? ''} /></Field>
          {!pending && <Field label="Account password"><input type="password" autoComplete="new-password" name="account_password" className={inputClass} placeholder={subscription?.has_password ? 'Leave blank to keep current password' : ''} /></Field>}
        </div>
        <Field label="Notes"><textarea name="notes" className={inputClass} rows={3} defaultValue={subscription?.notes ?? ''} /></Field>
      </section>
      <div className="flex flex-wrap justify-end gap-2">
        <Link className={buttonClass} to={backPath}>Cancel</Link>
        <button disabled={saving} className={primaryClass}>{saving ? 'Saving…' : pending ? 'Submit request' : 'Save subscription'}</button>
      </div>
    </form>
  )
}

export function SubscriptionFormPage() {
  const { id } = useParams<{ id: string }>()
  const [query] = useSearchParams()
  const [loaded, setLoaded] = useState<{ key: string; options: Options; subscription: Subscription | null } | null>(null)
  const [error, setError] = useState('')
  const queryString = query.toString()
  const requestKey = `${id ?? 'new'}:${queryString}`

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      const init = { signal: controller.signal }
      try {
        const subscription = id ? await api<Subscription>(`${subscriptionApi}${id}/`, init) : null
        const params = new URLSearchParams(queryString)
        if (subscription?.team) params.set('team', String(subscription.team))
        const options = await api<Options>(`${subscriptionApi}options/?${params}`, init)
        setLoaded({ key: requestKey, options, subscription })
        setError('')
      } catch (error) {
        if (!controller.signal.aborted) setError(showError(error))
      }
    }
    void load()
    return () => controller.abort()
  }, [id, queryString, requestKey])

  return (
    <section className="mx-auto max-w-4xl px-4 py-6 sm:px-6 lg:py-8">
      <ErrorBanner message={error} />
      {!error && loaded?.key !== requestKey && <p role="status" className="text-sm text-slate-600">Loading subscription form…</p>}
      {loaded?.key === requestKey && <SubscriptionEditor key={requestKey} options={loaded.options} subscription={loaded.subscription} />}
    </section>
  )
}
