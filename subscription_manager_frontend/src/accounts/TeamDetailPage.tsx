import { ServiceIcon } from '../ServiceIcon'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ArrowLeft, Plus, UsersRound } from 'lucide-react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { CredentialReveal } from './SecuritySettings'
import { displayDate } from '../subscriptions/shared'
import { SavedRenewal } from '../subscriptions/SavedRenewal'
import { useAuth } from './auth'
import { dangerClass, ErrorMessage, Field, fieldClass, formData, messageFrom, panelClass, primaryClass, secondaryClass, StatusMessage } from './Controls'
import { type Role, type TeamSubscription, TeamStatus } from './TeamPages'

type Member = {
  id: number
  user_id: number
  email: string
  role: Role
  can_view_credentials: boolean
  avatar_url: string
  avatar_background_color: string
}

type PendingRequest = {
  id: number
  service_name: string
  requested_by: string
  created_at: string
}

type PendingInvite = {
  id: number
  email: string
  role: Role
  expires_at: string
  status: 'ready' | 'expired'
}

type Renewal = {
  assignee_id: number | null
  renewal_date: string | null
  due_on: string | null
  decision: '' | 'keep' | 'change' | 'cancel'
  decided_at: string | null
  decided_by: string | null
  can_decide: boolean
}

type TeamSubscriptionDetail = TeamSubscription & { renewal: Renewal }
type RenewalFields = Record<string, FormDataEntryValue | null>

type Team = {
  id: number
  name: string
  role: Role
  can_view_credentials: boolean
  accent_color: string
  subscriptions: TeamSubscriptionDetail[]
  members: Member[]
  pending_requests: PendingRequest[]
  pending_invites: PendingInvite[]
}

