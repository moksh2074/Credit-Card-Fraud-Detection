import React from 'react'
import RiskBadge from '../fraud/RiskBadge'
import FraudScoreBar from '../fraud/FraudScoreBar'
import { formatISTDateTime } from '../../utils/time'

const TransactionTable = ({ transactions, onRowClick }) => {
  return (
    <div className="fd-table-wrap">
      <table className="fd-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Time</th>
            <th>Amount</th>
            <th>Merchant</th>
            <th>Channel</th>
            <th>Device</th>
            <th>Risk</th>
            <th>Score</th>
          </tr>
        </thead>
        <tbody>
          {transactions?.map((tx) => {
            const id = tx.transaction_id || tx.id || 'N/A'
            const timestamp = tx.timestamp || tx.created_at || new Date().toISOString()
            const amount = tx.amount || 0
            const merchant = tx.merchant || tx.merchant_name || 'Unknown'
            const merchantCategory = tx.merchant_category || tx.mcc || 'General'
            const channel = tx.channel || 'N/A'
            const deviceId = tx.device_id || 'N/A'
            const riskLevel = tx.risk_level || 'LOW'
            const fraudScore = tx.fraud_score || 0

            const isFraud = fraudScore > 0.8 || riskLevel === 'CRITICAL' || riskLevel === 'HIGH'

            return (
              <tr
                key={id}
                onClick={() => onRowClick && onRowClick(tx)}
                className={`fd-table-row ${isFraud ? 'fd-row-fraud' : ''}`}
              >
                <td className="fd-table-id-cell">
                  {typeof id === 'string' ? id.slice(-8) : id}
                </td>
                <td className="fd-table-time-cell">
                  {formatISTDateTime(timestamp)}
                </td>
                <td className="fd-table-amount-cell">$ {amount.toLocaleString()}</td>
                <td>
                  <div className="fd-table-merchant-cell">
                    <span>{merchant}</span>
                    <small>{merchantCategory}</small>
                  </div>
                </td>
                <td className="fd-table-channel-cell">{channel}</td>
                <td className="fd-table-id-cell">
                  {typeof deviceId === 'string' ? deviceId.slice(-6) : deviceId}
                </td>
                <td>
                  <RiskBadge riskLevel={riskLevel} />
                </td>
                <td className="fd-table-score-cell">
                  <FraudScoreBar score={fraudScore} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default TransactionTable
