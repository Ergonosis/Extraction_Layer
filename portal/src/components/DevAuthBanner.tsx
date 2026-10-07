import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { DEV_UI_BYPASS_AUTH } from '../config/devAuth'
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

  if (!DEV_UI_BYPASS_AUTH && !apiDevLogin) return null

  const parts: string[] = []
  if (DEV_UI_BYPASS_AUTH) parts.push('VITE_DEV_BYPASS_AUTH')
  if (apiDevLogin) parts.push('ENABLE_DEV_LOGIN')

  return (
    <div className="dev-auth-banner" role="alert">
      <strong>DEV AUTH BYPASS ON</strong>
      <span>
        {' '}
        ({parts.join(' + ')}) — local only. Turn these off before production.
      </span>
    </div>
  )
}
