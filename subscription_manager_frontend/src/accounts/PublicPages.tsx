import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Eye, EyeOff, Zap } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { type AccountUser, useAuth } from './auth'
import { ErrorMessage, Field, fieldClass, formData, messageFrom, primaryClass, secondaryClass } from './Controls'

function PublicAccountLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto grid min-h-[calc(100dvh-4rem)] max-w-360 lg:grid-cols-[1.1fr_1fr]">
      <div className="hidden flex-col justify-center overflow-hidden bg-[#eef0d9] p-12 lg:flex xl:p-18">
        <p className="mb-5 max-w-lg text-5xl leading-tight font-semibold tracking-tight text-zinc-900">
          See all your subscriptions in one place
        </p>
        <img src="/static/images/dashboard.png" alt="DUES dashboard preview" className="mt-7 max-w-none rounded-2xl border border-zinc-200 shadow-xl" />
      </div>
      <div className="flex items-center justify-center bg-white px-6 py-10">
        <div className="w-full max-w-sm">
          <Link to="/" className="mb-10 inline-flex items-center gap-2 text-lg font-bold text-zinc-950">
            <span className="grid size-9 place-items-center rounded-xl bg-[#e8f542]"><Zap aria-hidden size={18} fill="currentColor" /></span>
            DUES
          </Link>
          {children}
        </div>
      </div>
    </div>
  )
}

function PasswordInput({ id, name, autocomplete }: { id: string; name: string; autocomplete: string }) {
  const [show, setShow] = useState(false)
  const Icon = show ? EyeOff : Eye
  return (
    <div className="relative">
      <input id={id} name={name} autoComplete={autocomplete} type={show ? 'text' : 'password'} required className={fieldClass + ' pr-12'} />
      <button type="button" className="absolute inset-y-0 right-0 grid w-11 place-items-center text-zinc-600" onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>
        <Icon size={18} aria-hidden />
      </button>
    </div>
  )
}

function AuthForm({ signup = false }: { signup?: boolean }) {
  const { loading, setUser } = useAuth()
  const [search] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const rawNext = search.get('next') ?? ''
  const next = /^\/(?![\/\\])[^\\\u0000-\u001f]*$/u.test(rawNext) ? rawNext : '/dashboard/'
  const switchQuery = search.has('next') ? '?' + new URLSearchParams({ next }).toString() : ''

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      const reply = await api<{ user: AccountUser }>(signup ? '/api/accounts/signup/' : '/api/accounts/login/', {
        method: 'POST',
        body: JSON.stringify(formData(event.currentTarget)),
      })
      setUser(reply.user)
      navigate(next, { replace: true })
    } catch (failure) {
      setError(messageFrom(failure))
    } finally {
      setSaving(false)
    }
  }

  return (
    <PublicAccountLayout>
      <h1 className="mb-6 text-3xl font-bold tracking-tight">{signup ? 'Create account' : 'Sign in'}</h1>
      <form onSubmit={submit} className="grid gap-4">
        <ErrorMessage message={error} />
        <Field label="Email"><input name="email" type="email" autoComplete="username" defaultValue={search.get('email') ?? ''} required className={fieldClass} /></Field>
        <div className="grid gap-1.5 text-sm font-semibold text-zinc-800">
          <label htmlFor="auth-password">Password</label>
          <PasswordInput id="auth-password" name={signup ? 'password1' : 'password'} autocomplete={signup ? 'new-password' : 'current-password'} />
        </div>
        {!signup && <Field label="Authenticator or recovery code (if enabled)"><input name="otp" autoComplete="one-time-code" className={fieldClass} /></Field>}
        {signup && (
          <div className="grid gap-1.5 text-sm font-semibold text-zinc-800">
            <label htmlFor="auth-confirm-password">Confirm password</label>
            <PasswordInput id="auth-confirm-password" name="password2" autocomplete="new-password" />
          </div>
        )}
        <button className={primaryClass + ' mt-2'} disabled={saving || loading}>{signup ? 'Create account' : 'Sign in'}</button>
      </form>
      {!signup && <a className="mt-5 inline-block text-sm font-semibold underline" href="/accounts/password-reset/">Set or reset your password</a>}
      <p className="mt-5 text-sm text-zinc-600">
        {signup ? 'Already have an account?' : 'New to DUES?'}{' '}
        <Link className="font-semibold text-zinc-950 underline underline-offset-3" to={(signup ? '/accounts/login/' : '/accounts/signup/') + switchQuery}>
          {signup ? 'Sign in' : 'Create an account'}
        </Link>
      </p>
    </PublicAccountLayout>
  )
}

