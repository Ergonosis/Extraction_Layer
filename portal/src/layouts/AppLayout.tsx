import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import './AppLayout.css'

export function AppLayout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const onSignOut = async () => {
    await logout()
    void navigate('/login', { replace: true })
  }

  return (
    <div className="app-layout">
      <aside className="app-sidebar" aria-label="Main">
        <div className="app-sidebar-top">
          <div className="app-sidebar-brand">Ergonosis Portal</div>
          <nav className="app-sidebar-nav">
            <NavLink
              to="/connections"
              className={({ isActive }) =>
                isActive ? 'app-nav-link app-nav-link-active' : 'app-nav-link'
              }
            >
              Connections
            </NavLink>
            <NavLink
              to="/file-upload"
              className={({ isActive }) =>
                isActive ? 'app-nav-link app-nav-link-active' : 'app-nav-link'
              }
            >
              File Upload
            </NavLink>
          </nav>
        </div>
        <div className="app-sidebar-footer">
          <p className="app-sidebar-user" title={user?.email}>
            {user?.display_name}
          </p>
          <p className="app-sidebar-org">{user?.organization.name}</p>
          <button type="button" className="app-sidebar-logout" onClick={() => void onSignOut()}>
            Sign out
          </button>
        </div>
      </aside>
      <div className="app-content">
        <Outlet />
      </div>
    </div>
  )
}
