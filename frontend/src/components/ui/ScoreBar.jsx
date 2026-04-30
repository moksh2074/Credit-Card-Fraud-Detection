import React from 'react'

const ScoreBar = ({ score, label }) => {
  // score expected 0-1
  const percentage = Math.round(score * 100)
  
  const getColor = () => {
    if (score >= 0.85) return '#EF4444' // Red
    if (score >= 0.65) return '#F97316' // Orange
    if (score >= 0.35) return '#F59E0B' // Amber
    return '#10B981' // Green
  }

  return (
    <div className="flex items-center gap-3 w-full">
      <div className="flex-1 fd-score-bar-track">
        <div 
          className="fd-score-bar-fill" 
          style={{ width: `${percentage}%`, backgroundColor: getColor() }} 
        />
      </div>
      {label && <span className="text-xs font-mono font-bold w-12 text-right">{percentage}%</span>}
    </div>
  )
}

export default ScoreBar
