import React from 'react'
import { X, ExternalLink, MapPin, Smartphone, CreditCard, ShoppingBag } from 'lucide-react'
import RiskBadge from './RiskBadge'
import FraudScoreBar from './FraudScoreBar'
import ShapPanel from './ShapPanel'
import Button from '../ui/Button'
import Card from '../ui/Card'
import { formatISTDateTime } from '../../utils/time'

const TransactionDetailDrawer = ({ transaction, onClose }) => {
  if (!transaction) return null

  const isFraud =
    transaction.predicted_class === 'FRAUD' ||
    transaction.processing_status === 'ALERTED' ||
    transaction.fraud_score > 0.8
  const statusLabel = String(transaction.processing_status || 'SCORED').replace('_', ' ')
  const locationText = `${transaction.geo_city || 'Unknown'}, ${transaction.geo_country || 'N/A'}`
  const latText = Number.isFinite(transaction.lat) ? transaction.lat : 'N/A'
  const lonText = Number.isFinite(transaction.lon) ? transaction.lon : 'N/A'

  return (
    <>
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[60] animate-in fade-in" onClick={onClose} />
      <aside className={`fixed top-0 right-0 h-full w-[480px] bg-surface-card border-l border-border shadow-card-lg z-[70] flex flex-col animate-in slide-in-from-right duration-300`}>
        {/* HEADER */}
        <div className="p-6 border-b border-border flex items-center justify-between">
          <div className="flex flex-col gap-1">
            <span className="text-[10px] text-text-muted uppercase font-bold tracking-widest">Transaction # {transaction.transaction_id.slice(-8)}</span>
            <div className="flex items-center gap-2">
               <h2 className="text-xl font-bold text-text-primary">$ {transaction.amount.toLocaleString()}</h2>
               <RiskBadge riskLevel={transaction.risk_level} />
            </div>
          </div>
          <button onClick={onClose} className="fd-btn-icon text-text-secondary hover:text-text-primary">
            <X size={20} />
          </button>
        </div>

        {/* CONTENT */}
        <div className="flex-1 overflow-y-auto p-6 flex flex-col gap-8">
          {/* OVERVIEW SECTION */}
          <div className="grid grid-cols-2 gap-4">
             <div className="fd-card p-3 flex flex-col gap-1">
                <span className="text-[9px] text-text-muted uppercase font-bold">Timestamp</span>
                <span className="text-xs font-mono">{formatISTDateTime(transaction.timestamp)}</span>
             </div>
             <div className="fd-card p-3 flex flex-col gap-1">
                <span className="text-[9px] text-text-muted uppercase font-bold">Status</span>
                <span className={`text-xs font-bold uppercase ${isFraud ? 'text-alert-light' : 'text-success-light'}`}>{statusLabel}</span>
             </div>
          </div>

          {/* FRAUD ANALYSIS */}
          <section className="flex flex-col gap-3">
             <h3 className="text-xs font-bold text-text-secondary uppercase tracking-widest pl-1">Fraud Analysis</h3>
             <Card variant={isFraud ? 'alert' : 'default'} className="p-5 flex flex-col gap-4">
                <div className="flex justify-between items-center">
                   <span className="text-sm font-semibold">Probability Score</span>
                   <span className="text-lg font-mono font-bold text-primary">{Math.round(transaction.fraud_score * 100)}%</span>
                </div>
                <FraudScoreBar score={transaction.fraud_score} />
                <div className="mt-4">
                   <ShapPanel shapValues={transaction.shap_values} />
                </div>
             </Card>
          </section>

          {/* ATTRIBUTES */}
          <section className="flex flex-col gap-6">
             <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-surface-elevated flex items-center justify-center text-text-secondary">
                   <ShoppingBag size={16} />
                </div>
                <div className="flex flex-col">
                   <span className="text-[10px] text-text-muted uppercase font-bold tracking-widest">Merchant</span>
                   <span className="text-sm font-semibold">{transaction.merchant} <span className="text-text-muted text-xs font-normal">({transaction.merchant_category})</span></span>
                </div>
             </div>

             <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-surface-elevated flex items-center justify-center text-text-secondary">
                   <Smartphone size={16} />
                </div>
                <div className="flex flex-col">
                   <span className="text-[10px] text-text-muted uppercase font-bold tracking-widest">Device Channel</span>
                   <span className="text-sm font-semibold uppercase">{transaction.channel} / {transaction.device_id.slice(-6)}</span>
                </div>
             </div>

             <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-surface-elevated flex items-center justify-center text-text-secondary">
                   <MapPin size={16} />
                </div>
                <div className="flex flex-col">
                   <span className="text-[10px] text-text-muted uppercase font-bold tracking-widest">Geolocation</span>
                   <span className="text-sm font-semibold">{locationText} <span className="text-text-muted text-xs font-normal">[{latText}, {lonText}]</span></span>
                </div>
             </div>

             <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-surface-elevated flex items-center justify-center text-text-secondary">
                   <CreditCard size={16} />
                </div>
                <div className="flex flex-col">
                   <span className="text-[10px] text-text-muted uppercase font-bold tracking-widest">Card ID</span>
                   <span className="text-sm font-mono font-bold">{transaction.card_id}</span>
                </div>
             </div>
          </section>

          {/* Wazuh RULES Placeholder */}
          <section className="flex flex-col gap-3">
             <h3 className="text-xs font-bold text-text-secondary uppercase tracking-widest pl-1">Triggered Security Rules</h3>
             <div className="flex flex-col gap-2">
                <div className="p-3 border border-alert/20 bg-alert-subtle rounded-lg flex items-center justify-between">
                   <span className="text-xs text-alert-light font-medium">Excessive amount for user profile</span>
                   <span className="text-[10px] font-mono text-alert opacity-70">R_1001</span>
                </div>
                <div className="p-3 border border-border bg-surface-elevated rounded-lg flex items-center justify-between opacity-60">
                   <span className="text-xs text-text-muted font-medium">New device fingerprint detected</span>
                   <span className="text-[10px] font-mono text-text-muted">R_1002</span>
                </div>
             </div>
          </section>
        </div>

        {/* FOOTER ACTIONS */}
        <div className="p-6 border-t border-border flex gap-3">
           <Button variant="danger" className="flex-1">Flag as Fraud</Button>
           <Button variant="secondary" className="flex-1">Release Hold</Button>
        </div>
      </aside>
    </>
  )
}

export default TransactionDetailDrawer
