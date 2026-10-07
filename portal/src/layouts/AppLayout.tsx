import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import './AppLayout.css'

export function AppLayout() {
  const { user, logout } = useAuth()

  return (
    <div className="app-layout">
      <aside className="app-sidebar" aria-label="Main">
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
        <div className="app-sidebar-footer">
          <p className="app-sidebar-user" title={user?.email}>
            {user?.display_name}
          </p>
          <p className="app-sidebar-org">{user?.organization.name}</p>
          <button type="button" className="app-sidebar-logout" onClick={() => void logout()}>
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
