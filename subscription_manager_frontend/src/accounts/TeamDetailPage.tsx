import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, Plus, UsersRound } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { CredentialReveal } from './SecuritySettings'
import { displayDate } from '../subscriptions/shared'
import { useAuth } from './auth'
import { dangerClass, ErrorMessage, Field, fieldClass, formData, messageFrom, panelClass, primaryClass, secondaryClass, StatusMessage } from './Controls'
import { type Role, type TeamSubscription, TeamStatus } from './TeamPages'

type Member = {
  id: number
  user_id: number
  email: string
  role: Role
  avatar_url: string
  avatar_background_color: string
}

type PendingRequest = {
  id: number
  service_name: string
  requested_by: string
  created_at: string
}

type Team = {
  id: number
  name: string
  role: Role
  accent_color: string
  subscriptions: TeamSubscription[]
  members: Member[]
  pending_requests: PendingRequest[]
}

function SubscriptionCard({ subscription, team }: { subscription: TeamSubscription; team: Team }) {

  return (
    <article className="grid gap-3 rounded-xl border border-zinc-200 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-xl" style={{ backgroundColor: team.accent_color }} aria-hidden>{subscription.icon}</span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate font-bold">{subscription.service_name}</h3>
          <p className="text-sm text-zinc-600">{subscription.currency} {subscription.cost} / {subscription.billing_cycle}</p>
        </div>
        <TeamStatus status={subscription.status} />
      </div>
      <dl className="grid gap-3 rounded-xl bg-zinc-50 p-3 text-sm">
        {subscription.trial_end_date && <div><dt className="font-semibold">First paid date</dt><dd>{displayDate(subscription.trial_end_date)}</dd></div>}
        {subscription.cancel_by_date && <div><dt className="font-semibold">Cancel by</dt><dd>{displayDate(subscription.cancel_by_date)}</dd></div>}
        <div className="flex flex-wrap items-center justify-between gap-2"><dt className="font-semibold">Login email</dt><dd className="break-all text-zinc-700">{subscription.account_email || 'Not set'}</dd></div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <dt className="font-semibold">Password</dt>
          <dd className="flex flex-wrap items-center gap-2 text-zinc-700">
            {subscription.has_password ? (
              <>
                <CredentialReveal url={`/api/accounts/teams/${team.id}/subscriptions/${subscription.id}/password/`} />
              </>
            ) : 'Not set'}
          </dd>
        </div>
      </dl>
      {team.role === 'owner' && <Link className="justify-self-start text-sm font-semibold underline underline-offset-3" to={'/subscriptions/' + subscription.id + '/edit/'}>Edit subscription</Link>}
    </article>
  )
}

