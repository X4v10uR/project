import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { currencyAmount, displayDate, panelClass, showError, subscriptionApi } from './shared'

type Renewal = {
  service_name: string
  currency: string
  reminders_enabled: boolean
  next_payment: { date: string; amount: string } | null
}

export function SavedRenewal({ subscriptionId }: { subscriptionId?: number }) {
  const [result, setResult] = useState<{ id: number; renewal?: Renewal; error?: string }>()
  useEffect(() => {
    if (!subscriptionId) return
    const controller = new AbortController()
    api<Renewal>(`${subscriptionApi}${subscriptionId}/`, { signal: controller.signal })
      .then(renewal => { if (!controller.signal.aborted) setResult({ id: subscriptionId, renewal }) })
      .catch(error => { if (!controller.signal.aborted) setResult({ id: subscriptionId, error: showError(error) }) })
    return () => controller.abort()
  }, [subscriptionId])

  if (!subscriptionId || result?.id !== subscriptionId) return null
  const renewal = result.renewal
  return (
    <section className={panelClass} aria-label="Saved subscription schedule">
      {renewal && <>
        <h2 className="font-bold">{renewal.service_name} payment schedule</h2>
        <p className="my-2 text-sm">
          {renewal.next_payment
            ? <>Next provider charge <strong>{currencyAmount(renewal.next_payment.amount, renewal.currency)}</strong> on <time dateTime={renewal.next_payment.date}>{displayDate(renewal.next_payment.date)}</time>.</>
            : 'There are no upcoming charges for this subscription.'}
        </p>
      </>}
      {result.error && <p role="alert">Could not load the saved schedule. {result.error}</p>}
      <Link className="text-sm font-semibold text-indigo-700 underline" to={`/subscriptions/${subscriptionId}/edit/?section=reminders`}>
        {renewal?.reminders_enabled ? 'Adjust renewal reminders' : 'Set a renewal reminder'}
      </Link>
    </section>
  )
}
