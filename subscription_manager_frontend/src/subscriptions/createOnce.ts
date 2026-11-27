import { api, ApiError } from '../api'
import { subscriptionApi } from './shared'

const pending = new Map<string, string>()

function operationKey(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

function readKey(scope: string) {
  try { return sessionStorage.getItem(scope) ?? pending.get(scope) }
  catch { return pending.get(scope) }
}

function saveKey(scope: string, key: string) {
  pending.set(scope, key)
  // Retain only the opaque key across refreshes. Never store form contents.
  try { sessionStorage.setItem(scope, key) } catch { /* memory fallback */ }
}

function clearKey(scope: string, key: string) {
  if (pending.get(scope) === key) pending.delete(scope)
  try {
    if (sessionStorage.getItem(scope) === key) sessionStorage.removeItem(scope)
  } catch { /* memory fallback */ }
}

export async function createSubscription<T>(scope: string, body: string): Promise<T> {
  const storageKey = `dues:subscription-create:${scope}`
  const key = readKey(storageKey) ?? operationKey()
  saveKey(storageKey, key)
  try {
    const result = await api<T>(subscriptionApi, {
      method: 'POST', body, headers: { 'Idempotency-Key': key },
    })
    clearKey(storageKey, key)
    return result
  } catch (error) {
    if (error instanceof ApiError && (error.status === 409 || error.status === 410)) {
      // Only a deliberate next submit can start a different operation.
      const code = (error.data as { code?: string } | null)?.code
      if (code === 'idempotency_conflict' || code === 'idempotency_result_unavailable') clearKey(storageKey, key)
    }
    throw error
  }
}
