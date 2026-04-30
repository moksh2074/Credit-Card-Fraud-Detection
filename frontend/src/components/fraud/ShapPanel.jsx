import React from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
} from 'recharts'

const ShapPanel = ({ shapValues }) => {
  // shapValues: array of { feature, value }
  const data = Array.isArray(shapValues) 
    ? shapValues.sort((a, b) => Math.abs(b.value) - Math.abs(a.value)).slice(0, 5)
    : [
      { feature: 'Amount', value: 0.25 },
      { feature: 'Merchant_Risk', value: 0.15 },
      { feature: 'Card_Freq', value: -0.1 },
      { feature: 'Geo_Dist', value: 0.12 },
      { feature: 'Device_Hist', value: 0.08 }
    ] // Placeholder if data missing

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-sm font-bold text-text-secondary uppercase tracking-widest">Model Contributions (SHAP)</h3>
      <div className="h-[220px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} stroke="#1E293B" />
            <XAxis type="number" hide />
            <YAxis 
              dataKey="feature" 
              type="category" 
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: '#94A3B8', fontSize: 11, fontWeight: 500 }}
              width={100}
            />
            <Tooltip
              contentStyle={{ background: '#111827', border: '1px solid #1E293B', borderRadius: '8px' }}
              itemStyle={{ color: '#F1F5F9', fontSize: 12 }}
              cursor={{ fill: 'rgba(255,255,255,0.05)' }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={12}>
              {data.map((entry, index) => (
                <Cell 
                  key={`cell-${index}`} 
                  fill={entry.value > 0 ? '#EF4444' : '#10B981'} 
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[10px] text-text-muted italic px-2">
        Red bars indicate features increasing fraud probability, green bars indicate features decreasing it.
      </p>
    </div>
  )
}

export default ShapPanel