function RenewalPanel({ renewal, team, saving, onUpdate }: {
  renewal: Renewal; team: Team; saving: boolean; onUpdate: (fields: RenewalFields) => void
}) {
  const assignee = team.members.find(person => person.id === renewal.assignee_id)
  const labels = { '': 'Awaiting decision', keep: 'Keep', change: 'Change', cancel: 'Cancel' }
  function assign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onUpdate({ assignee_id: new FormData(event.currentTarget).get('assignee_id') || null })
  }
  function decide(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onUpdate({ decision: new FormData(event.currentTarget).get('decision'), renewal_date: renewal.renewal_date })
  }
  return <section className="grid gap-2 border-t border-zinc-200 pt-3 text-sm" aria-label="Renewal responsibility">
    <h4 className="font-bold">Renewal decision</h4>
    <p>Responsible person · {assignee?.email || 'Unassigned'}</p>
    {renewal.renewal_date ? <>
      <p>Renewal {displayDate(renewal.renewal_date)} · Decide by {displayDate(renewal.due_on)}</p>
      <p className="font-semibold">{labels[renewal.decision]}</p>
      {renewal.decided_at && <p className="text-zinc-600">Recorded {new Date(renewal.decided_at).toLocaleString()}{renewal.decided_by && ' by ' + renewal.decided_by}</p>}
    </> : <p>No upcoming payment scheduled.</p>}
    {team.role === 'owner' && <form className="grid gap-2" onSubmit={assign}>
      <Field label="Renewal owner"><select className={fieldClass} name="assignee_id" key={renewal.assignee_id ?? ''} defaultValue={renewal.assignee_id ?? ''}>
        <option value="">Unassigned</option>
        {team.members.filter(person => person.role === 'owner' || person.role === 'member').map(person => <option key={person.id} value={person.id}>{person.email}</option>)}
      </select></Field>
      <button className={secondaryClass + ' justify-self-start'} disabled={saving}>Save assignment</button>
    </form>}
    {renewal.can_decide && <form className="grid gap-2" onSubmit={decide}>
      <Field label="Decision for this renewal"><select className={fieldClass} name="decision" key={renewal.renewal_date + renewal.decision} defaultValue={renewal.decision}>
        {Object.entries(labels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></Field>
      <p className="text-xs text-zinc-600">Record the team's plan here. Complete plan changes or cancellation with the provider.</p>
      <button className={secondaryClass + ' justify-self-start'} disabled={saving}>Save decision</button>
    </form>}
  </section>
}

function SubscriptionCard({ subscription, team, saving, onUpdate }: {
  subscription: TeamSubscriptionDetail; team: Team; saving: boolean; onUpdate: (fields: RenewalFields) => void
}) {

  return (
    <article id={`subscription-${subscription.id}`} tabIndex={-1} className="grid gap-3 rounded-xl border border-zinc-200 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <ServiceIcon name={subscription.service_name} accent={team.accent_color} />
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
            {subscription.has_password && team.can_view_credentials ? (
              <>
                <CredentialReveal url={`/api/accounts/teams/${team.id}/subscriptions/${subscription.id}/password/`} />
              </>
            ) : subscription.has_password ? 'Restricted by team permissions' : 'Not set'}
          </dd>
        </div>
      </dl>
      <RenewalPanel renewal={subscription.renewal} team={team} saving={saving} onUpdate={onUpdate} />
      {team.role === 'owner' && <Link className="justify-self-start text-sm font-semibold underline underline-offset-3" to={'/subscriptions/' + subscription.id + '/edit/'}>Edit subscription</Link>}
    </article>
  )
}

export function TeamDetailPage() {
  const { teamId } = useParams()
  const { user } = useAuth()
  const navigate = useNavigate()
  const { state, hash } = useLocation()
  const incomingNotice = typeof state?.notice === 'string' ? state.notice : ''
  const [team, setTeam] = useState<Team | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(incomingNotice)
  const [saving, setSaving] = useState(false)
  const [inviteUrl, setInviteUrl] = useState('')
  const [confirmation, setConfirmation] = useState<'leave' | 'delete' | null>(null)
  const endpoint = '/api/accounts/teams/' + teamId + '/'

  useEffect(() => {
    let active = true
    setTeam(null)
    setError('')
    setConfirmation(null)
    setInviteUrl('')
    setNotice(incomingNotice)
    api<Team>(endpoint).then((reply) => {
      if (active) setTeam(reply)
    }).catch((failure) => {
      if (active) setError(messageFrom(failure))
    })
    return () => { active = false }
  }, [endpoint, incomingNotice])

  useEffect(() => {
    if (team && /^#(?:request|subscription)-\d+$/.test(hash)) {
      document.getElementById(hash.slice(1))?.focus()
    }
  }, [team, hash])

  async function action(path: string, method: 'POST' | 'DELETE' | 'PATCH', success: string, options?: {
    data?: Record<string, FormDataEntryValue | null>
    returnToTeams?: boolean
    resetForm?: HTMLFormElement
  }) {
    setError('')
    setNotice('')
    setInviteUrl('')
    setSaving(true)
    try {
      const reply = await api<{ message?: string; invite_url?: string }>(path, {
        method,
        body: options?.data ? JSON.stringify(options.data) : undefined,
      })
      if (options?.returnToTeams) {
        navigate('/accounts/teams/', { state: { notice: reply.message ?? success }, replace: true })
        return
      }
      options?.resetForm?.reset()
      setTeam(await api<Team>(endpoint))
      setInviteUrl(reply.invite_url ?? '')
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
      {state?.savedSubscriptionId && <SavedRenewal subscriptionId={state.savedSubscriptionId} />}
      {!team && !error && <p role="status" className="text-sm text-zinc-600">Loading team…</p>}
      {team && <>
        <header className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-12 shrink-0 place-items-center rounded-xl" style={{ backgroundColor: team.accent_color }}><UsersRound size={22} aria-hidden /></span>
            <h1 className="break-words text-3xl font-bold tracking-tight">{team.name}</h1>
          </div>
          {(isOwner || team.role === 'member') && <Link className={primaryClass} to={'/subscriptions/add/?team=' + team.id}><Plus size={18} aria-hidden />{isOwner ? 'Add subscription' : 'Create request'}</Link>}
        </header>
        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="grid gap-5">
            <section className={panelClass}>
              <h2 className="mb-4 text-lg font-bold">Subscriptions</h2>
              {team.subscriptions.length ? (
                <div className="grid gap-3 lg:grid-cols-2">
                  {team.subscriptions.map(item => <SubscriptionCard key={item.id} subscription={item} team={team} saving={saving}
                    onUpdate={fields => void action(endpoint + 'subscriptions/' + item.id + '/renewal/', 'PATCH', 'Renewal updated.', { data: fields })} />)}
                </div>
              ) : <p className="text-sm text-zinc-600">No subscriptions yet.</p>}
            </section>
            <section className={panelClass}>
              <h2 className="mb-4 text-lg font-bold">Pending requests</h2>
              {team.pending_requests.length ? (
                <div className="grid gap-3">
                  {team.pending_requests.map((item) => (
                    <article id={`request-${item.id}`} tabIndex={-1} key={item.id} className="grid gap-3 rounded-xl border border-zinc-200 p-4">
                      <div>
                        <h3 className="flex items-center gap-2 font-semibold"><ServiceIcon name={item.service_name} className="size-7" />{item.service_name}</h3>
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
              <p className="mb-3 text-xs text-zinc-500">Viewers read subscriptions. Accountants manage payments, receipts and budgets. Members can request subscriptions; owners manage the team.</p>
              <ul className="grid gap-3">
                {team.members.map((member) => (
                  <li key={member.id} className="flex flex-wrap items-center gap-2">
                    <span className="grid size-9 shrink-0 place-items-center rounded-lg" style={{ backgroundColor: member.avatar_background_color }}>
                      {member.avatar_url ? <img src={member.avatar_url} alt="" className="size-full rounded-lg object-contain" /> : <UsersRound size={17} aria-hidden />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="break-all text-sm font-semibold">{member.email}</p>
                      <p className="text-xs text-zinc-600 capitalize">{member.role}{member.user_id === user?.id && ' · You'}</p>
                      {isOwner && <form key={member.role + String(member.can_view_credentials)} className="mt-2 grid gap-2" onSubmit={event => { event.preventDefault(); const fields = formData(event.currentTarget); void action(endpoint + 'members/' + member.id + '/', 'PATCH', 'Permissions updated.', { data: { role: fields.role, can_view_credentials: fields.can_view_credentials ? 'true' : 'false' } }) }}><label className="text-xs">Role for {member.email}<select name="role" className={fieldClass} defaultValue={member.role}><option value="owner">Owner</option><option value="member">Member</option><option value="viewer">Viewer</option><option value="accountant">Accountant</option></select></label><label className="flex items-center gap-2 text-xs"><input name="can_view_credentials" type="checkbox" defaultChecked={member.can_view_credentials && member.role === 'member'} />Allow stored credentials for Member role</label><button className={secondaryClass} disabled={saving}>Save permissions</button></form>}
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
                  <Field label="Role"><select name="role" className={fieldClass} defaultValue="member"><option value="member">Member</option><option value="owner">Owner</option><option value="viewer">Viewer</option><option value="accountant">Accountant</option></select></Field>
                  <button className={primaryClass} disabled={saving}>Send invite</button>
                </form>
                {inviteUrl && <div className="mt-4 grid gap-2 text-sm">
                  <p>Share this invitation link with the recipient.</p>
                  <input aria-label="Invitation link" readOnly value={inviteUrl} onFocus={event => event.currentTarget.select()} className={fieldClass} />
                </div>}
                <h3 className="mt-5 mb-3 font-semibold">Pending invitations</h3>
                {team.pending_invites?.length ? <ul className="grid gap-3">
                  {team.pending_invites.map(invite => <li key={invite.id} className="grid gap-2 rounded-xl border border-zinc-200 p-3">
                    <p className="break-all text-sm font-semibold">{invite.email}</p>
                    <p className="text-xs text-zinc-600 capitalize">{invite.role} · {invite.status === 'expired' ? 'Expired' : 'Expires ' + new Date(invite.expires_at).toLocaleString()}</p>
                    <div className="flex flex-wrap gap-2">
                      <button type="button" className={secondaryClass} disabled={saving} onClick={() => void action(endpoint + 'invite/', 'POST', 'Invitation re-sent.', { data: { email: invite.email, role: invite.role } })}>Resend invite</button>
                      <button type="button" className={dangerClass} disabled={saving} onClick={() => void action(endpoint + 'invites/' + invite.id + '/', 'DELETE', 'Invitation revoked.')}>Revoke invite</button>
                    </div>
                  </li>)}
                </ul> : <p className="text-sm text-zinc-600">No pending invitations.</p>}
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
