import React from 'react'
import { Loader2 } from 'lucide-react'

const Button = ({ variant = 'primary', children, onClick, disabled, loading, type = 'button', className = '' }) => {
  const getVariantClass = () => {
    switch (variant) {
      case 'secondary': return 'fd-btn-secondary'
      case 'danger': return 'fd-btn-danger'
      case 'icon': return 'fd-btn-icon'
      default: return 'fd-btn-primary'
    }
  }

  return (
    <button
      type={type}
      className={`${getVariantClass()} ${className} flex items-center justify-center gap-2`}
      onClick={onClick}
      disabled={disabled || loading}
    >
      {loading && <Loader2 className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  )
}

export default Button
