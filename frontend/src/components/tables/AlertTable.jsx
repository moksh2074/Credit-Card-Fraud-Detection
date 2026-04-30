import React from 'react'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import { MoreVertical, ExternalLink } from 'lucide-react'
import { formatISTShort } from '../../utils/time'

const getStatusClass = (status) => {
  const value = String(status || '').toLowerCase()
  if (value === 'new' || value === 'open') return 'fd-alert-status-open'
  if (value === 'acknowledged' || value === 'investigating') return 'fd-alert-status-investigating'
  if (value === 'resolved') return 'fd-alert-status-resolved'
  if (value === 'false_positive' || value === 'false positive') return 'fd-alert-status-false-positive'
  return 'fd-alert-status-investigating'
}

const AlertTable = ({ alerts, onSelectAlert, selectedAlertId }) => {
  return (
    <div className="fd-table-wrap">
      <table className="fd-table fd-alert-table">
        <thead>
          <tr>
            <th>Severity</th>
            <th>Card ID</th>
            <th>Time</th>
            <th>Description</th>
            <th>Assignee</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => {
            const isSelected = selectedAlertId === alert.id
            return (
              <tr
                key={alert.id}
                className={`fd-alert-row ${isSelected ? 'fd-alert-row-selected' : ''}`}
                onClick={() => onSelectAlert(alert)}
              >
                <td>
                  <Badge status={alert.severity} />
                </td>
                <td className="fd-table-id-cell">{alert.card_id}</td>
                <td className="fd-table-time-cell">{formatISTShort(alert.timestamp)}</td>
                <td className="fd-alert-desc-cell">{alert.description}</td>
                <td>
                  <div className="fd-alert-assignee">
                    <div>{alert.assignee ? String(alert.assignee).charAt(0).toUpperCase() : 'U'}</div>
                    <span>{alert.assignee || 'Unassigned'}</span>
                  </div>
                </td>
                <td>
                  <span className={`fd-alert-status ${getStatusClass(alert.status)}`}>
                    {String(alert.status || '').replace('_', ' ')}
                  </span>
                </td>
                <td>
                  <div className="fd-alert-action-icons" onClick={(e) => e.stopPropagation()}>
                    <Button variant="icon" className="w-8 h-8" onClick={() => onSelectAlert(alert)}>
                      <ExternalLink size={14} />
                    </Button>
                    <Button variant="icon" className="w-8 h-8">
                      <MoreVertical size={14} />
                    </Button>
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default AlertTable
