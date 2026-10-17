import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  devLogin,
  fetchCurrentUser,
  fetchDevLoginStatus,
  logout as logoutRequest,
  type AuthUser,
} from '../api/auth'

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

type AuthContextValue = {
  status: AuthStatus
  user: AuthUser | null
  refresh: () => Promise<void>
  logout: () => Promise<void>
  /** Explicit local API login (ENABLE_DEV_LOGIN). */
  loginAsDev: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

async function ensureDevSession(): Promise<AuthUser | null> {
  const enabled = await fetchDevLoginStatus()
  if (!enabled) return null
  try {
    const user = await devLogin()
    // Prefer the payload from login; fall back to /me if needed.
    return user ?? (await fetchCurrentUser())
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)
  // After Sign out, do not immediately re-create a local session.
  const suppressAutoDevLoginRef = useRef(false)

  const refresh = useCallback(async () => {
    try {
      let next = await fetchCurrentUser()

      if (!next && !suppressAutoDevLoginRef.current) {
        next = await ensureDevSession()
      }

      if (next) {
        setUser(next)
        setStatus('authenticated')
        return
      }

      setUser(null)
      setStatus('unauthenticated')
    } catch {
      if (!suppressAutoDevLoginRef.current) {
        const recovered = await ensureDevSession()
        if (recovered) {
          setUser(recovered)
          setStatus('authenticated')
          return
        }
      }
      setUser(null)
      setStatus('unauthenticated')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const logout = useCallback(async () => {
    suppressAutoDevLoginRef.current = true
    try {
      await logoutRequest()
    } catch {
      // Already logged out — still clear local auth state.
    } finally {
      setUser(null)
      setStatus('unauthenticated')
    }
  }, [])

  const loginAsDev = useCallback(async () => {
    suppressAutoDevLoginRef.current = false
    const next = await ensureDevSession()
    if (!next) {
      throw new Error('Dev login failed')
    }
    setUser(next)
    setStatus('authenticated')
  }, [])

  const value = useMemo(
    () => ({
      status,
      user,
      refresh,
      logout,
      loginAsDev,
    }),
    [status, user, refresh, logout, loginAsDev],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
