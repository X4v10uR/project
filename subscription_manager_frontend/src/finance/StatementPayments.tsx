import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { useAuth } from '../accounts/auth'
import { buttonClass, currencyAmount, displayDate, ErrorBanner, Field, inputClass, panelClass, primaryClass, showError } from '../subscriptions/shared'
import { endpoint, useFinancePages } from './common'

const columns = [
  ['date', 'Payment date'], ['merchant', 'Merchant'], ['amount', 'Amount'],
  ['currency', 'Currency'], ['reference', 'Transaction ID'],
] as const

type StatementRow = {
  line: number; status: 'ready' | 'duplicate' | 'error' | 'skipped'; message?: string
  merchant?: string; amount?: string; currency?: string; date?: string
}
type Preview = {
  headers: string[]; mapping: Record<string, string>; rows: StatementRow[]
  ready: number; duplicates: number; skipped: number; errors: number; imported?: number
}

export function StatementImport({ onImport }: { onImport: () => void }) {
  const { user } = useAuth()
  const [file, setFile] = useState<File>()
  const [headers, setHeaders] = useState<string[]>([])
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<Preview>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file) return
    const form = new FormData(event.currentTarget)
    const confirm = (event.nativeEvent as SubmitEvent).submitter?.getAttribute('value') === 'confirm'
    form.set('mode', confirm ? 'confirm' : 'preview')
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const result = await api<Preview>(endpoint + 'statements/import/', { method: 'POST', body: form })
      setHeaders(result.headers)
      setMapping(result.mapping)
      setPreview(result)
      if (confirm) {
        setNotice(`Imported ${result.imported} payments. Review them below.`)
        onImport()
      }
    } catch (failure) {
      setError(showError(failure))
    } finally {
      setBusy(false)
    }
  }

  return <section className={panelClass}>
    <h2 className="font-bold">Import a bank statement</h2>
    <p className="mt-2 text-sm text-slate-600">Upload up to 500 rows from a UTF-8 CSV. Use the same account label for overlapping statements. A transaction ID distinguishes identical payments on the same day.</p>
    <form onSubmit={submit} onChange={() => { setPreview(undefined); setNotice(''); setError('') }}>
      <fieldset className="mt-3 grid gap-3" disabled={busy}>
        <Field label="Statement CSV"><input className={inputClass} type="file" name="file" accept=".csv,text/csv" required
          onChange={event => { setFile(event.target.files?.[0]); setHeaders([]); setMapping({}) }} /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Statement account label"><input className={inputClass} name="account" defaultValue="Bank statement" maxLength={100} required /></Field>
          <Field label="Default currency"><input className={inputClass} name="currency" defaultValue={user?.preferred_currency || 'USD'} pattern="[A-Za-z]{3}" maxLength={3} required /></Field>
          <Field label="Statement date format"><select className={inputClass} name="date_format"><option value="iso">YYYY-MM-DD</option><option value="mdy">MM/DD/YYYY</option><option value="dmy">DD/MM/YYYY</option></select></Field>
          <Field label="Outgoing payments"><select className={inputClass} name="debits"><option value="positive">Positive amounts</option><option value="negative">Negative amounts</option></select></Field>
        </div>
        {headers.length > 0 && <div className="grid gap-3 sm:grid-cols-2">
          {columns.map(([key, label]) => <Field key={key} label={label + ' column'}>
            <select className={inputClass} name={'column_' + key} value={mapping[key] ?? ''}
              onChange={event => setMapping({ ...mapping, [key]: event.target.value })}>
              <option value="">{key === 'currency' ? 'Use default currency' : key === 'reference' ? 'Use date, merchant and amount' : 'Choose a column'}</option>
              {headers.map(name => <option key={name}>{name}</option>)}
            </select>
          </Field>)}
        </div>}
        {preview && !preview.rows.length && <p role="status">Choose the date, merchant and amount columns and preview again.</p>}
        {preview && preview.rows.length > 0 && <div>
          <p className="mb-2 text-sm" role="status">{preview.ready} ready · {preview.duplicates} duplicates · {preview.skipped} skipped · {preview.errors} invalid</p>
          <div className="max-h-64 overflow-auto"><table className="w-full text-left text-sm">
            <thead><tr>{['Row', 'Date', 'Merchant', 'Amount', 'Result'].map(label => <th className="p-2" key={label}>{label}</th>)}</tr></thead>
            <tbody>{preview.rows.map(row => <tr key={row.line}><td className="p-2">{row.line}</td><td className="p-2">{row.date}</td><td className="p-2">{row.merchant}</td><td className="p-2">{row.amount && row.currency && currencyAmount(row.amount, row.currency)}</td><td className="p-2">{row.message ?? row.status}</td></tr>)}</tbody>
          </table></div>
        </div>}
        <div className="flex flex-wrap gap-2">
          <button className={buttonClass} disabled={!file} value="preview">Preview statement</button>
          {preview && preview.ready > 0 && !preview.errors && preview.imported === undefined && <button className={primaryClass} value="confirm">Import {preview.ready} payments</button>}
        </div>
      </fieldset>
    </form>
    <ErrorBanner message={error} />{notice && <p className="mt-2 text-sm" role="status">{notice}</p>}
  </section>
}