export function LoginPage() {
  return <AuthForm />
}

export function SignupPage() {
  return <AuthForm signup />
}

type InviteStatus = 'ready' | 'email_mismatch' | 'sign_in_required' | 'expired' | 'already_used' | 'revoked' | 'invalid'
type Invite = {
  status: InviteStatus
  team_name?: string
  email?: string
  current_email?: string | null
  requires_account?: boolean
}

const inviteTitles: Record<InviteStatus, string> = {
  ready: 'Accept invitation',
  email_mismatch: 'Switch account to continue',
  sign_in_required: 'Sign in to accept the invitation',
  expired: 'Invite expired',
  already_used: 'Invite already used',
  revoked: 'Invite revoked',
  invalid: 'Invalid invitation',
}

export function InviteAcceptPage() {
  const { token } = useParams()
  const { loading, setUser } = useAuth()
  const navigate = useNavigate()
  const [invite, setInvite] = useState<Invite | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const endpoint = '/api/accounts/invites/accept/' + encodeURIComponent(token ?? '') + '/'
  const loginPath = '/accounts/login/?' + new URLSearchParams({
    next: '/accounts/invites/accept/' + encodeURIComponent(token ?? '') + '/',
    email: invite?.email ?? '',
  })

  useEffect(() => {
    let active = true
    setInvite(null)
    setError('')
    api<Invite>(endpoint).then((reply) => {
      if (active) setInvite(reply)
    }).catch((failure) => {
      if (active) setError(messageFrom(failure))
    })
    return () => { active = false }
  }, [endpoint])

  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = formData(event.currentTarget)
    setSaving(true)
    setError('')
    try {
      const reply = await api<{ team_id: number; user: AccountUser }>(endpoint, {
        method: 'POST',
        body: JSON.stringify(fields),
      })
      setUser(reply.user)
      navigate('/accounts/teams/' + reply.team_id + '/', { replace: true })
    } catch (failure) {
      if (failure instanceof ApiError && failure.data && typeof failure.data === 'object' && 'status' in failure.data) {
        setInvite(failure.data as Invite)
      }
      setError(messageFrom(failure))
    } finally {
      setSaving(false)
    }
  }

  const needsSignIn = invite?.status === 'email_mismatch' || invite?.status === 'sign_in_required'
  return (
    <PublicAccountLayout>
      <div className="grid gap-4">
        <h1 className="text-3xl font-bold tracking-tight">{invite ? inviteTitles[invite.status] : 'Team invitation'}</h1>
        <ErrorMessage message={error} />
        {!invite && !error && <p role="status" className="text-sm text-zinc-600">Loading invitation…</p>}
        {invite?.status === 'email_mismatch' && <p className="text-sm text-zinc-600">You are signed in as {invite.current_email}.</p>}
        {(needsSignIn || invite?.status === 'ready') && <p className="text-sm text-zinc-600">{invite.email} was invited to join {invite.team_name}.</p>}
        {needsSignIn ? (
          <>
            <Link className={primaryClass} to={loginPath}>Sign in with the invited email</Link>
            <a className={secondaryClass} href="/accounts/password-reset/">Set or reset your password</a>
          </>
        ) : invite?.status === 'ready' ? (
          <form onSubmit={accept} className="grid gap-4">
            {invite.requires_account && <>
              <p className="text-sm text-zinc-600">Create your account with {invite.email} and choose a password to sign in again.</p>
              <label htmlFor="invite-password" className="text-sm font-semibold">Password</label>
              <PasswordInput id="invite-password" name="password1" autocomplete="new-password" />
              <label htmlFor="invite-confirm-password" className="text-sm font-semibold">Confirm password</label>
              <PasswordInput id="invite-confirm-password" name="password2" autocomplete="new-password" />
            </>}
            <button className={primaryClass} disabled={loading || saving}>
              {saving ? 'Accepting…' : invite.requires_account ? 'Create account and join team' : 'Accept invitation'}
            </button>
          </form>
        ) : invite && <Link className={secondaryClass} to="/accounts/teams/">Go to teams</Link>}
      </div>
    </PublicAccountLayout>
  )
}
