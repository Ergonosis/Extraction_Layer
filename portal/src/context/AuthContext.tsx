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
  devLogin,
  fetchCurrentUser,
  fetchDevLoginStatus,
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

async function ensureDevSession(): Promise<AuthUser | null> {
  const enabled = await fetchDevLoginStatus()
  if (!enabled) return null
  try {
    await devLogin()
    return await fetchCurrentUser()
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [uiBypassActive, setUiBypassActive] = useState(false)

  const refresh = useCallback(async () => {
    try {
      let next = await fetchCurrentUser()

      // Prefer a real local session over UI-only mock so /api/integrations works.
      if (!next) {
        next = await ensureDevSession()
      }

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
      const recovered = await ensureDevSession()
      if (recovered) {
        setUser(recovered)
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
      // After logout, try to stay usable in local-dev mode.
      const recovered = await ensureDevSession()
      if (recovered) {
        setUser(recovered)
        setUiBypassActive(false)
        setStatus('authenticated')
        return
      }
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
