import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import TransactionTable from '../components/tables/TransactionTable'
import FraudRateTrendChart from '../components/charts/FraudRateTrendChart'
import RiskDistributionChart from '../components/charts/RiskDistributionChart'
import TimeHeatmapChart from '../components/charts/TimeHeatmapChart'
import TransactionDetailDrawer from '../components/fraud/TransactionDetailDrawer'
import { ShieldCheck, Crosshair, AlertTriangle, TrendingUp } from 'lucide-react'
import { useSSE } from '../hooks/useSSE'
import api from '../services/api'
import { getFraudRateTrend, getFraudSummary, getRiskDistribution, getTimeHeatmap } from '../services/analytics'

const DASHBOARD_SNAPSHOT_KEY = 'fd_dashboard_snapshot_v1'
const DEFAULT_SUMMARY = {
  total_volume: 0,
  fraud_rate: 0,
  open_alerts: 0,
  approved_transactions: 0,
  total_transactions: 0,
  flagged_transactions: 0,
}

const RISK_COLORS = {
  LOW: '#10B981',
  MEDIUM: '#F59E0B',
  HIGH: '#F97316',
  CRITICAL: '#EF4444',
}

const normalizeShapValues = (shapFeatures) => {
  if (Array.isArray(shapFeatures)) {
    return shapFeatures.map((item) => ({
      feature: item.feature || item.name || 'Feature',
      value: Number(item.value ?? item.shap_value ?? 0)
    }))
  }

  if (shapFeatures && typeof shapFeatures === 'object') {
    return Object.entries(shapFeatures).map(([feature, value]) => ({
      feature,
      value: Number(value || 0)
    }))
  }

  return []
}

const mapTransaction = (tx) => ({
  transaction_id: tx.id,
  timestamp: tx.created_at,
  amount: tx.amount || 0,
  merchant: tx.merchant_name || tx.merchant_id || 'Unknown',
  merchant_category: tx.mcc || 'General',
  channel: tx.channel || 'N/A',
  device_id: tx.device_id || 'N/A',
  risk_level: tx.risk_level || 'LOW',
  processing_status: tx.processing_status || 'SCORED',
  predicted_class: tx.predicted_class || 'LEGITIMATE',
  fraud_score: tx.fraud_score ?? 0,
  shap_values: normalizeShapValues(tx.shap_features),
  card_id: tx.card_id_hash || 'N/A',
  geo_city: tx.geo_city || 'Unknown',
  geo_country: tx.geo_country || 'N/A',
  lat: tx.geo_lat,
  lon: tx.geo_lon,
})

const safeParseSnapshot = (rawValue) => {
  if (!rawValue) return null
  try {
    const parsed = JSON.parse(rawValue)
    if (!parsed || typeof parsed !== 'object') return null
    return parsed
  } catch (err) {
    console.warn('Dashboard snapshot parse failed:', err)
    return null
  }
}

const readDashboardSnapshot = () => {
  if (typeof window === 'undefined') return null
  return safeParseSnapshot(window.localStorage.getItem(DASHBOARD_SNAPSHOT_KEY))
}

