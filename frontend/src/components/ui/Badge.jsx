import React from 'react'

const Badge = ({ status = 'low' }) => {
  const getBadgeClass = () => {
    switch (status.toLowerCase()) {
      case 'critical': return 'fd-badge-critical'
      case 'high': return 'fd-badge-high'
      case 'medium': return 'fd-badge-medium'
      case 'low': return 'fd-badge-low'
      case 'fraud': return 'fd-badge-fraud'
      case 'approved': return 'fd-badge-approved'
      case 'p0': return 'fd-badge-p0'
      case 'p1': return 'fd-badge-p1'
      case 'p2': return 'fd-badge-p2'
      case 'p3': return 'fd-badge-p3'
      default: return 'fd-badge-low'
    }
  }

  return (
    <span className={`fd-badge ${getBadgeClass()}`}>
      {status}
    </span>
  )
}

export default Badge
