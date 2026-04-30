import React from 'react'

const TimeHeatmapChart = ({ data }) => {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  const hours = Array.from({ length: 24 }, (_, i) => i)

  const heatmapData = Array.isArray(data)
    ? data
    : Array.from({ length: 7 }, () => Array.from({ length: 24 }, () => 0))

  const getIntensityColor = (value) => {
    if (value > 0.8) return 'bg-alert shadow-glow-alert z-10 scale-105 rounded-[2px]'
    if (value > 0.5) return 'bg-primary shadow-glow-primary opacity-80'
    if (value > 0.3) return 'bg-primary/40'
    return 'bg-surface-elevated/40'
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-between items-center px-2">
        <span className="text-[10px] text-text-muted font-bold uppercase tracking-widest">Fraud Intensity Matrix (7x24)</span>
        <div className="flex gap-4 items-center">
            <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 bg-surface-elevated rounded"></div><span className="text-[9px] text-text-muted font-bold uppercase">Low</span></div>
            <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 bg-alert rounded"></div><span className="text-[9px] text-text-muted font-bold uppercase">High</span></div>
        </div>
      </div>
      
      <div className="flex">
        {/* Y-axis labels */}
        <div className="flex flex-col gap-[2px] pr-3 pt-[20px]">
          {days.map(day => (
            <span key={day} className="text-[9px] text-text-muted font-bold h-[18px] flex items-center justify-end w-8 uppercase">{day}</span>
          ))}
        </div>
        
        <div className="flex-1 flex flex-col gap-[2px]">
          {/* X-axis labels */}
          <div className="flex gap-[2px] mb-1">
            {hours.map(hour => (
              <span key={hour} className="text-[8px] text-text-muted/60 font-bold w-full text-center">
                {hour % 4 === 0 ? hour : ''}
              </span>
            ))}
          </div>
          
          {heatmapData.map((dayData, dIdx) => (
            <div key={dIdx} className="flex gap-[2px] h-[18px]">
              {dayData.map((value, hIdx) => (
                <div 
                  key={hIdx}
                  className={`flex-1 transition-all duration-300 hover:ring-1 hover:ring-white border border-black/10 ${getIntensityColor(value)}`}
                  title={`Value: ${Math.round(value*100)}%`}
                />
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default TimeHeatmapChart
