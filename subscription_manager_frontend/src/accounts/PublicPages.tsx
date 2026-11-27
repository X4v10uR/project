import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Eye, EyeOff, ShieldCheck, Zap } from 'lucide-react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { type AccountUser, useAuth } from './auth'
import { AuthLayout } from './AuthLayout'
import { ErrorMessage, fieldClass, formData, messageFrom, primaryClass, secondaryClass } from './Controls'

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

function PasswordInput({ id, name, autocomplete, authStyle = false, describedBy }: {
  id: string; name: string; autocomplete: string; authStyle?: boolean; describedBy?: string;
}) {
  const [show, setShow] = useState(false)
  const Icon = show ? EyeOff : Eye
  return (
    <div className={authStyle ? 'auth-password-wrap' : 'relative'}>
      <input id={id} name={name} autoComplete={autocomplete} type={show ? 'text' : 'password'} required
        aria-describedby={describedBy} placeholder={authStyle ? 'Enter your password' : undefined}
        className={authStyle ? 'auth-input auth-password-input' : fieldClass + ' pr-12'} />
      <button type="button" className={authStyle ? 'auth-password-toggle' : 'absolute inset-y-0 right-0 grid w-11 place-items-center text-zinc-600'}
        onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'} aria-pressed={show} aria-controls={id}>
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
  const [showOtp, setShowOtp] = useState(false)
  const rawNext = search.get('next') ?? ''
  const next = /^\/(?![\/\\])[^\\\u0000-\u001f]*$/u.test(rawNext) ? rawNext : '/dashboard/'
  const switchQuery = search.has('next') ? '?' + new URLSearchParams({ next }).toString() : ''

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSaving(true)
    const fields = formData(event.currentTarget)
    try {
      const reply = await api<{ user: AccountUser }>(signup ? '/api/accounts/signup/' : '/api/accounts/login/', {
        method: 'POST',
        body: JSON.stringify(signup ? fields : { ...fields, remember: fields.remember === 'on' }),
      })
      setUser(reply.user)
      navigate(next, { replace: true })
    } catch (failure) {
      setError(messageFrom(failure))
      if (messageFrom(failure).includes('authenticator code')) setShowOtp(true)
    } finally {
      setSaving(false)
    }
  }

  return (
    <AuthLayout>
      <h1 className="auth-heading">{signup ? 'Create an account' : 'Welcome back'}</h1>
      <p className="auth-description">{signup ? 'A little less admin. A lot more peace of mind.' : 'Welcome back! Please enter your details.'}</p>
      <form onSubmit={submit} className="auth-form" aria-label={signup ? 'Create your account' : 'Sign in to DUES'} aria-busy={saving}>
        {error && <p className="auth-error" role="alert">{error}</p>}
        <div className="auth-field">
          <label htmlFor="auth-email" className="auth-label">Email</label>
          <input id="auth-email" name="email" type="email" autoComplete="username" placeholder="Enter your email"
            autoCapitalize="none" spellCheck={false} defaultValue={search.get('email') ?? ''} required className="auth-input" />
        </div>
        <div className="auth-field">
          <label htmlFor="auth-password" className="auth-label">Password</label>
          <PasswordInput id="auth-password" name={signup ? 'password1' : 'password'} autocomplete={signup ? 'new-password' : 'current-password'}
            authStyle describedBy={signup ? 'auth-password-hint' : undefined} />
          {signup && <p className="auth-field-hint" id="auth-password-hint">Use at least 8 characters. Avoid common passwords.</p>}
        </div>
        {signup && <div className="auth-field">
          <label htmlFor="auth-confirm-password" className="auth-label">Confirm password</label>
          <PasswordInput id="auth-confirm-password" name="password2" autocomplete="new-password" authStyle />
        </div>}
        {!signup && showOtp && <div className="auth-field" id="auth-code-field">
          <label htmlFor="auth-code" className="auth-label">Authenticator or recovery code</label>
          <input id="auth-code" name="otp" autoComplete="one-time-code" placeholder="Enter your code" className="auth-input" />
        </div>}
        {!signup && <div className="auth-options">
          <label className="auth-remember"><input type="checkbox" name="remember" />Remember for 30 days</label>
          <a className="auth-text-link" href="/accounts/password-reset/">Forgot password</a>
        </div>}
        <div className="auth-actions">
          <button type="submit" className="auth-submit" disabled={saving || loading}>
            {saving ? (signup ? 'Creating account…' : 'Signing in…') : (signup ? 'Create account' : 'Sign in')}
          </button>
          {!signup && <button type="button" className="auth-code-toggle" aria-expanded={showOtp} aria-controls="auth-code-field" onClick={() => setShowOtp(!showOtp)}>
            <ShieldCheck size={20} aria-hidden="true" />{showOtp ? 'Hide authenticator code' : 'Use an authenticator code'}
          </button>}
        </div>
      </form>
      <p className="auth-switch">
        {signup ? 'Already have an account?' : 'Don’t have an account?'}{' '}
        <Link className="auth-text-link" to={(signup ? '/accounts/login/' : '/accounts/signup/') + switchQuery}>
          {signup ? 'Log in' : 'Sign up'}
        </Link>
      </p>
    </AuthLayout>
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
