import { useAuth } from '../context/AuthContext'
import './ConnectionsPage.css'

/**
 * Authenticated landing shell after SSO.
 * Full connections dashboard UI is issue #23.
 */
export function ConnectionsPage() {
  const { user, logout } = useAuth()

  return (
    <div className="app-shell">
      <header className="app-shell-header">
        <div>
          <p className="app-shell-brand">Ergonosis Portal</p>
          <h1>Connections</h1>
        </div>
        <button type="button" className="app-shell-logout" onClick={() => void logout()}>
          Sign out
        </button>
      </header>
      <main className="app-shell-main">
        <p>
          Signed in as <strong>{user?.display_name}</strong> ({user?.email})
        </p>
        <p className="app-shell-muted">
          Organization: {user?.organization.name} · Integration cards arrive in a later
          issue.
        </p>
      </main>
    </div>
  )
}
