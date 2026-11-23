import { ServiceIcon } from '../ServiceIcon'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api'
import { buttonClass, ErrorBanner, Field, inputClass, panelClass, primaryClass, showError, subscriptionApi, subscriptionPath } from './shared'

type Row = {
  row: number; service: string; status: 'ready' | 'duplicate' | 'invalid'; errors?: unknown
  cost?: string; currency?: string; cycle?: string; start?: string
}
type Preview = { rows: Row[]; imported: number; first_subscription_id?: number | null }
const template = 'Service Name,Plan Name,Category,Billing Cycle,Currency,Total Cost,Start Date,Trial End Date,Cancel By Date\r\nMusic,Individual,Music,monthly,USD,9.99,2026-01-31,,\r\n'

export function ImportPage() {
  const navigate = useNavigate()
  const [file, setFile] = useState<File>()
  const [preview, setPreview] = useState<Preview>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const ready = preview?.rows.filter((row) => row.status === 'ready').length ?? 0
  const duplicates = preview?.rows.filter((row) => row.status === 'duplicate').length ?? 0
  const invalid = preview?.rows.filter((row) => row.status === 'invalid').length ?? 0

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file || busy) return
    const mode = preview ? 'confirm' : 'preview'
    const body = new FormData()
    body.set('file', file)
    body.set('mode', mode)
    setBusy(true)
    setError('')
    try {
      const result = await api<Preview>(`${subscriptionApi}import/csv/`, { method: 'POST', body })
      if (mode === 'confirm') {
        const skipped = result.rows.filter((row) => row.status === 'duplicate').length
        navigate(subscriptionPath, { state: { savedSubscriptionId: result.first_subscription_id, notice: `Imported ${result.imported}. Skipped ${skipped} duplicates.` } })
      } else {
        setPreview(result)
      }
    } catch (failure) {
      setError(showError(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mx-auto grid max-w-4xl gap-5 px-4 py-6 sm:px-6">
      <Link className="text-sm font-semibold text-slate-600" to={subscriptionPath}>Back to subscriptions</Link>
      <h1 className="text-3xl font-bold tracking-tight">Import subscriptions</h1>
      <form className={`${panelClass} grid gap-4`} onSubmit={submit}>
        <p className="text-sm text-slate-700">Upload personal subscriptions using a DUES export or the CSV template. Use UTF-8, up to 500 rows and 1 MB.</p>
        <a className="w-fit text-sm font-semibold underline" href={`data:text/csv;charset=utf-8,${encodeURIComponent(template)}`} download="subscriptions-template.csv">Download CSV template</a>
        <Field label="CSV file"><input type="file" required accept=".csv,text/csv" className={inputClass} disabled={busy} onChange={(event) => {
          setFile(event.currentTarget.files?.[0])
          setPreview(undefined)
          setError('')
        }} /></Field>
        <ErrorBanner message={error} />
        {preview && <>
          <h2 className="text-lg font-bold">Import preview</h2>
          <p role="status">{ready} ready · {duplicates} duplicates · {invalid} invalid</p>
          <p className="text-sm text-slate-600">Rows matching the same service, plan, and account email are skipped. Correct invalid rows and choose the updated file to continue.</p>
          <div className="max-h-96 overflow-auto"><table className="w-full text-left text-sm">
            <thead><tr>{['Row', 'Service', 'Cost', 'Cycle', 'Start date', 'Result'].map((label) => <th className="p-2" key={label}>{label}</th>)}</tr></thead>
            <tbody>{preview.rows.map((row) => <tr className="border-t border-slate-200" key={row.row}>
              <td className="p-2">{row.row}</td><td className="p-2">{row.service && <ServiceIcon name={row.service} className="mr-1 size-5 align-middle" />}{row.service}</td><td className="p-2">{row.currency} {row.cost}</td>
              <td className="p-2">{row.cycle}</td><td className="p-2">{row.start}</td><td className="p-2">{row.errors ? errorMessage(row.errors, 'Invalid row') : row.status}</td>
            </tr>)}</tbody>
          </table></div>
        </>}
        <div className="flex flex-wrap gap-2">
          <button className={primaryClass} disabled={busy || !file || (!!preview && (!ready || !!invalid))}>{busy ? 'Processing…' : preview ? 'Confirm import' : 'Preview import'}</button>
          <Link className={buttonClass} to={subscriptionPath}>Cancel</Link>
        </div>
      </form>
    </section>
  )
}
