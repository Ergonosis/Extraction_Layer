import { Navigate } from 'react-router-dom'
import { startMicrosoftLogin } from '../api/auth'
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
  const { status } = useAuth()

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
      </div>
    </div>
  )
}