export function TeamDetailPage() {
  const { teamId } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { state } = useLocation()
  const incomingNotice = typeof state?.notice === 'string' ? state.notice : ''
  const [team, setTeam] = useState<Team | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(incomingNotice)
  const [saving, setSaving] = useState(false)
  const [confirmation, setConfirmation] = useState<'leave' | 'delete' | null>(null)
  const endpoint = '/api/accounts/teams/' + teamId + '/'

  useEffect(() => {
    let active = true
    setTeam(null)
    setError('')
    setConfirmation(null)
    setNotice(incomingNotice)
    api<Team>(endpoint).then((reply) => {
      if (active) setTeam(reply)
    }).catch((failure) => {
      if (active) setError(messageFrom(failure))
    })
    return () => { active = false }
  }, [endpoint, incomingNotice])

  async function action(path: string, method: 'POST' | 'DELETE', success: string, options?: {
    data?: Record<string, FormDataEntryValue>
    returnToTeams?: boolean
    resetForm?: HTMLFormElement
  }) {
    setError('')
    setNotice('')
    setSaving(true)
    try {
      const reply = await api<{ message?: string }>(path, {
        method,
        body: options?.data ? JSON.stringify(options.data) : undefined,
      })
      if (options?.returnToTeams) {
        navigate('/accounts/teams/', { state: { notice: reply.message ?? success }, replace: true })
        return
      }
      options?.resetForm?.reset()
      setTeam(await api<Team>(endpoint))
      setNotice(reply.message ?? success)
    } catch (failure) {
      setError(messageFrom(failure))
    } finally {
      setSaving(false)
    }
  }

  function onInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    void action(endpoint + 'invite/', 'POST', 'Invitation sent.', { data: formData(form), resetForm: form })
  }

  function reject(event: FormEvent<HTMLFormElement>, id: number) {
    event.preventDefault()
    void action('/api/accounts/teams/requests/' + id + '/reject/', 'POST', 'Request rejected.', { data: formData(event.currentTarget) })
  }

  const isOwner = team?.role === 'owner'
  return (
    <div className="mx-auto grid w-full max-w-7xl gap-5 p-4 sm:p-8">
      <Link className={secondaryClass + ' justify-self-start'} to="/accounts/teams/"><ArrowLeft size={15} aria-hidden /> Teams</Link>
      <ErrorMessage message={error} />
      <StatusMessage message={notice} />
      {!team && !error && <p role="status" className="text-sm text-zinc-600">Loading team…</p>}
      {team && <>
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-12 shrink-0 place-items-center rounded-xl" style={{ backgroundColor: team.accent_color }}><UsersRound size={22} aria-hidden /></span>
            <h1 className="break-words text-3xl font-bold tracking-tight">{team.name}</h1>
          </div>
          <Link className={primaryClass} to={'/subscriptions/add/?team=' + team.id}><Plus size={18} aria-hidden />{isOwner ? 'Add subscription' : 'Create request'}</Link>
        </header>
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="grid gap-5">
            <section className={panelClass}>
              <h2 className="mb-4 text-lg font-bold">Subscriptions</h2>
              {team.subscriptions.length ? (
                <div className="grid gap-3 lg:grid-cols-2">
                  {team.subscriptions.map((item) => <SubscriptionCard key={item.id} subscription={item} team={team} />)}
                </div>
              ) : <p className="text-sm text-zinc-600">No subscriptions yet.</p>}
            </section>
            <section className={panelClass}>
              <h2 className="mb-4 text-lg font-bold">Pending requests</h2>
              {team.pending_requests.length ? (
                <div className="grid gap-3">
                  {team.pending_requests.map((item) => (
                    <article key={item.id} className="grid gap-3 rounded-xl border border-zinc-200 p-4">
                      <div>
                        <h3 className="font-semibold">{item.service_name}</h3>
                        <p className="text-sm text-zinc-600">Requested by {item.requested_by} on {new Date(item.created_at).toLocaleDateString()}</p>
                      </div>
                      {isOwner && (
                        <div className="flex flex-wrap items-center gap-2">
                          <button className={primaryClass} disabled={saving} type="button" onClick={() => void action('/api/accounts/teams/requests/' + item.id + '/approve/', 'POST', 'Request approved and subscription created.')}>Approve</button>
                          <form className="flex flex-wrap gap-2" onSubmit={(event) => reject(event, item.id)}>
                            <input name="decision_note" aria-label="Reason for rejection" placeholder="Reason (optional)" className={fieldClass + ' sm:w-44'} />
                            <button className={dangerClass} disabled={saving}>Reject</button>
                          </form>
                        </div>
                      )}
                    </article>
                  ))}
                </div>
              ) : <p className="text-sm text-zinc-600">No pending requests.</p>}
            </section>
          </div>
          <aside className="grid gap-4">
            <section className={panelClass}>
              <h2 className="mb-4 text-lg font-bold">Members <span className="ml-1 rounded-full bg-zinc-100 px-2 py-1 text-xs">{team.members.length}</span></h2>
              <ul className="grid gap-3">
                {team.members.map((member) => (
                  <li key={member.id} className="flex items-center gap-2">
                    <span className="grid size-9 shrink-0 place-items-center rounded-lg" style={{ backgroundColor: member.avatar_background_color }}>
                      {member.avatar_url ? <img src={member.avatar_url} alt="" className="size-full rounded-lg object-contain" /> : <UsersRound size={17} aria-hidden />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="break-all text-sm font-semibold">{member.email}</p>
                      <p className="text-xs text-zinc-600 capitalize">{member.role}{member.user_id === user?.id && ' · You'}</p>
                    </div>
                    {isOwner && member.role !== 'owner' && member.user_id !== user?.id && (
                      <button className="shrink-0 rounded px-1 text-xs font-semibold text-red-700 hover:underline disabled:opacity-50" type="button" disabled={saving} onClick={() => {
                        if (window.confirm('Remove ' + member.email + ' from this team?')) {
                          void action(endpoint + 'members/' + member.id + '/', 'DELETE', 'Member removed.')
                        }
                      }}>Remove</button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
            {isOwner && (
              <section className={panelClass}>
                <h2 className="mb-3 text-lg font-bold">Invite member</h2>
                <form className="grid gap-3" onSubmit={onInvite}>
                  <Field label="Email"><input name="email" type="email" placeholder="member@example.com" required className={fieldClass} /></Field>
                  <Field label="Role"><select name="role" className={fieldClass} defaultValue="member"><option value="member">Member</option><option value="owner">Owner</option></select></Field>
                  <button className={primaryClass} disabled={saving}>Send invite</button>
                </form>
              </section>
            )}
            <section className={panelClass + ' grid gap-3'} aria-label="Team membership actions">
              {confirmation ? (
                <>
                  <p className="text-sm font-semibold">{confirmation === 'delete' ? 'Permanently delete this team and its subscriptions?' : 'Leave this team and lose access to its subscriptions?'}</p>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" className={secondaryClass} disabled={saving} onClick={() => setConfirmation(null)}>Cancel</button>
                    <button type="button" className={dangerClass} disabled={saving} onClick={() => void action(
                      confirmation === 'delete' ? endpoint : endpoint + 'leave/',
                      confirmation === 'delete' ? 'DELETE' : 'POST',
                      '',
                      { returnToTeams: true },
                    )}>{confirmation === 'delete' ? 'Delete team' : 'Leave team'}</button>
                  </div>
                </>
              ) : (
                <>
                  <button type="button" className={secondaryClass} disabled={saving} onClick={() => setConfirmation('leave')}>Leave team</button>
                  {isOwner && <button type="button" className={dangerClass} disabled={saving} onClick={() => setConfirmation('delete')}>Delete team</button>}
                </>
              )}
            </section>
          </aside>
        </div>
      </>}
    </div>
  )
}
