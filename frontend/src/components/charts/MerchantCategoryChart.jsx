import React from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from 'recharts'

const CustomTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    return (
      <div className="fd-card p-2.5 border-border bg-surface-elevated/90 backdrop-blur-md">
        <p className="text-[10px] text-text-muted font-bold uppercase tracking-wider mb-1">{payload[0].payload.category}</p>
        <p className="text-sm font-bold text-primary">
          {payload[0].value}% Fraud Rate
        </p>
      </div>
    )
  }
  return null
}

const MerchantCategoryChart = ({ data }) => {
  const chartData = (Array.isArray(data) ? data : []).sort((a, b) => b.rate - a.rate)

  return (
    <div className="h-full w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          layout="vertical"
          data={chartData}
          margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
        >
          <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#1E293B" />
          <XAxis type="number" hide />
          <YAxis 
            dataKey="category" 
            type="category" 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: '#94A3B8', fontSize: 11, fontWeight: 500 }}
            width={100}
          />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.05)' }}
            content={<CustomTooltip />}
          />
          <Bar dataKey="rate" fill="#6366F1" radius={[0, 4, 4, 0]} barSize={16} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export default MerchantCategoryChart