const DashboardPage = () => {
  const initialSnapshot = useMemo(() => readDashboardSnapshot(), [])
  const [selectedTx, setSelectedTx] = useState(null)
  const [summary, setSummary] = useState(initialSnapshot?.summary || DEFAULT_SUMMARY)
  const [transactions, setTransactions] = useState(initialSnapshot?.transactions || [])
  const [trendPoints, setTrendPoints] = useState(initialSnapshot?.trendPoints || [])
  const [riskDistribution, setRiskDistribution] = useState(initialSnapshot?.riskDistribution || [])
  const [heatmapData, setHeatmapData] = useState(initialSnapshot?.heatmapData || [])
  const [loading, setLoading] = useState(!initialSnapshot)
  const [error, setError] = useState('')
  const requestIdRef = useRef(0)
  const liveRefreshRef = useRef(0)

  const lastTxEvent = useSSE('/api/v1/stream/transactions')

  const fetchDashboardData = useCallback(async ({ silent = false } = {}) => {
    const requestId = ++requestIdRef.current
    if (!silent) {
      setLoading(true)
      setError('')
    }

    try {
      const [summaryPayload, trendPayload, riskPayload, heatmapPayload, txResponse] = await Promise.all([
        getFraudSummary({ time_range: '24h', synthetic_only: true }),
        getFraudRateTrend({ period: '1h', time_range: '24h', synthetic_only: true }),
        getRiskDistribution({ time_range: '24h', synthetic_only: true }),
        getTimeHeatmap({ time_range: '7d', synthetic_only: true }),
        api.get('/transactions', { params: { page: 1, size: 10, synthetic_only: true } }),
      ])

      if (requestId !== requestIdRef.current) return

      const trendPointsRaw = Array.isArray(trendPayload?.points) ? trendPayload.points : []
      const riskLabels = Array.isArray(riskPayload?.labels) ? riskPayload.labels : []
      const riskValues = Array.isArray(riskPayload?.data) ? riskPayload.data : []
      const mappedRisk = riskLabels.map((label, index) => {
        const key = String(label || '').toUpperCase()
        return {
          tier: label ? `${label.charAt(0)}${label.slice(1).toLowerCase()}` : 'Unknown',
          count: Number(riskValues[index] || 0),
          color: RISK_COLORS[key] || '#94A3B8',
        }
      })

      const txItems = Array.isArray(txResponse?.data?.items) ? txResponse.data.items : []
      const nextSummary = summaryPayload && typeof summaryPayload === 'object'
        ? { ...DEFAULT_SUMMARY, ...summaryPayload }
        : null
      const nextHeatmap = Array.isArray(heatmapPayload?.heatmap_data) ? heatmapPayload.heatmap_data : []
      const nextTransactions = txItems.map(mapTransaction)

      if (nextSummary) {
        setSummary(nextSummary)
      } else if (!silent) {
        setSummary((prev) => ({ ...DEFAULT_SUMMARY, ...prev }))
      }

      setTrendPoints((prev) => (trendPointsRaw.length > 0 ? trendPointsRaw : prev))
      setRiskDistribution((prev) => (mappedRisk.length > 0 ? mappedRisk : prev))
      setHeatmapData((prev) => (nextHeatmap.length > 0 ? nextHeatmap : prev))
      setTransactions((prev) => (nextTransactions.length > 0 ? nextTransactions : prev))

      if (typeof window !== 'undefined') {
        const previousSnapshot = readDashboardSnapshot() || {}
        const snapshot = {
          summary: nextSummary || previousSnapshot.summary || DEFAULT_SUMMARY,
          trendPoints: trendPointsRaw.length > 0 ? trendPointsRaw : (previousSnapshot.trendPoints || []),
          riskDistribution: mappedRisk.length > 0 ? mappedRisk : (previousSnapshot.riskDistribution || []),
          heatmapData: nextHeatmap.length > 0 ? nextHeatmap : (previousSnapshot.heatmapData || []),
          transactions: nextTransactions.length > 0 ? nextTransactions : (previousSnapshot.transactions || []),
        }
        window.localStorage.setItem(DASHBOARD_SNAPSHOT_KEY, JSON.stringify(snapshot))
      }
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err)
      if (requestId !== requestIdRef.current) return
      setError('Failed to load live dashboard analytics.')
    } finally {
      if (requestId === requestIdRef.current && !silent) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    fetchDashboardData()
  }, [fetchDashboardData])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      fetchDashboardData({ silent: true })
    }, 8000)
    return () => window.clearInterval(intervalId)
  }, [fetchDashboardData])

  useEffect(() => {
    if (!lastTxEvent || lastTxEvent.status === 'keep-alive') return
    const eventType = String(lastTxEvent.event_type || '').toLowerCase()
    if (!['transaction_ingested', 'alert_updated', 'generator_stopped'].includes(eventType)) return

    const now = Date.now()
    if (now - liveRefreshRef.current < 1200) return
    liveRefreshRef.current = now
    fetchDashboardData({ silent: true })
  }, [lastTxEvent, fetchDashboardData])

  useEffect(() => {
    if (!selectedTx) return
    const latest = transactions.find((tx) => tx.transaction_id === selectedTx.transaction_id)
    if (latest && latest !== selectedTx) {
      setSelectedTx(latest)
    }
  }, [transactions, selectedTx])

  const totalVolumeValue = useMemo(
    () => `$ ${Number(summary.total_volume || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}`,
    [summary.total_volume],
  )

  const kpis = useMemo(() => ([
    {
      label: 'Total Volume',
      value: totalVolumeValue,
      trend: `${Number(summary.total_transactions || 0).toLocaleString()} tx`,
      icon: TrendingUp,
      tone: 'primary'
    },
    {
      label: 'Fraud Rate',
      value: `${Number(summary.fraud_rate || 0).toFixed(2)}%`,
      trend: `${Number(summary.flagged_transactions || 0).toLocaleString()} flagged`,
      icon: AlertTriangle,
      tone: 'alert'
    },
    {
      label: 'Open Alerts',
      value: `${Number(summary.open_alerts || 0).toLocaleString()}`,
      trend: 'Active queue',
      icon: Crosshair,
      tone: 'warning'
    },
    {
      label: 'Approved',
      value: `${Number(summary.approved_transactions || 0).toLocaleString()}`,
      trend: 'Cleared by model/rules',
      icon: ShieldCheck,
      tone: 'success'
    },
  ]), [summary, totalVolumeValue])

  const getKpiToneClass = (tone) => {
    switch (tone) {
      case 'alert':
        return 'fd-kpi-icon-alert'
      case 'warning':
        return 'fd-kpi-icon-warning'
      case 'success':
        return 'fd-kpi-icon-success'
      default:
        return 'fd-kpi-icon-primary'
    }
  }

  const getTrendClass = (trend) => {
    if (trend.startsWith('+')) return 'fd-kpi-trend-up'
    if (trend.startsWith('-')) return 'fd-kpi-trend-down'
    return 'fd-kpi-trend-neutral'
  }

  return (
    <PageWrapper>
      <div className="fd-dashboard-layout">
        <section className="fd-kpi-grid">
          {kpis.map((kpi) => (
            <Card key={kpi.label} variant="elevated" className="fd-kpi-card fd-hover-lift">
              <div className="fd-kpi-top">
                <div className="fd-kpi-copy">
                  <span className="fd-kpi-label">{kpi.label}</span>
                  <h3 className="fd-kpi-value">{kpi.value}</h3>
                </div>
                <div className={`fd-kpi-icon ${getKpiToneClass(kpi.tone)}`}>
                  <kpi.icon size={20} />
                </div>
              </div>
              <div className="fd-kpi-meta">
                <span className={`fd-kpi-trend ${getTrendClass(kpi.trend)}`}>{kpi.trend}</span>
                <span className="fd-kpi-caption">vs yesterday</span>
              </div>
            </Card>
          ))}
        </section>

        {error ? <div className="fd-page-error">{error}</div> : null}

        <section className="fd-dashboard-grid-main">
          <Card className="fd-panel fd-panel-large">
            <div className="fd-panel-head">
              <h3 className="fd-panel-title">Fraud Rate Trend</h3>
              <div className="fd-chart-legend">
                <span className="fd-dot fd-dot-primary" />
                <span>Rate %</span>
                <span className="fd-dot fd-dot-muted" />
                <span>Volume</span>
              </div>
            </div>
            <div className="fd-chart-shell">
              <FraudRateTrendChart data={trendPoints} />
            </div>
          </Card>

          <Card className="fd-panel">
            <div className="fd-panel-head">
              <h3 className="fd-panel-title">Risk Distribution</h3>
            </div>
            <div className="fd-chart-shell">
              <RiskDistributionChart data={riskDistribution} />
            </div>
          </Card>
        </section>

        <section className="fd-dashboard-grid-secondary">
          <Card className="fd-panel">
            <TimeHeatmapChart data={heatmapData} />
          </Card>

          <Card className="fd-panel fd-live-feed-panel">
            <div className="fd-panel-head">
              <div className="fd-live-headline">
                <h3 className="fd-panel-title">Live Feed</h3>
                <span className="fd-pulse-live" />
              </div>
              <button type="button" className="fd-panel-link">View All</button>
            </div>

            {loading ? (
              <div className="fd-page-loading">Loading live feed...</div>
            ) : (
              <TransactionTable transactions={transactions} onRowClick={(tx) => setSelectedTx(tx)} />
            )}
          </Card>
        </section>
      </div>

      <TransactionDetailDrawer transaction={selectedTx} onClose={() => setSelectedTx(null)} />
    </PageWrapper>
  )
}

export default DashboardPage
