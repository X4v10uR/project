import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Check, X } from 'lucide-react'
import { api } from '../api'
import type { AccountUser } from './auth'
import { ErrorMessage, Field, fieldClass, messageFrom, primaryClass, secondaryClass } from './Controls'

type Avatar = {
  path: string
  url: string
  person: string
  skin_tone: string
  mood_label: string
}

type AvatarOptions = {
  sections: Record<'male' | 'female', Avatar[]>
  backgrounds: { key: string; label: string; color: string }[]
}

export type SavedAvatar = {
  user: AccountUser
  avatar_choice: string
  avatar_background: string
}

export function AvatarPicker({ avatar, background, onSave, onClose }: {
  avatar: string
  background: string
  onSave: (reply: SavedAvatar) => void
  onClose: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [options, setOptions] = useState<AvatarOptions | null>(null)
  const [selection, setSelection] = useState(avatar)
  const [color, setColor] = useState(background)
  const [section, setSection] = useState<'male' | 'female'>(avatar.startsWith('female_memoji/') ? 'female' : 'male')
  const [search, setSearch] = useState('')
  const [limit, setLimit] = useState(36)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!dialog.current?.open) dialog.current?.showModal()
    let active = true
    api<AvatarOptions>('/api/accounts/settings/avatar/').then((data) => {
      if (active) setOptions(data)
    }).catch((failure) => {
      if (active) setError(messageFrom(failure))
    })
    return () => { active = false }
  }, [])

  const query = search.trim().toLowerCase()
  const matches = options?.sections[section].filter((item) => (
    [item.person, item.skin_tone, item.mood_label].some((value) => value.toLowerCase().includes(query))
  )) ?? []
  const selectedColor = options?.backgrounds.find((item) => item.key === color)?.color

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      const reply = await api<SavedAvatar>('/api/accounts/settings/avatar/', {
        method: 'POST',
        body: JSON.stringify({ avatar_choice: selection, avatar_background: color }),
      })
      onSave(reply)
      onClose()
    } catch (failure) {
      setError(messageFrom(failure))
    } finally {
      setSaving(false)
    }
  }

  return (
    <dialog ref={dialog} onClose={onClose} aria-labelledby="avatar-picker-title" className="m-auto max-h-[90dvh] w-[min(92vw,43rem)] overflow-auto rounded-2xl border border-zinc-200 bg-white p-5 text-zinc-900 shadow-2xl backdrop:bg-zinc-950/40 sm:p-6">
      <form onSubmit={save} className="grid gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 id="avatar-picker-title" className="text-xl font-bold">Select avatar</h2>
          <button type="button" className="rounded-lg p-2 hover:bg-zinc-100" aria-label="Close avatar picker" onClick={onClose}><X size={20} aria-hidden /></button>
        </div>
        <ErrorMessage message={error} />
        {!options && !error && <p role="status" className="text-sm text-zinc-600">Loading avatars…</p>}
        {options && <>
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-1 text-sm font-semibold text-zinc-700">Background</span>
            {options.backgrounds.map((item) => (
              <button key={item.key} type="button" aria-label={item.label} title={item.label} aria-pressed={color === item.key} style={{ backgroundColor: item.color }} onClick={() => setColor(item.key)} className="grid size-9 place-items-center rounded-full border border-black/10">
                {color === item.key && <Check size={16} aria-hidden />}
              </button>
            ))}
          </div>
          <div className="grid gap-3 sm:grid-cols-[9rem_1fr]">
            <Field label="Characters">
              <select className={fieldClass} value={section} onChange={(event) => { setSection(event.target.value as typeof section); setLimit(36) }}>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
            </Field>
            <Field label="Search avatars">
              <input className={fieldClass} type="search" placeholder="Name, skin tone or expression" value={search} onChange={(event) => { setSearch(event.target.value); setLimit(36) }} />
            </Field>
          </div>
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
            {matches.slice(0, limit).map((item) => {
              const label = [item.person, item.skin_tone, item.mood_label].filter(Boolean).join(', ')
              return (
                <button key={item.path} type="button" aria-label={label} title={label} aria-pressed={selection === item.path} onClick={() => setSelection(item.path)} style={{ backgroundColor: selectedColor }} className="aspect-square rounded-xl border border-black/10 p-1 aria-pressed:ring-2 aria-pressed:ring-inset aria-pressed:ring-zinc-900">
                  <img src={item.url} alt="" className="h-full w-full object-contain" loading="lazy" />
                </button>
              )
            })}
          </div>
          {!matches.length && <p className="text-sm text-zinc-600">No avatars found.</p>}
          {matches.length > limit && <button type="button" className={secondaryClass + ' justify-self-center'} onClick={() => setLimit(limit + 36)}>Show more</button>}
        </>}
        <div className="sticky bottom-0 flex justify-end gap-2 bg-white pt-3">
          <button type="button" className={secondaryClass} onClick={onClose}>Cancel</button>
          <button className={primaryClass} disabled={!options || saving}>Save avatar</button>
        </div>
      </form>
    </dialog>
  )
}
