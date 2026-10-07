import { useEffect, useState } from 'react'
import { api } from '../api/client'
import './DevAuthBanner.css'

/**
 * Loud warning when local SSO bypass is active.
 * Must never appear in a correctly configured production deploy.
 */
export function DevAuthBanner() {
  const [apiDevLogin, setApiDevLogin] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const { data } = await api.get<{ dev_login_enabled?: boolean }>('/api/health')
        if (!cancelled) setApiDevLogin(Boolean(data.dev_login_enabled))
      } catch {
        if (!cancelled) setApiDevLogin(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  if (!apiDevLogin) return null

  return (
    <div className="dev-auth-banner" role="alert">
      <strong>DEV AUTH BYPASS ON</strong>
      <span>
        {' '}
        (ENABLE_DEV_LOGIN) — local only. Turn this off before production.
      </span>
    </div>
  )
}
