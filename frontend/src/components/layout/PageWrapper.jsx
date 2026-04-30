import React from 'react'
import Sidebar from './Sidebar'
import TopNav from './TopNav'
import { useUIStore } from '../../store/useUIStore'

const PageWrapper = ({ children }) => {
  const collapsed = useUIStore(state => state.sidebarCollapsed)

  return (
    <div className={`fd-app-shell ${collapsed ? 'fd-app-shell-collapsed' : ''}`}>
      <Sidebar />
      <div className="fd-shell-main">
        <TopNav />
        <main className="fd-main-content fd-fade-up">
          <div className="fd-content-container">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}

export default PageWrapper
