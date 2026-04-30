import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  CreditCard,
  Bell,
  BarChart3,
  ChevronLeft,
  ShieldAlert,
  Zap,
  Menu
} from 'lucide-react'
import { useAuthStore } from '../../store/useAuthStore'
import { useUIStore } from '../../store/useUIStore'

const Sidebar = () => {
  const collapsed = useUIStore(state => state.sidebarCollapsed)
  const setCollapsed = useUIStore(state => state.setSidebarCollapsed)
  const user = useAuthStore(state => state.user)
  const isAdmin = user?.role === 'admin'

  const navItems = [
    { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
    { name: 'Transactions', path: '/transactions', icon: CreditCard },
    { name: 'Alerts', path: '/alerts', icon: Bell },
    { name: 'Analytics', path: '/analytics', icon: BarChart3 },
    ...(isAdmin ? [{ name: 'Generator', path: '/generator', icon: Zap }] : []),
  ]

  return (
    <aside className={`fd-sidebar ${collapsed ? 'fd-sidebar-collapsed' : ''}`}>
      <div className="fd-sidebar-inner">
        <div className="fd-sidebar-brand">
          <div className="fd-sidebar-brand-mark">
            <ShieldAlert size={18} className="text-white" />
          </div>
          {!collapsed && (
            <div className="fd-sidebar-brand-copy">
              <span className="fd-sidebar-brand-name">FraudPlatform</span>
              <span className="fd-sidebar-brand-tag">Fraud Intelligence</span>
            </div>
          )}
        </div>

        <nav className="fd-sidebar-nav">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `fd-nav-item ${isActive ? 'fd-nav-item-active' : ''}`}
            >
              <item.icon size={18} className="fd-nav-icon" />
              {!collapsed && <span className="fd-nav-label">{item.name}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="fd-sidebar-footer">
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className="fd-sidebar-toggle"
          >
            {collapsed ? (
              <>
                <Menu size={17} />
                <span className="sr-only">Expand Sidebar</span>
              </>
            ) : (
              <>
                <ChevronLeft size={16} />
                <span>Collapse</span>
              </>
            )}
          </button>
        </div>
      </div>
    </aside>
  )
}

export default Sidebar
