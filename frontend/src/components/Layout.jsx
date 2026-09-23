import { NavLink, useNavigate } from 'react-router-dom'
import { getUser, setToken, setUser } from '../api/client'

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: '▦' },
  { to: '/agents', label: 'Agents', icon: '◈' },
  { to: '/calls', label: 'Calls', icon: '◉' },
  { to: '/settings', label: 'Settings', icon: '⚙' },
]

export default function Layout({ children }) {
  const navigate = useNavigate()
  const user = getUser()

  const logout = () => {
    setToken(null)
    setUser(null)
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-orb" />
          <span className="brand-name">VoiceAgent</span>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="user-chip" title={user?.email || ''}>
            <div className="user-avatar">{(user?.email || 'U')[0].toUpperCase()}</div>
            <div className="user-meta">
              <div className="user-name">{user?.name || 'User'}</div>
              <div className="user-email">{user?.email || ''}</div>
            </div>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={logout}>
            Log out
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  )
}
