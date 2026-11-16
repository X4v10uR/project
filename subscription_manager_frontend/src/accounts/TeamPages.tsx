import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, ArrowUpRight, Plus, UsersRound } from 'lucide-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { currencyAmount } from '../subscriptions/shared'
import { ErrorMessage, Field, fieldClass, formData, messageFrom, panelClass, primaryClass, secondaryClass, StatusMessage } from './Controls'

export type Role = 'owner' | 'member'

export type TeamSubscription = {
  id: number
  team_id: number
  team_name: string
  service_name: string
  currency: string
  cost: string
  billing_cycle: string
  status: string
  icon: string
  account_email: string | null
  has_password: boolean
  accent_color?: string
}

type TeamCard = {
  id: number
  name: string
  role: Role
  member_count: number
  accent_color: string
}

type Overview = {
  teams: TeamCard[]
  subscriptions: TeamSubscription[]
  monthly_spend_by_currency: Record<string, string>
}

function teamPath(id: number) {
  return '/accounts/teams/' + id + '/'
}

export function TeamStatus({ status }: { status: string }) {
  return <span className={'shrink-0 rounded-full px-2.5 py-1 text-xs font-medium capitalize ' + (status === 'active' ? 'bg-emerald-50 text-emerald-800' : 'bg-zinc-100 text-zinc-700')}>{status}</span>
}

export function TeamsPage() {
  const { state } = useLocation()
  const [data, setData] = useState<Overview | null>(null)
  const [selectedTeam, setSelectedTeam] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    api<Overview>('/api/accounts/teams/').then((reply) => {
      if (active) setData(reply)
    }).catch((failure) => {
      if (active) setError(messageFrom(failure))
    })
    return () => { active = false }
  }, [])

  const subscriptions = data?.subscriptions.filter((item) => !selectedTeam || String(item.team_id) === selectedTeam) ?? []
  return (
    <div className="mx-auto grid w-full max-w-7xl grid-cols-[minmax(0,1fr)] gap-6 p-4 sm:p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-bold tracking-tight">Teams</h1>
        <Link className={primaryClass} to="/accounts/teams/create/"><Plus aria-hidden size={18} /> Create team</Link>
      </header>
      <ErrorMessage message={error} />
      <StatusMessage message={typeof state?.notice === 'string' ? state.notice : ''} />
      {!data && !error && <p role="status" className="text-sm text-zinc-600">Loading teams…</p>}
      {data && <>
        <div className="grid gap-3 sm:grid-cols-3">
          <div className={panelClass}><p className="text-sm font-medium text-zinc-600">Teams</p><p className="mt-1 text-2xl font-bold">{data.teams.length}</p></div>
          <div className={panelClass}><p className="text-sm font-medium text-zinc-600">Team subscriptions</p><p className="mt-1 text-2xl font-bold">{data.subscriptions.length}</p></div>
          <div className="rounded-2xl bg-zinc-950 p-5 text-white sm:p-6"><p className="text-sm font-medium text-zinc-300">Monthly team spend</p><p className="mt-1 wrap-anywhere text-2xl font-bold">{Object.entries(data.monthly_spend_by_currency).map(([currency, amount]) => currencyAmount(amount, currency)).join(' + ') || '$0.00'}</p></div>
        </div>
        <section>
          <h2 className="mb-3 text-lg font-bold">Your teams</h2>
          {data.teams.length ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {data.teams.map((team) => (
                <Link to={teamPath(team.id)} key={team.id} className={panelClass + ' flex items-center gap-3 transition hover:border-zinc-400'}>
                  <span className="grid size-11 shrink-0 place-items-center rounded-xl" style={{ backgroundColor: team.accent_color }}><UsersRound size={19} aria-hidden /></span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-bold">{team.name}</p>
                    <p className="text-sm text-zinc-600 capitalize">{team.role} · {team.member_count} {team.member_count === 1 ? 'member' : 'members'}</p>
                  </div>
                  <ArrowUpRight aria-hidden size={18} className="shrink-0 text-zinc-600" />
                </Link>
              ))}
            </div>
          ) : <p className={panelClass + ' text-sm text-zinc-600'}>You haven’t joined any teams yet.</p>}
        </section>
        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-bold">Team subscriptions</h2>
            {data.teams.length > 1 && (
              <select aria-label="Filter by team" className={fieldClass + ' sm:w-52'} value={selectedTeam} onChange={(event) => setSelectedTeam(event.target.value)}>
                <option value="">All teams</option>
                {data.teams.map((team) => <option key={team.id} value={team.id}>{team.name}</option>)}
              </select>
            )}
          </div>
          <div className="overflow-x-auto rounded-2xl border border-zinc-200 bg-white" role="region" aria-label="Team subscription table" tabIndex={subscriptions.length ? 0 : undefined}>
            {subscriptions.length ? (
              <table className="w-full min-w-160 text-left text-sm">
                <thead className="border-b border-zinc-200 bg-zinc-50 text-zinc-600"><tr>
                  {['Subscription', 'Team', 'Cost', 'Status'].map((title) => <th key={title} scope="col" className="px-4 py-3 font-semibold">{title}</th>)}
                </tr></thead>
                <tbody className="divide-y divide-zinc-100">
                  {subscriptions.map((item) => <tr key={item.id}>
                    <td className="px-4 py-3">
                      <Link className="inline-flex items-center gap-2 font-semibold hover:underline" to={teamPath(item.team_id)}>
                        <span className="grid size-8 place-items-center rounded-lg" style={{ backgroundColor: item.accent_color }} aria-hidden>{item.icon}</span>
                        {item.service_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-zinc-600">{item.team_name}</td>
                    <td className="px-4 py-3 text-zinc-600">{item.currency} {item.cost} / {item.billing_cycle}</td>
                    <td className="px-4 py-3"><TeamStatus status={item.status} /></td>
                  </tr>)}
                </tbody>
              </table>
            ) : <p className="p-6 text-sm text-zinc-600">No team subscriptions to show.</p>}
          </div>
        </section>
      </>}
    </div>
  )
}

export function TeamCreatePage() {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      const team = await api<{ id: number }>('/api/accounts/teams/', {
        method: 'POST',
        body: JSON.stringify(formData(event.currentTarget)),
      })
      navigate(teamPath(team.id), { state: { notice: 'Team created.' } })
    } catch (failure) {
      setError(messageFrom(failure))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto grid w-full max-w-3xl gap-4 p-4 sm:p-8">
      <Link className={secondaryClass + ' justify-self-start'} to="/accounts/teams/"><ArrowLeft size={15} aria-hidden /> Teams</Link>
      <form onSubmit={submit} className={panelClass + ' grid gap-5'}>
        <h1 className="text-2xl font-bold tracking-tight">Create team</h1>
        <ErrorMessage message={error} />
        <Field label="Team name"><input autoFocus required maxLength={120} name="name" className={fieldClass} /></Field>
        <button className={primaryClass + ' justify-self-end'} disabled={saving}>Create team</button>
      </form>
    </div>
  )
}
