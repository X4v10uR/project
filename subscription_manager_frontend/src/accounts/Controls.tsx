import type { ReactNode } from 'react'

export const fieldClass = 'w-full min-w-0 rounded-xl border border-zinc-200 bg-white px-3.5 py-2.5 text-sm text-zinc-900 outline-none placeholder:text-zinc-400 focus:border-zinc-600'
export const primaryClass = 'inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-[#e8f542] px-4 py-2.5 text-sm font-semibold text-zinc-950 hover:bg-[#dce83d] disabled:opacity-50'
export const secondaryClass = 'inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-semibold text-zinc-800 hover:bg-zinc-100 disabled:opacity-50'
export const dangerClass = 'inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-red-200 bg-white px-4 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50'
export const panelClass = 'rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm sm:p-6'

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid min-w-0 gap-1.5 text-sm font-semibold text-zinc-800">{label}{children}</label>
}

export function ErrorMessage({ message }: { message: string }) {
  if (!message) return null
  return <p role="alert" className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{message}</p>
}

export function StatusMessage({ message }: { message: string }) {
  if (!message) return null
  return <p role="status" className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-sm text-zinc-700">{message}</p>
}

export function messageFrom(error: unknown) {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}

export function formData(form: HTMLFormElement) {
  return Object.fromEntries(new FormData(form))
}
