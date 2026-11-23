import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Camera, CreditCard, KeyRound, SlidersHorizontal, Trash2, UserRound } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { AvatarPicker, type SavedAvatar } from './AvatarPicker'
import { SecuritySettings } from './SecuritySettings'
import { type AccountUser, useAuth } from './auth'
import { dangerClass, ErrorMessage, Field, fieldClass, formData, messageFrom, panelClass, primaryClass, secondaryClass, StatusMessage } from './Controls'

const sections = [
  { id: 'profile', title: 'Profile', icon: UserRound },
  { id: 'billing', title: 'Plan & billing', icon: CreditCard },
  { id: 'preferences', title: 'Preferences', icon: SlidersHorizontal },
  { id: 'password', title: 'Password', icon: KeyRound },
  { id: 'security', title: 'Security', icon: KeyRound },
  { id: 'delete', title: 'Delete account', icon: Trash2 },
] as const

type SectionId = typeof sections[number]['id']
type Settings = {
  user: AccountUser
  profile: {
    first_name: string
    last_name: string
    display_name: string
    email: string
    bio: string
    timezone: string
    preferred_currency: string
    avatar_choice: string
    avatar_background: string
  }
  billing: {
    subscription_plan: string
    plan_status: string
    plan_renews_on: string | null
  }
  preferences: {
    product_updates_enabled: boolean
    marketing_emails_enabled: boolean
  }
  timezones: string[]
  plans: [string, string][]
  plan_statuses: [string, string][]
}

