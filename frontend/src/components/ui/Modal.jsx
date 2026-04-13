import React from 'react'
import { X } from 'lucide-react'

const Modal = ({ isOpen, onClose, title, children, width = 'max-w-md' }) => {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-surface-base/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className={`fd-card-elevated w-full ${width} relative animate-in zoom-in-95 duration-200`}>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-text-primary">{title}</h2>
          <button onClick={onClose} className="fd-btn-icon text-text-secondary hover:text-text-primary">
            <X size={20} />
          </button>
        </div>
        <div>
          {children}
        </div>
      </div>
    </div>
  )
}

export default Modal
