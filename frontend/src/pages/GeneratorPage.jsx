import React, { useEffect, useRef, useState } from 'react'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import { Play, Square, Settings, RefreshCw, Layers, Save } from 'lucide-react'
import api from '../services/api'
import { useSSE } from '../hooks/useSSE'
import { formatISTDateTime } from '../utils/time'

const appendLog = (setLogs, message) => {
  const timestamp = formatISTDateTime(new Date())
  setLogs((prev) => [`[${timestamp}] ${message}`, ...prev].slice(0, 300))
}

const GeneratorPage = () => {
  const [isRunning, setIsRunning] = useState(false)
  const [tps, setTps] = useState(5)
  const [fraudRate, setFraudRate] = useState(0.05)
  const [configDirty, setConfigDirty] = useState(false)
  const [activeScenarios, setActiveScenarios] = useState([])
  const [actionLoading, setActionLoading] = useState(false)
  const [statusLoading, setStatusLoading] = useState(false)
  const [error, setError] = useState('')
  const [logs, setLogs] = useState([])

  const configDirtyRef = useRef(false)
  const lastTxEvent = useSSE('/api/v1/stream/transactions')

  useEffect(() => {
    configDirtyRef.current = configDirty
  }, [configDirty])

  const fetchStatus = async ({ silent = false } = {}) => {
    if (!silent) setStatusLoading(true)

    try {
      const response = await api.get('/generator/status')
      const data = response.data
      const serverTps = Number(data.current_tps ?? 1)
      const serverFraudRate = Number(data.fraud_rate ?? 0.05)

      setIsRunning(Boolean(data.is_running))
      setActiveScenarios(Array.isArray(data.active_scenarios) ? data.active_scenarios : [])

      // Do not override slider values while user is adjusting unsaved config.
      if (!configDirtyRef.current) {
        setTps(serverTps)
        setFraudRate(serverFraudRate)
      }
    } catch (err) {
      console.error('Failed to fetch generator status:', err)
      setError('Failed to fetch generator status.')
    } finally {
      if (!silent) setStatusLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    const intervalId = window.setInterval(() => {
      fetchStatus({ silent: true })
    }, 4000)

    return () => window.clearInterval(intervalId)
  }, [])

  useEffect(() => {
    if (!lastTxEvent || lastTxEvent.status === 'keep-alive' || !isRunning) return
    if (lastTxEvent.event_type && lastTxEvent.event_type !== 'transaction_ingested') return

    const txId = lastTxEvent.transaction_id ? String(lastTxEvent.transaction_id).slice(0, 8) : 'N/A'
    const score = typeof lastTxEvent.fraud_score === 'number' ? lastTxEvent.fraud_score.toFixed(3) : 'N/A'
    const risk = lastTxEvent.risk_level || 'UNKNOWN'
    appendLog(setLogs, `[SIM] TX ${txId} scored=${score} risk=${risk}`)
  }, [lastTxEvent, isRunning])

  const handleToggleGenerator = async () => {
    setActionLoading(true)
    setError('')

    try {
      if (isRunning) {
        await api.post('/generator/stop')
        appendLog(setLogs, '[CTRL] Generator stop requested')
      } else {
        await api.post('/generator/start', null, {
          params: {
            tps,
            fraud_injection_rate: fraudRate,
          },
        })
        appendLog(setLogs, `[CTRL] Generator start requested (TPS=${tps}, FRAUD_RATE=${Math.round(fraudRate * 100)}%)`)
      }

      setConfigDirty(false)
      configDirtyRef.current = false
      await fetchStatus()
    } catch (err) {
      console.error('Failed to toggle generator:', err)
      setError('Generator action failed.')
    } finally {
      setActionLoading(false)
    }
  }

  const handleApplyConfig = async () => {
    setActionLoading(true)
    setError('')

    try {
      await api.patch('/generator/config', {
        tps,
        fraud_injection_rate: fraudRate,
      })
      appendLog(setLogs, `[CTRL] Config updated (TPS=${tps}, FRAUD_RATE=${Math.round(fraudRate * 100)}%)`)
      setConfigDirty(false)
      configDirtyRef.current = false
      await fetchStatus()
    } catch (err) {
      console.error('Failed to update config:', err)
      setError('Failed to update generator config.')
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <PageWrapper>
      <div className="fd-generator-shell">
        <div className="fd-generator-head">
          <div>
            <h2>Synthetic Data Generator</h2>
            <p>Control the source of all platform data</p>
          </div>

          <div className={`fd-generator-status ${isRunning ? 'fd-generator-status-running' : 'fd-generator-status-idle'}`}>
            <div className={`fd-generator-status-dot ${isRunning ? 'fd-generator-status-dot-running' : ''}`} />
            <span>{isRunning ? 'Running' : statusLoading ? 'Checking...' : 'Standby'}</span>
          </div>
        </div>

        {configDirty ? <div className="fd-page-info">Configuration changed. Click `Apply Config` to persist values.</div> : null}
        {error ? <div className="fd-page-error">{error}</div> : null}

        <div className="fd-generator-grid">
          <Card className="fd-generator-control-card">
            <div className="fd-generator-panel-title">
              <Settings size={18} />
              <h3>Simulation Config</h3>
            </div>

            <div className="fd-generator-slider-group">
              <div className="fd-generator-slider-head">
                <label htmlFor="fd-generator-tps">Transactions/Sec</label>
                <span>{tps} TPS</span>
              </div>
              <input
                id="fd-generator-tps"
                type="range"
                min="1"
                max="50"
                value={tps}
                onChange={(e) => {
                  setTps(parseInt(e.target.value, 10))
                  configDirtyRef.current = true
                  setConfigDirty(true)
                }}
                className="fd-generator-range fd-generator-range-primary"
              />
            </div>

            <div className="fd-generator-slider-group">
              <div className="fd-generator-slider-head">
                <label htmlFor="fd-generator-fraud-rate">Simulated Fraud Rate</label>
                <span>{Math.round(fraudRate * 100)}%</span>
              </div>
              <input
                id="fd-generator-fraud-rate"
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={fraudRate}
                onChange={(e) => {
                  setFraudRate(parseFloat(e.target.value))
                  configDirtyRef.current = true
                  setConfigDirty(true)
                }}
                className="fd-generator-range fd-generator-range-alert"
              />
            </div>

            <div className="fd-generator-action-row">
              <Button className="fd-generator-main-btn" onClick={handleToggleGenerator} variant={isRunning ? 'danger' : 'primary'} disabled={actionLoading}>
                {isRunning ? <Square size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}
                <span>{isRunning ? 'Stop Simulation' : 'Start Simulation'}</span>
              </Button>

              <Button variant="secondary" className="fd-generator-apply-btn" onClick={handleApplyConfig} disabled={actionLoading || !configDirty}>
                <Save size={15} />
                Apply Config
              </Button>
            </div>
          </Card>

          <div className="fd-generator-side-stack">
            <Card variant="elevated" className="fd-generator-model-card">
              <div className="fd-generator-panel-title">
                <Layers size={18} className="text-primary" />
                <h3>Active Scenarios</h3>
              </div>

              <div className="fd-generator-model-list">
                {activeScenarios.length > 0 ? (
                  activeScenarios.map((scenario) => (
                    <div key={scenario} className="fd-generator-model-row">
                      <span>{scenario}</span>
                      <span className="fd-badge fd-badge-approved">Active</span>
                    </div>
                  ))
                ) : (
                  <div className="fd-generator-model-row">
                    <span>No active scenarios</span>
                    <span className="fd-badge fd-badge-medium">Idle</span>
                  </div>
                )}
              </div>
            </Card>

            <Card className="fd-generator-log-card">
              <div className="fd-generator-log-head">
                <div>
                  <RefreshCw size={17} className={isRunning ? 'fd-spin' : ''} />
                  <h3>Runtime Logs</h3>
                </div>
                <button type="button" onClick={() => setLogs([])}>Clear</button>
              </div>

              <div className="fd-generator-log-body">
                {logs.length > 0 ? (
                  logs.map((entry, index) => <p key={`${entry}-${index}`}>{entry}</p>)
                ) : (
                  <p className="fd-generator-log-idle">No runtime activity yet.</p>
                )}
              </div>
            </Card>
          </div>
        </div>
      </div>
    </PageWrapper>
  )
}

export default GeneratorPage
