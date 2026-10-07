import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  fetchCurrentUser,
  logout as logoutRequest,
  type AuthUser,
} from '../api/auth'
import { DEV_MOCK_USER, DEV_UI_BYPASS_AUTH } from '../config/devAuth'

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated'

type AuthContextValue = {
  status: AuthStatus
  user: AuthUser | null
  /** True when VITE_DEV_BYPASS_AUTH is providing a mock user (no real session). */
  uiBypassActive: boolean
  refresh: () => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [uiBypassActive, setUiBypassActive] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const next = await fetchCurrentUser()
      if (next) {
        setUser(next)
        setUiBypassActive(false)
        setStatus('authenticated')
        return
      }
      if (DEV_UI_BYPASS_AUTH) {
        setUser({ ...DEV_MOCK_USER })
        setUiBypassActive(true)
        setStatus('authenticated')
        return
      }
      setUser(null)
      setUiBypassActive(false)
      setStatus('unauthenticated')
    } catch {
      if (DEV_UI_BYPASS_AUTH) {
        setUser({ ...DEV_MOCK_USER })
        setUiBypassActive(true)
        setStatus('authenticated')
        return
      }
      setUser(null)
      setUiBypassActive(false)
      setStatus('unauthenticated')
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const logout = useCallback(async () => {
    try {
      if (!uiBypassActive) {
        await logoutRequest()
      }
    } finally {
      if (DEV_UI_BYPASS_AUTH) {
        setUser({ ...DEV_MOCK_USER })
        setUiBypassActive(true)
        setStatus('authenticated')
      } else {
        setUser(null)
        setUiBypassActive(false)
        setStatus('unauthenticated')
      }
    }
  }, [uiBypassActive])

  const value = useMemo(
    () => ({ status, user, uiBypassActive, refresh, logout }),
    [status, user, uiBypassActive, refresh, logout],
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
