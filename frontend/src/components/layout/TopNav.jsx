import React, { useEffect } from 'react'
import { Bell, User, LogOut } from 'lucide-react'
import { useLocation, Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../store/useAuthStore'
import { useAlertStore } from '../../store/useAlertStore'
import api from '../../services/api'

const TopNav = () => {
  const location = useLocation()
  const navigate = useNavigate()
  const logout = useAuthStore(state => state.logout)
  const openAlertCount = useAlertStore(state => state.openAlertCount)
  const setAlerts = useAlertStore(state => state.setAlerts)
  const user = useAuthStore(state => state.user)

  const getPageTitle = () => {
    const path = location.pathname.substring(1)
    if (!path) return 'Dashboard'
    return path.charAt(0).toUpperCase() + path.slice(1)
  }

  useEffect(() => {
    let mounted = true

    const fetchAlerts = async () => {
      try {
        const response = await api.get('/alerts')
        if (mounted && Array.isArray(response.data)) {
          setAlerts(response.data)
        }
      } catch (error) {
        console.error('Failed to fetch alerts for top nav:', error)
      }
    }

    fetchAlerts()
    const intervalId = window.setInterval(fetchAlerts, 30000)

    return () => {
      mounted = false
      window.clearInterval(intervalId)
    }
  }, [setAlerts])

  const handleLogout = async () => {
    try {
      await api.post('/auth/logout')
    } catch (error) {
      console.warn('Logout API failed, continuing local logout:', error)
    } finally {
      logout()
      navigate('/login', { replace: true })
    }
  }

  return (
    <header className="fd-topnav">
      <div className="fd-topnav-left">
        <h1 className="fd-topnav-title">{getPageTitle()}</h1>
        <div className="fd-topnav-breadcrumb">
          <Link to="/dashboard" className="fd-topnav-link">Platform</Link>
          <span>/</span>
          <span className="fd-topnav-current">{getPageTitle()}</span>
        </div>
      </div>

      <div className="fd-topnav-right">
        <div className="fd-topnav-alert">
          <button type="button" className="fd-btn-icon" onClick={() => navigate('/alerts')}>
            <Bell size={18} className="text-text-secondary" />
          </button>
          {openAlertCount > 0 && (
            <span className="fd-topnav-alert-badge">
              {openAlertCount > 9 ? '9+' : openAlertCount}
            </span>
          )}
        </div>

        <div className="fd-topnav-user-block">
          <div className="fd-topnav-user-meta">
            <span className="fd-topnav-user-name">{user?.name || 'Guest User'}</span>
            <span className="fd-topnav-user-role">{user?.role || 'operator'}</span>
          </div>

          <div className="fd-topnav-avatar" aria-hidden="true">
            {user?.avatar ? <img src={user.avatar} alt="Avatar" className="fd-topnav-avatar-img" /> : <User size={20} />}
          </div>
        </div>

        <button type="button" className="fd-topnav-signout-direct" onClick={handleLogout}>
          <LogOut size={15} />
          <span>Sign Out</span>
        </button>
      </div>
    </header>
  )
}

export default TopNav
