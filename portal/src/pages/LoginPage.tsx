import { useEffect, useState } from 'react'
import { Navigate } from 'react-router-dom'
import {
  devLogin,
  fetchDevLoginStatus,
  startMicrosoftLogin,
} from '../api/auth'
import { DEV_UI_BYPASS_AUTH } from '../config/devAuth'
import { useAuth } from '../context/AuthContext'
import './LoginPage.css'

function MicrosoftLogo() {
  return (
    <svg
      className="login-ms-logo"
      width="21"
      height="21"
      viewBox="0 0 21 21"
      aria-hidden="true"
    >
      <rect x="1" y="1" width="9" height="9" fill="#f25022" />
      <rect x="11" y="1" width="9" height="9" fill="#7fba00" />
      <rect x="1" y="11" width="9" height="9" fill="#00a4ef" />
      <rect x="11" y="11" width="9" height="9" fill="#ffb900" />
    </svg>
  )
}

function ShieldLockIcon() {
  return (
    <svg
      className="login-shield"
      width="72"
      height="72"
      viewBox="0 0 72 72"
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M36 8L14 18v16c0 14.5 9.6 28 22 31.5C48.4 62 58 48.5 58 34V18L36 8z"
        stroke="#9aa3af"
        strokeWidth="2.5"
        strokeLinejoin="round"
      />
      <rect
        x="28"
        y="32"
        width="16"
        height="14"
        rx="2.5"
        stroke="#9aa3af"
        strokeWidth="2.5"
      />
      <path
        d="M32 32v-4a4 4 0 0 1 8 0v4"
        stroke="#9aa3af"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function LoginPage() {
  const { status, refresh } = useAuth()
  const [apiDevLogin, setApiDevLogin] = useState(false)
  const [devBusy, setDevBusy] = useState(false)
  const [devError, setDevError] = useState<string | null>(null)

  useEffect(() => {
    void fetchDevLoginStatus().then(setApiDevLogin)
  }, [])

  if (status === 'loading') {
    return (
      <div className="login-page">
        <p className="auth-loading">Checking session…</p>
      </div>
    )
  }

  if (status === 'authenticated') {
    return <Navigate to="/connections" replace />
  }

  const onDevLogin = async () => {
    setDevBusy(true)
    setDevError(null)
    try {
      await devLogin()
      await refresh()
    } catch {
      setDevError('Dev login failed. Is Flask running with ENABLE_DEV_LOGIN=true?')
    } finally {
      setDevBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1 className="login-title">Ergonosis Portal</h1>
        <ShieldLockIcon />
        <p className="login-subtitle">Manage your external integrations</p>
        <button
          type="button"
          className="login-ms-button"
          onClick={() => startMicrosoftLogin('/connections')}
        >
          <MicrosoftLogo />
          <span>Sign in with Microsoft</span>
        </button>
        <p className="login-footer">Sign in with your organization account</p>

        {(apiDevLogin || DEV_UI_BYPASS_AUTH) && (
          <div className="login-dev-panel">
            <p className="login-dev-warning">
              LOCAL ONLY — disable before production
            </p>
            {apiDevLogin && (
              <button
                type="button"
                className="login-dev-button"
                disabled={devBusy}
                onClick={() => void onDevLogin()}
              >
                {devBusy ? 'Signing in…' : 'Continue as local dev user'}
              </button>
            )}
            {DEV_UI_BYPASS_AUTH && !apiDevLogin && (
              <p className="login-dev-hint">
                UI bypass is on (`VITE_DEV_BYPASS_AUTH`). Open /connections for a
                mock shell; enable `ENABLE_DEV_LOGIN` for real API data.
              </p>
            )}
            {devError && <p className="login-dev-error">{devError}</p>}
          </div>
        )}
      </div>
    </div>
  )
}