type Charge = { id: number; service: string; date: string; amount: string; currency: string; team: string | null }
export function ManualMatch({ payment, onMatch, onClose }: {
  payment: { id: number; merchant: string; amount: string; currency: string; date: string }
  onMatch: () => void; onClose: () => void
}) {
  const [query, setQuery] = useState('')
  const [chosen, setChosen] = useState<Charge>()
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState('')
  const path = `discoveries/${payment.id}/charges/?q=${encodeURIComponent(query)}`
  const { pages, data, error, next, loading, loadOlder } = useFinancePages<{ charges: Charge[]; next: string | null }>(path)
  const charges = pages.flatMap(page => page.charges)
  async function confirm() {
    if (!chosen) return
    setBusy(true)
    setFailure('')
    try {
      await api(endpoint + `discoveries/${payment.id}/`, {
        method: 'POST', body: JSON.stringify({ action: 'manual_match', charge: chosen.id }),
      })
      onMatch()
    } catch (issue) {
      setFailure(showError(issue))
    } finally {
      setBusy(false)
    }
  }
  return <fieldset className="mt-4 grid gap-3 border-t pt-3" disabled={busy}>
    <legend className="font-semibold">Match {payment.merchant} to a charge</legend>
    <Field label="Search charges by service or team"><input className={inputClass} type="search" value={query} onChange={event => { setQuery(event.target.value); setChosen(undefined) }} /></Field>
    {data && !charges.length && <p>No eligible charges in {payment.currency}.</p>}
    {charges.length > 0 && <Field label="Charge to match"><select className={inputClass} value={chosen?.id ?? ''} onChange={event => setChosen(charges.find(charge => charge.id === Number(event.target.value)))}>
      <option value="">Choose a charge</option>
      {charges.map(charge => <option value={charge.id} key={charge.id}>{charge.service} · {charge.team ?? 'Personal'} · {displayDate(charge.date)} · {currencyAmount(charge.amount, charge.currency)}</option>)}
    </select></Field>}
    {next && <button className={buttonClass} disabled={loading} onClick={loadOlder}>Load older charges</button>}
    {chosen && <p className="text-sm">Link the {currencyAmount(payment.amount, payment.currency)} payment from {displayDate(payment.date)} and mark the {currencyAmount(chosen.amount, chosen.currency)} charge for {chosen.service} paid. History keeps the recorded charge amount and shares.</p>}
    <ErrorBanner message={error || failure} />
    <div className="flex gap-2"><button className={primaryClass} disabled={!chosen} onClick={confirm}>Confirm manual match</button><button className={buttonClass} onClick={onClose}>Close</button></div>
  </fieldset>
}
