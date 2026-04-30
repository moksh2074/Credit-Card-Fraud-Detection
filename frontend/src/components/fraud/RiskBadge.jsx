import React from 'react'
import Badge from '../ui/Badge'

const RiskBadge = ({ riskLevel }) => {
  // Mapping API risk levels to badge statuses
  const level = riskLevel?.toLowerCase() || 'low'
  
  const getStatus = () => {
    switch(level) {
      case 'critical':
      case 'fraud': return 'critical'
      case 'high': return 'high'
      case 'medium': return 'medium'
      case 'low': return 'low'
      case 'approved': return 'approved'
      default: return 'low'
    }
  }

  return <Badge status={getStatus()} />
}

export default RiskBadge
