import React from 'react'

const Card = ({ variant = 'default', children, className = '' }) => {
  const getVariantClass = () => {
    switch (variant) {
      case 'elevated': return 'fd-card-elevated'
      case 'alert': return 'fd-card-alert'
      case 'success': return 'fd-card-success'
      default: return 'fd-card'
    }
  }

  return (
    <div className={`${getVariantClass()} ${className}`}>
      {children}
    </div>
  )
}

export default Card
