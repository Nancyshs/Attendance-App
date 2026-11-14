import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, authEvents, STAFF_KEY } from './api'
import type { User } from './types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<User>
  logout: () => void
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState<boolean>(() => !!localStorage.getItem(STAFF_KEY))

  const logout = useCallback(() => {
    localStorage.removeItem(STAFF_KEY)
    setUser(null)
  }, [])

  useEffect(() => {
    if (!localStorage.getItem(STAFF_KEY)) return
    api
      .get<User>('/auth/me')
      .then(setUser)
      .catch(() => localStorage.removeItem(STAFF_KEY))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const onUnauthorized = (e: Event) => {
      if ((e as CustomEvent).detail === 'staff') logout()
    }
    authEvents.addEventListener('unauthorized', onUnauthorized)
    return () => authEvents.removeEventListener('unauthorized', onUnauthorized)
  }, [logout])

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>('/auth/login', { username, password }, 'none')
    localStorage.setItem(STAFF_KEY, res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthState {
  const v = useContext(Ctx)
  if (!v) throw new Error('AuthProvider missing')
  return v
}
