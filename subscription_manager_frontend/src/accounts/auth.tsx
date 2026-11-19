import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../api'

export type AccountUser = {
  id: number
  email: string
  first_name: string
  last_name: string
  display_name: string
  avatar_url: string
  avatar_background_color: string
  preferred_currency: string
  has_usable_password: boolean
}

type AuthState = {
  user: AccountUser | null
  loading: boolean
  refresh: () => Promise<AccountUser | null>
  logout: () => Promise<void>
  setUser: (user: AccountUser | null) => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const [user, setUser] = useState<AccountUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const session = await api<{ user: AccountUser | null }>('/api/accounts/session/', { signal })
      if (!signal?.aborted) {
        setUser(session.user)
        setError('')
      }
      return session.user
    } catch (failure) {
      if (!signal?.aborted) {
        setError('Could not connect to Subly. Check your connection and try again.')
      }
      throw failure
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  const logout = useCallback(async () => {
    await api('/api/accounts/logout/', { method: 'POST' })
    setUser(null)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    void refresh(controller.signal).catch(() => {})
    return () => controller.abort()
  }, [refresh])

  // The public landing page remains available while the API is offline.
  if (error && pathname !== '/') {
    return (
      <main className="mx-auto max-w-lg p-8 text-center">
        <p role="alert" className="mb-4 text-red-800">{error}</p>
        <button type="button" className="primary-link" disabled={loading} onClick={() => {
          setLoading(true)
          void refresh().catch(() => {})
        }}>{loading ? 'Connecting…' : 'Try again'}</button>
      </main>
    )
  }

  return <AuthContext.Provider value={{ user, loading, refresh, logout, setUser }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('Account screens require an AuthProvider.')
  return context
}
