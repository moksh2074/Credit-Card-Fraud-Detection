import React from 'react'

const Input = ({ label, type = 'text', placeholder, value, onChange, error, className = '' }) => {
  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      {label && <label className="text-xs font-semibold text-text-secondary uppercase tracking-wider">{label}</label>}
      <input
        type={type}
        className={`fd-input ${error ? 'error' : ''}`}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
      />
      {error && <span className="text-xs text-alert-light mt-0.5">{error}</span>}
    </div>
  )
}

export default Input
