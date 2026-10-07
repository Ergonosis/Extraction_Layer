import { Navigate, useLocation } from 'react-router-dom'
import { DEV_UI_BYPASS_AUTH } from '../config/devAuth'
import { useAuth } from '../context/AuthContext'

type Props = {
  children: React.ReactNode
}

export function AuthGuard({ children }: Props) {
  const { status } = useAuth()
  const location = useLocation()

  // LOCAL ONLY — VITE_DEV_BYPASS_AUTH. Never enable in production builds.
  if (DEV_UI_BYPASS_AUTH && status === 'authenticated') {
    return <div className="app-frame-fill">{children}</div>
  }

  if (status === 'loading') {
    return (
      <div className="auth-loading" role="status" aria-live="polite">
        Checking session…
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <div className="app-frame-fill">{children}</div>
}
