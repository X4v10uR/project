import { X } from 'lucide-react'
import { type ReactNode, useEffect, useRef } from 'react'

export const subscriptionPath = '/subscriptions/'
export const subscriptionApi = '/api/subscriptions/'
export const inputClass = 'w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-indigo-500 focus:outline-2 focus:outline-indigo-500/25'
export const buttonClass = 'inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-800 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50'
export const primaryClass = 'inline-flex items-center justify-center rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50'
export const dangerClass = 'inline-flex items-center justify-center rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50'
export const panelClass = 'rounded-2xl border border-slate-200 bg-white p-5 shadow-sm'

export const subscriptionStatuses = [['active', 'Active'], ['paused', 'Paused'], ['cancelled', 'Cancelled']]
export const billingCycles = [['weekly', 'Weekly'], ['monthly', 'Monthly'], ['quarterly', 'Quarterly'], ['halfyearly', 'Every six months'], ['fourweekly', 'Every 28 days'], ['yearly', 'Yearly']]

export interface Card {
  id: string
  nickname: string
  last4: string
  brand: string
  theme: string
  isPrimary: boolean
}

export interface Subscription {
  edit_revision?: string
  id: number
  team: number | null
  payer_id: number
  current_status: string
  service_name: string
  display_color: string
  plan_name: string | null
  category: string
  billing_cycle: string
  cost: string
  user_cost: string
  current_cost: string
  current_user_cost: string
  currency: string
  start_date: string
  trial_end_date: string | null
  cancel_by_date: string | null
  cancellation_url: string
  cancellation_state: string
  cancellation_notes: string
  access_until: string | null
  pause_from: string | null
  resume_on: string | null
  introductory_cost: string | null
  introductory_until: string | null
  last_reviewed_on: string | null
  usage_rating: string
  renewal_date: string | null
  renewal_time: string | null
  status: string
  reminders_enabled: boolean
  reminder_offsets: number[]
  card: number | null
  card_nickname: string | null
  notes: string | null
  is_shared: boolean
  split_type: string
  account_email: string | null
  has_password: boolean
  participants: { name: string; share_amount: string | null; member_id: number | null }[]
}

export interface SubscriptionDetails {
  renewal_date: string
  card_color: string
  card_text_is_light: boolean
  billing_cycle_detail: string
  days_until_renewal: number | null
  card_last4: string
  card_brand: string
  history: {
    payment_status: string
    charged_for_date: string
    charged_for_date_display: string
    amount_display: string
  }[]
}

export function currencyAmount(value: number | string, currency: string, fractionDigits?: number) {
  if (!/^[A-Za-z]{3}$/.test(currency)) return `${currency} ${Number(value).toFixed(2)}`
  return new Intl.NumberFormat(undefined, {
    style: 'currency', currency, minimumFractionDigits: fractionDigits, maximumFractionDigits: fractionDigits,
  }).format(Number(value))
}

export function displayDate(value: string | null) {
  if (!value) return 'No date set'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(`${value}T00:00:00`))
}

export function displayCycle(value: string) {
  return billingCycles.find(([cycle]) => cycle === value)?.[1] ?? value
}

export function showError(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong. Try again.'
}

export function ErrorBanner({ message }: { message: string }) {
  return message && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-800">{message}</p>
}

export function Modal({ title, onClose, children }: { title: ReactNode; onClose: () => void; children: ReactNode }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const headingId = 'subscription-dialog-heading'

  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => element?.close()
  }, [])

  return (
    <dialog ref={dialog} aria-labelledby={headingId} onCancel={onClose} className="m-auto max-h-[90dvh] w-[min(94vw,36rem)] overflow-auto rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl backdrop:bg-slate-900/40">
      <header className="mb-5 flex items-start justify-between gap-4">
        <h2 id={headingId} className="text-xl font-bold text-slate-950">{title}</h2>
        <button type="button" className="grid size-9 place-items-center rounded-lg text-slate-600 hover:bg-slate-100" aria-label="Close dialog" onClick={onClose}><X size={20} aria-hidden /></button>
      </header>
      {children}
    </dialog>
  )
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid gap-1.5 text-sm font-semibold text-slate-700"><span>{label}</span>{children}</label>
}
