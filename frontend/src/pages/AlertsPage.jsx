import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import AlertTable from '../components/tables/AlertTable'
import ShapPanel from '../components/fraud/ShapPanel'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import { MapPin, ShieldAlert, CheckCircle, XCircle, UserPlus, Info, Filter } from 'lucide-react'
import api from '../services/api'
import { useAlertStore } from '../store/useAlertStore'
import { useSSE } from '../hooks/useSSE'
import { formatISTDateTime } from '../utils/time'

const buildAlertDescription = (alert) => {
  if (alert.description) return alert.description

  const triggers = alert.rule_triggers || {}
  const triggerEntries = Object.entries(triggers)
  if (triggerEntries.length > 0) {
    return triggerEntries.map(([key, value]) => `${key}: ${value}`).join(' | ')
  }

  return `Fraud alert on card ${alert.card_id_hash}`
}

const mapAlert = (alert) => ({
  ...alert,
  card_id: alert.card_id_hash,
  timestamp: alert.created_at,
  description: buildAlertDescription(alert),
  assignee: alert.assignee_id || null,
})

const AlertsPage = () => {
  const [alerts, setAlerts] = useState([])
  const [selectedAlertId, setSelectedAlertId] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [error, setError] = useState('')

  const liveRefreshRef = useRef(0)
  const lastTxEvent = useSSE('/api/v1/stream/transactions')

  const setAlertStore = useAlertStore(state => state.setAlerts)
  const selectedAlert = alerts.find(a => a.id === selectedAlertId) || alerts[0] || null

  const unresolvedCount = useMemo(
    () => alerts.filter((a) => !['RESOLVED', 'FALSE_POSITIVE'].includes(String(a.status))).length,
    [alerts]
  )

  const fetchAlerts = useCallback(async ({ silent = false } = {}) => {
    if (!silent) {
      setLoading(true)
      setError('')
    }

    try {
      const params = { synthetic_only: true }
      if (statusFilter) params.status = statusFilter
      if (severityFilter) params.severity = severityFilter

      const response = await api.get('/alerts', { params })
      const rows = Array.isArray(response.data) ? response.data.map(mapAlert) : []
      setAlerts(rows)
      setAlertStore(rows)

      if (rows.length > 0) {
        setSelectedAlertId((current) => current && rows.some(a => a.id === current) ? current : rows[0].id)
      } else {
        setSelectedAlertId(null)
      }
    } catch (err) {
      console.error('Failed to fetch alerts:', err)
      setError('Failed to load alerts from backend.')
      setAlerts([])
      setSelectedAlertId(null)
    } finally {
      if (!silent) setLoading(false)
    }
  }, [severityFilter, setAlertStore, statusFilter])

  useEffect(() => {
    fetchAlerts()
    const intervalId = window.setInterval(() => {
      fetchAlerts({ silent: true })
    }, 5000)

    return () => window.clearInterval(intervalId)
  }, [fetchAlerts])

  useEffect(() => {
    if (!lastTxEvent || lastTxEvent.status === 'keep-alive') return

    const eventType = String(lastTxEvent.event_type || '').toLowerCase()
    const shouldRefresh =
      eventType === 'alert_updated' ||
      Boolean(lastTxEvent.alert_generated) ||
      ['HIGH', 'CRITICAL'].includes(String(lastTxEvent.risk_level || '').toUpperCase())

    if (!shouldRefresh) return

    const now = Date.now()
    if (now - liveRefreshRef.current < 1200) return
    liveRefreshRef.current = now

    fetchAlerts({ silent: true })
  }, [fetchAlerts, lastTxEvent])

  const updateAlertStatus = async (status, outcome = null) => {
    if (!selectedAlert) return

    setActionLoading(true)
    setError('')
    try {
      await api.patch(`/alerts/${selectedAlert.id}/status`, { status, outcome })
      await fetchAlerts()
    } catch (err) {
      console.error('Failed to update alert:', err)
      setError('Failed to update alert status.')
    } finally {
      setActionLoading(false)
    }
  }

  const handleBulkAction = async () => {
    const newAlerts = alerts.filter((a) => String(a.status).toUpperCase() === 'NEW')
    if (newAlerts.length === 0) return

    setActionLoading(true)
    setError('')
    try {
      await Promise.all(newAlerts.map((alert) => api.patch(`/alerts/${alert.id}/status`, { status: 'ACKNOWLEDGED' })))
      await fetchAlerts()
    } catch (err) {
      console.error('Bulk action failed:', err)
      setError('Bulk action failed.')
    } finally {
      setActionLoading(false)
    }
  }

  const shapEvidence = useMemo(() => {
    if (!selectedAlert?.rule_triggers || Object.keys(selectedAlert.rule_triggers).length === 0) {
      return [
        { feature: 'Velocity', value: 0.45 },
        { feature: 'Amount', value: 0.35 },
        { feature: 'Merchant_Hist', value: 0.12 },
        { feature: 'Device_Fingerprint', value: -0.10 },
      ]
    }

    return Object.entries(selectedAlert.rule_triggers).map(([feature, value]) => ({
      feature,
      value: Number(value) || 0,
    }))
  }, [selectedAlert])

  return (
    <PageWrapper>
      <div className="fd-alerts-layout">
        <section className="fd-alerts-list-panel">
          <div className="fd-alerts-toolbar">
            <div className="fd-alerts-heading">
              <h2>Fraud Alerts</h2>
              <span className="fd-badge fd-badge-critical">{unresolvedCount} Unresolved</span>
            </div>
            <Button variant="secondary" className="fd-tab-btn-small" onClick={handleBulkAction} disabled={actionLoading || alerts.length === 0}>
              Bulk Action
            </Button>
          </div>

          <div className="fd-filter-panel">
            <div className="fd-filter-item">
              <label htmlFor="fd-alert-status-filter">Status</label>
              <select id="fd-alert-status-filter" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">All</option>
                <option value="NEW">New</option>
                <option value="ACKNOWLEDGED">Acknowledged</option>
                <option value="RESOLVED">Resolved</option>
                <option value="FALSE_POSITIVE">False Positive</option>
              </select>
            </div>

            <div className="fd-filter-item">
              <label htmlFor="fd-alert-severity-filter">Severity</label>
              <select id="fd-alert-severity-filter" value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)}>
                <option value="">All</option>
                <option value="P0">P0</option>
                <option value="P1">P1</option>
                <option value="P2">P2</option>
                <option value="P3">P3</option>
              </select>
            </div>

            <Button variant="secondary" className="fd-tab-btn-small" onClick={() => { setStatusFilter(''); setSeverityFilter('') }}>
              <Filter size={13} />
              Clear
            </Button>
          </div>

          {error ? <div className="fd-page-error">{error}</div> : null}

          <Card className="fd-table-card-shell">
            {loading ? (
              <div className="fd-page-loading">Loading alerts...</div>
            ) : (
              <AlertTable
                alerts={alerts}
                selectedAlertId={selectedAlertId}
                onSelectAlert={(item) => setSelectedAlertId(item.id)}
              />
            )}
          </Card>
        </section>

        <section className="fd-alerts-detail-panel">
          <h3 className="fd-alerts-detail-label">Alert Investigation</h3>

          <Card variant="elevated" className="fd-alerts-detail-card">
            {selectedAlert ? (
              <>
                <div className="fd-alerts-detail-head">
                  <div>
                    <div className="fd-alert-meta-row">
                      <span>ID: {selectedAlert.id.slice(0, 8)}</span>
                      <Badge status={selectedAlert.severity} />
                    </div>
                    <h4>{selectedAlert.description}</h4>
                  </div>
                </div>

                <div className="fd-alert-map-box">
                  <div className="fd-alert-map-overlay" />
                  <div className="fd-alert-map-center">
                    <MapPin size={30} className="text-alert" />
                    <span>Card: {selectedAlert.card_id}</span>
                  </div>
                  <div className="fd-alert-map-info-btn">
                    <Button variant="icon" className="w-8 h-8 rounded-full">
                      <Info size={14} />
                    </Button>
                  </div>
                </div>

                <div className="fd-alert-model-card">
                  <div className="fd-alert-model-head">
                    <ShieldAlert size={16} className="text-primary" />
                    <span>Model Evidence</span>
                  </div>
                  <ShapPanel shapValues={shapEvidence} />
                </div>

                <div className="fd-alert-action-stack">
                  <div className="fd-alert-action-row">
                    <Button variant="secondary" className="fd-alert-action-btn" onClick={() => updateAlertStatus('ACKNOWLEDGED')} disabled={actionLoading}>
                      <UserPlus size={16} />
                      Assign Me
                    </Button>
                    <Button variant="danger" className="fd-alert-action-btn" onClick={() => updateAlertStatus('RESOLVED', 'CONFIRMED_FRAUD')} disabled={actionLoading}>
                      <CheckCircle size={16} />
                      Confirm Fraud
                    </Button>
                  </div>
                  <Button variant="secondary" className="fd-alert-action-btn fd-alert-false-positive-btn" onClick={() => updateAlertStatus('FALSE_POSITIVE', 'FALSE_POSITIVE')} disabled={actionLoading}>
                    <XCircle size={16} />
                    False Positive
                  </Button>
                </div>

                <div className="fd-alert-audit">
                  <div className="fd-alert-audit-head">
                    <span>Audit Trail</span>
                    <button type="button" onClick={() => setStatusFilter('')}>View All</button>
                  </div>

                  <div className="fd-alert-audit-item">
                    <div className="fd-alert-audit-dot" />
                    <div>
                      <p><strong>System</strong> created alert</p>
                      <small>{formatISTDateTime(selectedAlert.created_at)}</small>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div className="fd-page-loading">No alerts available.</div>
            )}
          </Card>
        </section>
      </div>
    </PageWrapper>
  )
}

export default AlertsPage