export function SettingsPage() {
  const { setUser } = useAuth()
  const navigate = useNavigate()
  const [section, setSection] = useState<SectionId>('profile')
  const [settings, setSettings] = useState<Settings | null>(null)
  const [avatarOpen, setAvatarOpen] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let active = true
    api<Settings>('/api/accounts/settings/').then((data) => {
      if (active) setSettings(data)
    }).catch((failure) => {
      if (active) setError(messageFrom(failure))
    })
    return () => { active = false }
  }, [])

  function chooseSection(id: SectionId) {
    setSection(id)
    setError('')
    setNotice('')
  }

  function saveAvatar(reply: SavedAvatar) {
    setUser(reply.user)
    setSettings((current) => current && {
      ...current,
      user: reply.user,
      profile: { ...current.profile, avatar_choice: reply.avatar_choice, avatar_background: reply.avatar_background },
    })
    setNotice('Avatar updated.')
    setError('')
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    setError('')
    setNotice('')
    setSaving(true)
    try {
      const reply = await api<{ user: AccountUser } | undefined>('/api/accounts/settings/' + section + '/', {
        method: 'POST',
        body: JSON.stringify(formData(form)),
      })
      if (section === 'delete') {
        setUser(null)
        navigate('/', { replace: true })
        return
      }
      if (reply) setUser(reply.user)
      if (section === 'password') form.reset()
      setSettings(await api<Settings>('/api/accounts/settings/'))
      setVersion((current) => current + 1)
      setNotice(section === 'password' ? 'Password saved.' : 'Settings saved.')
    } catch (failure) {
      setError(messageFrom(failure))
    } finally {
      setSaving(false)
    }
  }

  const active = sections.find((item) => item.id === section)
  return (
    <div className="mx-auto w-full max-w-6xl p-4 sm:p-8">
      <h1 className="mb-5 text-3xl font-bold tracking-tight text-zinc-950">Settings</h1>
      <div className="grid items-start gap-5 lg:grid-cols-[13rem_minmax(0,1fr)]">
        <nav aria-label="Settings" className="flex flex-wrap gap-1 rounded-2xl border border-zinc-200 bg-white p-2 lg:grid">
          {sections.map(({ id, title, icon: Icon }) => (
            <button key={id} type="button" aria-current={id === section ? 'page' : undefined} onClick={() => chooseSection(id)} disabled={saving || !settings} className="flex items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-semibold text-zinc-700 hover:bg-zinc-100 aria-[current=page]:bg-[#f2f6d7] aria-[current=page]:text-zinc-950 disabled:opacity-60">
              <Icon size={16} aria-hidden />{title}
            </button>
          ))}
        </nav>
        <section aria-labelledby="settings-section" className={panelClass}>
          <h2 id="settings-section" className="mb-5 text-xl font-bold">{active?.title}</h2>
          <div className="mb-4 flex flex-wrap gap-3"><Link className={secondaryClass} to="/planning/alerts/">Notification preferences</Link><Link className={secondaryClass} to="/planning/connections/">Connected accounts</Link><Link className={secondaryClass} to="/planning/data/">Backup & restore</Link></div>
          <div className="grid gap-3">
            <ErrorMessage message={error} />
            <StatusMessage message={notice} />
            {!settings && !error && <p role="status" className="text-sm text-zinc-600">Loading settings…</p>}
          </div>
          {settings && section === 'security' && <SecuritySettings />}
          {settings && section !== 'security' && (
            <form key={section + version} onSubmit={save} className="mt-4 grid gap-4">
              {section === 'profile' && <>
                <div className="mb-2 flex items-center gap-4">
                  {settings.user.avatar_url ? (
                    <img className="size-18 rounded-2xl object-contain" src={settings.user.avatar_url} alt="" style={{ backgroundColor: settings.user.avatar_background_color }} />
                  ) : <div className="grid size-18 place-items-center rounded-2xl bg-zinc-100"><UserRound aria-hidden size={28} /></div>}
                  <button type="button" className={secondaryClass} onClick={() => setAvatarOpen(true)}><Camera size={16} aria-hidden /> Edit avatar</button>
                  <input type="hidden" name="avatar_choice" value={settings.profile.avatar_choice} />
                  <input type="hidden" name="avatar_background" value={settings.profile.avatar_background} />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="First name"><input className={fieldClass} name="first_name" defaultValue={settings.profile.first_name} autoComplete="given-name" maxLength={150} /></Field>
                  <Field label="Last name"><input className={fieldClass} name="last_name" defaultValue={settings.profile.last_name} autoComplete="family-name" maxLength={150} /></Field>
                  <Field label="Display name"><input className={fieldClass} name="display_name" defaultValue={settings.profile.display_name} maxLength={120} /></Field>
                  <Field label="Email"><input className={fieldClass} type="email" name="email" defaultValue={settings.profile.email} autoComplete="email" required /></Field>
                  {settings.user.has_usable_password && <Field label="Current password (when changing email)"><input className={fieldClass} type="password" name="current_password" autoComplete="current-password" /></Field>}
                  <Field label="Time zone">
                    <select name="timezone" className={fieldClass} defaultValue={settings.profile.timezone}>
                      {settings.timezones.map((tz) => <option key={tz} value={tz}>{tz}</option>)}
                    </select>
                  </Field>
                  <Field label="Preferred currency">
                    <input className={fieldClass} name="preferred_currency" defaultValue={settings.profile.preferred_currency} maxLength={3} pattern="[A-Za-z]{3}" required />
                  </Field>
                </div>
                <Field label="Bio"><textarea className={fieldClass} name="bio" rows={3} defaultValue={settings.profile.bio} maxLength={280} /></Field>
              </>}
              {section === 'billing' && <>
                <div className="rounded-xl border border-lime-200 bg-lime-50 p-5"><h3 className="text-xl font-bold">DUES Free</h3><p className="mt-2 text-sm text-zinc-700">All current tracking, planning, and team features are included. DUES does not charge you, and there is no plan renewal date.</p></div>
              </>}
              {section === 'preferences' && <>
                <label className="flex items-center gap-3 rounded-xl border border-zinc-200 p-4 text-sm font-semibold">
                  <input type="checkbox" name="product_updates_enabled" defaultChecked={settings.preferences.product_updates_enabled} className="size-4 accent-zinc-900" />
                  Email me product updates
                </label>
                <label className="flex items-center gap-3 rounded-xl border border-zinc-200 p-4 text-sm font-semibold">
                  <input type="checkbox" name="marketing_emails_enabled" defaultChecked={settings.preferences.marketing_emails_enabled} className="size-4 accent-zinc-900" />
                  Email me news and offers
                </label>
              </>}
              {section === 'password' && <>
                {settings.user.has_usable_password && (
                  <Field label="Current password"><input required name="old_password" type="password" autoComplete="current-password" className={fieldClass} /></Field>
                )}
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="New password"><input required name="new_password1" type="password" autoComplete="new-password" className={fieldClass} minLength={8} /></Field>
                  <Field label="Confirm new password"><input required name="new_password2" type="password" autoComplete="new-password" className={fieldClass} minLength={8} /></Field>
                </div>
              </>}
              {section === 'delete' && <>
                <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">Deleting your account permanently removes your subscription data.</p>
                <Field label="Confirm your email"><input required name="confirm_email" type="email" className={fieldClass} /></Field>
                <Field label="Type DELETE to confirm"><input required name="confirm_phrase" className={fieldClass} autoComplete="off" /></Field>
                {settings.user.has_usable_password && (
                  <Field label="Current password"><input required name="current_password" type="password" autoComplete="current-password" className={fieldClass} /></Field>
                )}
              </>}
              {section !== 'billing' && <div className="flex justify-end border-t border-zinc-100 pt-4">
                <button disabled={saving} className={section === 'delete' ? dangerClass : primaryClass}>
                  {section === 'delete' ? 'Delete account' : section === 'password' ? 'Save password' : 'Save changes'}
                </button>
              </div>}
            </form>
          )}
        </section>
      </div>
      {avatarOpen && settings && <AvatarPicker avatar={settings.profile.avatar_choice} background={settings.profile.avatar_background} onSave={saveAvatar} onClose={() => setAvatarOpen(false)} />}
    </div>
  )
}
