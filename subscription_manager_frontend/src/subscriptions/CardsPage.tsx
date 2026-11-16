import { CreditCard, Pencil, Plus, Search, Star, Trash2 } from 'lucide-react'
import { type FormEvent, useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import {
  buttonClass, currencyAmount, dangerClass, ErrorBanner, Field, inputClass, Modal, panelClass,
  primaryClass, showError, subscriptionApi, subscriptionPath, type Card,
} from './shared'

const cardsPath = `${subscriptionApi}cards/`
const brands: [string, string][] = [['visa', 'Visa'], ['mastercard', 'Mastercard'], ['amex', 'American Express'], ['discover', 'Discover'], ['jcb', 'JCB']]
const themes: [string, string, string][] = [
  ['dark', 'Midnight', 'from-neutral-900 via-neutral-700 to-black'],
  ['navy', 'Ocean', 'from-indigo-950 via-blue-900 to-slate-950'],
  ['forest', 'Forest', 'from-emerald-950 via-green-900 to-slate-950'],
  ['plum', 'Plum', 'from-purple-950 via-fuchsia-900 to-slate-950'],
  ['rose', 'Rose', 'from-rose-950 via-rose-800 to-slate-950'],
]

interface CardSubscription {
  id: string
  name: string
  teamId: number | null
  monthlyPrice: number
  currency: string
  cardId: string
  iconBg: string
  iconLabel: string
  nextBillingDate: string
  plan: string
}

interface CardsState {
  cards: Card[]
  subscriptions: CardSubscription[]
}

type CardResponse = { state: CardsState }
type Mode = 'add' | 'edit' | 'delete' | null

function cardBrand(brand: string) {
  return brands.find(([value]) => value === brand)?.[1] ?? brand
}

function CardTile({ card, active, onSelect }: { card: Card; active: boolean; onSelect: () => void }) {
  const theme = themes.find(([value]) => value === card.theme) ?? themes[0]
  return (
    <button type="button" aria-pressed={active} onClick={onSelect} className={`grid min-h-40 w-full gap-4 rounded-2xl bg-linear-to-br ${theme[2]} p-5 text-left text-white shadow-sm transition hover:-translate-y-0.5 ${active ? 'ring-3 ring-lime-400 ring-offset-2' : ''}`}>
      <span className="flex items-center justify-between gap-3">
        <CreditCard size={23} aria-hidden="true" />
        {card.isPrimary && <span className="inline-flex items-center gap-1 rounded-full bg-lime-300 px-2 py-1 text-xs font-bold text-slate-950"><Star size={12} /> Primary</span>}
      </span>
      <span className="font-mono text-lg tracking-[0.13em]">••••&nbsp; {card.last4}</span>
      <span className="flex items-end justify-between gap-2 text-sm"><span className="min-w-0 truncate font-semibold">{card.nickname}</span><span className="shrink-0 opacity-85">{cardBrand(card.brand)}</span></span>
    </button>
  )
}

function CardForm({ card, onSave, onClose, busy }: {
  card: Card | null; onSave: (init: RequestInit) => void; onClose: () => void; busy: boolean
}) {
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    onSave({
      method: card ? 'PUT' : 'POST',
      body: JSON.stringify({
        nickname: fields.get('nickname'), last4: fields.get('last4'), brand: fields.get('brand'),
        theme: fields.get('theme'), isPrimary: fields.has('primary'),
      }),
    })
  }

  return (
    <form className="grid gap-4" onSubmit={save}>
      <Field label="Card nickname"><input className={inputClass} name="nickname" required maxLength={50} defaultValue={card?.nickname} placeholder="e.g. Work card" /></Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Last four digits"><input className={`${inputClass} font-mono`} name="last4" required inputMode="numeric" pattern="[0-9]{4}" maxLength={4} defaultValue={card?.last4} placeholder="1234" /></Field>
        <Field label="Brand"><select className={inputClass} name="brand" defaultValue={card?.brand ?? 'visa'}>{brands.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      </div>
      <Field label="Theme"><select className={inputClass} name="theme" defaultValue={card?.theme ?? 'dark'}>{themes.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      <label className="flex items-center gap-2 text-sm font-semibold"><input name="primary" type="checkbox" className="size-4 accent-indigo-600" defaultChecked={card?.isPrimary ?? false} /> Set as primary card</label>
      <div className="flex justify-end gap-2 pt-2">
        <button type="button" className={buttonClass} onClick={onClose}>Cancel</button>
        <button className={primaryClass} disabled={busy}>{busy ? 'Saving…' : 'Save card'}</button>
      </div>
    </form>
  )
}

export function CardsPage() {
  const [query, setQuery] = useSearchParams()
  const [state, setState] = useState<CardsState | null>(null)
  const [selectedId, setSelectedId] = useState(query.get('card'))
  const [search, setSearch] = useState('')
  const [modal, setModal] = useState<Mode>(() => {
    const mode = query.get('modal')
    return mode === 'add' || mode === 'edit' || mode === 'delete' ? mode : null
  })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    api<CardResponse>(cardsPath, { signal: controller.signal })
      .then(({ state }) => setState(state))
      .catch((error) => { if (!controller.signal.aborted) setError(showError(error)) })
    return () => controller.abort()
  }, [])

  const selected = state?.cards.find((card) => card.id === selectedId) ?? state?.cards.find((card) => card.isPrimary) ?? state?.cards[0]
  const modalCard = modal === 'edit' || modal === 'delete' ? state?.cards.find((card) => card.id === selectedId) : null
  const subscriptions = state?.subscriptions.filter((subscription) => subscription.cardId === selected?.id) ?? []
  const shown = subscriptions.filter((subscription) => subscription.name.toLowerCase().includes(search.trim().toLowerCase()))
  const totals = new Map<string, number>()
  for (const subscription of subscriptions) {
    totals.set(subscription.currency, (totals.get(subscription.currency) ?? 0) + subscription.monthlyPrice)
  }

  function closeModal() {
    setModal(null)
    setError('')
    if (query.has('modal')) setQuery({}, { replace: true })
  }

  function openModal(mode: Mode, card?: Card) {
    setError('')
    if (card) setSelectedId(card.id)
    setModal(mode)
  }

  async function mutate(path: string, init: RequestInit) {
    setBusy(true)
    setError('')
    try {
      const response = await api<CardResponse>(path, init)
      if (modal === 'add') {
        const created = response.state.cards.find((card) => !state?.cards.some((previous) => previous.id === card.id))
        if (created) setSelectedId(created.id)
      }
      setState(response.state)
      closeModal()
    } catch (error) {
      setError(showError(error))
    } finally {
      setBusy(false)
    }
  }

  const modalOpen = (modal === 'add' && !!state) || Boolean(modalCard)
  return (
    <section className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">Payment cards</h1>
        <button className={`${primaryClass} gap-2`} disabled={!state} onClick={() => openModal('add')}><Plus size={18} /> Add card</button>
      </header>
      {!modalOpen && <ErrorBanner message={error} />}
      {!state && !error && <p role="status" className="text-sm text-slate-600">Loading cards…</p>}
      {state && state.cards.length === 0 && <div className={`${panelClass} grid justify-items-center gap-3 py-12`}><CreditCard size={32} className="text-slate-400" /><h2 className="text-lg font-bold">No payment cards yet</h2><p className="text-center text-sm text-slate-600">Add a card using its last four digits to organize subscriptions by payment method.</p></div>}
      {state && state.cards.length > 0 && selected && (
        <div className="grid gap-5 lg:grid-cols-[minmax(16rem,22rem)_minmax(0,1fr)]">
          <aside aria-label="Your payment cards" className="grid content-start gap-4 sm:grid-cols-2 lg:grid-cols-1">
            {state.cards.map((card) => <CardTile key={card.id} card={card} active={card.id === selected.id} onSelect={() => setSelectedId(card.id)} />)}
          </aside>
          <div className={`${panelClass} grid content-start gap-5`}>
            <header className="flex flex-wrap items-start justify-between gap-3">
              <div><h2 className="text-xl font-bold">{selected.nickname}</h2><p className="mt-1 text-sm text-slate-500">{cardBrand(selected.brand)} · •••• {selected.last4}</p></div>
              <div className="flex flex-wrap gap-2">
                {!selected.isPrimary && <button className={`${buttonClass} gap-1.5`} disabled={busy} onClick={() => void mutate(`${cardsPath}${selected.id}/set-primary/`, { method: 'POST' })}><Star size={15} /> Set primary</button>}
                <button className={`${buttonClass} gap-1.5`} disabled={busy} onClick={() => openModal('edit', selected)}><Pencil size={15} /> Edit</button>
                <button className={`${buttonClass} gap-1.5 text-red-700`} disabled={busy} onClick={() => openModal('delete', selected)}><Trash2 size={15} /> Delete</button>
              </div>
            </header>
            <div className="rounded-2xl bg-slate-50 p-4">
              <p className="text-sm font-semibold text-slate-600">Active monthly spend</p>
              <p className="mt-2 text-xl font-bold text-slate-950">{[...totals].map(([currency, value]) => currencyAmount(value, currency)).join(' + ') || 'No active spending'}</p>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="font-bold">Active subscriptions ({subscriptions.length})</h3>
              {subscriptions.length > 0 && <label className="relative"><span className="sr-only">Search linked subscriptions</span><Search size={16} className="pointer-events-none absolute top-3 left-3 text-slate-400" /><input type="search" className={`${inputClass} pl-9`} placeholder="Search subscriptions" value={search} onChange={(event) => setSearch(event.target.value)} /></label>}
            </div>
            {shown.length > 0 ? (
              <ul className="divide-y divide-slate-100">
                {shown.map((subscription) => (
                  <li key={subscription.id}>
                    <Link to={subscription.teamId ? `/accounts/teams/${subscription.teamId}/` : `${subscriptionPath}?subscription=${subscription.id.slice(1)}`} className="flex items-center gap-3 rounded-lg px-1 py-3 hover:bg-slate-50">
                      <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-100 text-sm font-bold text-white" style={{ backgroundColor: subscription.iconBg, textShadow: '0 1px 3px #111827' }}>{subscription.iconLabel}</span>
                      <span className="min-w-0 flex-1"><span className="block truncate text-sm font-bold">{subscription.name}</span><span className="block text-xs text-slate-500">{subscription.plan} · {subscription.nextBillingDate}</span></span>
                      <span className="shrink-0 text-sm font-bold">{currencyAmount(subscription.monthlyPrice, subscription.currency)}<span className="block text-right text-xs font-medium text-slate-500">per month</span></span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-slate-600">{subscriptions.length ? 'No matching subscriptions.' : 'There are no active subscriptions on this card.'}</p>}
          </div>
        </div>
      )}
      {modalOpen && modal !== 'delete' && (
        <Modal title={modal === 'add' ? 'Add payment card' : 'Edit payment card'} onClose={closeModal}>
          <div className="grid gap-3"><ErrorBanner message={error} /><CardForm card={modalCard ?? null} busy={busy} onClose={closeModal} onSave={(init) => void mutate(modalCard ? `${cardsPath}${modalCard.id}/` : cardsPath, init)} /></div>
        </Modal>
      )}
      {modal === 'delete' && modalCard && (
        <Modal title={`Delete ${modalCard.nickname}?`} onClose={closeModal}>
          <form className="grid gap-4" onSubmit={(event) => {
            event.preventDefault()
            const destination = new FormData(event.currentTarget).get('destination')
            void mutate(`${cardsPath}${modalCard.id}/`, { method: 'DELETE', body: JSON.stringify({ move_to_card_id: destination || null }) })
          }}>
            <ErrorBanner message={error} />
            <p className="text-sm text-slate-600">Choose another payment card for linked subscriptions or leave them without a card.</p>
            <Field label="Move linked subscriptions to"><select name="destination" className={inputClass}><option value="">No card</option>{state?.cards.filter((card) => card.id !== modalCard.id).map((card) => <option key={card.id} value={card.id}>{card.nickname} · {card.last4}</option>)}</select></Field>
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" className={buttonClass} onClick={closeModal}>Cancel</button>
              <button className={dangerClass} disabled={busy}>{busy ? 'Deleting…' : 'Delete card'}</button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  )
}
