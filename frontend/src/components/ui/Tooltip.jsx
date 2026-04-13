import React, { useState } from 'react'

const Tooltip = ({ children, content }) => {
  const [show, setShow] = useState(false)

  return (
    <div className="relative inline-block" 
         onMouseEnter={() => setShow(true)} 
         onMouseLeave={() => setShow(false)}>
      {children}
      {show && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 fd-card text-xs whitespace-nowrap z-50 animate-in fade-in slide-in-from-bottom-1 p-2">
          {content}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-t-surface-card" />
        </div>
      )}
    </div>
  )
}

export default Tooltip
