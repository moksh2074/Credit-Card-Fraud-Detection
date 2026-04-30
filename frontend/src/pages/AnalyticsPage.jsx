import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import FraudRateTrendChart from '../components/charts/FraudRateTrendChart'
import DeviceChannelChart from '../components/charts/DeviceChannelChart'
import MerchantCategoryChart from '../components/charts/MerchantCategoryChart'
import TimeHeatmapChart from '../components/charts/TimeHeatmapChart'
import { BarChart3, Globe, Clock, Smartphone, ShoppingBag } from 'lucide-react'
import { useSSE } from '../hooks/useSSE'
import {
  getDeviceChannelStats,
  getFraudRateTrend,
  getMerchantCategoryStats,
  getModelPerformance,
  getTimeHeatmap,
} from '../services/analytics'

const CHANNEL_COLORS = ['#6366F1', '#38BDF8', '#818CF8', '#94A3B8', '#10B981', '#F97316']
const ANALYTICS_SNAPSHOT_KEY = 'fd_analytics_snapshot_v1'

const safeParseSnapshot = (rawValue) => {
  if (!rawValue) return null
  try {
    const parsed = JSON.parse(rawValue)
    if (!parsed || typeof parsed !== 'object') return null
    return parsed
  } catch (err) {
    console.warn('Analytics snapshot parse failed:', err)
    return null
  }
}

const readAnalyticsSnapshot = () => {
  if (typeof window === 'undefined') return null
  return safeParseSnapshot(window.localStorage.getItem(ANALYTICS_SNAPSHOT_KEY))
}

const AnalyticsPage = () => {
  const initialSnapshot = useMemo(() => readAnalyticsSnapshot(), [])
  const [trendData, setTrendData] = useState(initialSnapshot?.trendData || [])
  const [deviceChannelData, setDeviceChannelData] = useState(initialSnapshot?.deviceChannelData || [])
  const [merchantData, setMerchantData] = useState(initialSnapshot?.merchantData || [])
  const [heatmapData, setHeatmapData] = useState(initialSnapshot?.heatmapData || [])
  const [precision, setPrecision] = useState(initialSnapshot?.precision || 0)
  const [loading, setLoading] = useState(!initialSnapshot)
  const [error, setError] = useState('')
  const requestIdRef = useRef(0)
  const liveRefreshRef = useRef(0)
  const lastTxEvent = useSSE('/api/v1/stream/transactions')

  const fetchAnalyticsData = useCallback(async ({ silent = false } = {}) => {
    const requestId = ++requestIdRef.current
    if (!silent) {
      setLoading(true)
      setError('')
    }

    try {
      const [trendPayload, devicePayload, merchantPayload, heatmapPayload, modelPayload] = await Promise.all([
        getFraudRateTrend({ period: '1h', time_range: '7d', synthetic_only: true }),
        getDeviceChannelStats({ time_range: '7d', synthetic_only: true }),
        getMerchantCategoryStats({ time_range: '7d', synthetic_only: true }),
        getTimeHeatmap({ time_range: '7d', synthetic_only: true }),
        getModelPerformance({ time_range: '7d', synthetic_only: true }),
      ])

      if (requestId !== requestIdRef.current) return

      const trendPoints = Array.isArray(trendPayload?.points) ? trendPayload.points : []
      const channelDataRaw = Array.isArray(devicePayload?.channel_data) ? devicePayload.channel_data : []
      const channelData = channelDataRaw.map((item, index) => ({
        name: String(item.name || 'UNKNOWN'),
        value: Number(item.value || 0),
        color: CHANNEL_COLORS[index % CHANNEL_COLORS.length],
      }))

      const merchantItemsRaw = Array.isArray(merchantPayload?.items) ? merchantPayload.items : []
      const merchantItems = merchantItemsRaw.map((item) => ({
        category: String(item.category || 'UNKNOWN'),
        rate: Number(item.rate || 0),
      }))

      const nextHeatmap = Array.isArray(heatmapPayload?.heatmap_data) ? heatmapPayload.heatmap_data : []
      const nextPrecision = Number(modelPayload?.precision || 0)

      setTrendData((prev) => (trendPoints.length > 0 ? trendPoints : prev))
      setDeviceChannelData((prev) => (channelData.length > 0 ? channelData : prev))
      setMerchantData((prev) => (merchantItems.length > 0 ? merchantItems : prev))
      setHeatmapData((prev) => (nextHeatmap.length > 0 ? nextHeatmap : prev))
      setPrecision((prev) => (Number.isFinite(nextPrecision) ? nextPrecision : prev))

      if (typeof window !== 'undefined') {
        const previousSnapshot = readAnalyticsSnapshot() || {}
        const snapshot = {
          trendData: trendPoints.length > 0 ? trendPoints : (previousSnapshot.trendData || []),
          deviceChannelData: channelData.length > 0 ? channelData : (previousSnapshot.deviceChannelData || []),
          merchantData: merchantItems.length > 0 ? merchantItems : (previousSnapshot.merchantData || []),
          heatmapData: nextHeatmap.length > 0 ? nextHeatmap : (previousSnapshot.heatmapData || []),
          precision: Number.isFinite(nextPrecision) ? nextPrecision : (previousSnapshot.precision || 0),
        }
        window.localStorage.setItem(ANALYTICS_SNAPSHOT_KEY, JSON.stringify(snapshot))
      }
    } catch (err) {
      console.error('Failed to fetch analytics data:', err)
      if (requestId !== requestIdRef.current) return
      setError('Failed to load analytics data.')
    } finally {
      if (requestId === requestIdRef.current && !silent) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    fetchAnalyticsData()
  }, [fetchAnalyticsData])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      fetchAnalyticsData({ silent: true })
    }, 10000)
    return () => window.clearInterval(intervalId)
  }, [fetchAnalyticsData])

  useEffect(() => {
    if (!lastTxEvent || lastTxEvent.status === 'keep-alive') return
    const eventType = String(lastTxEvent.event_type || '').toLowerCase()
    if (!['transaction_ingested', 'alert_updated', 'generator_stopped'].includes(eventType)) return

    const now = Date.now()
    if (now - liveRefreshRef.current < 1200) return
    liveRefreshRef.current = now
    fetchAnalyticsData({ silent: true })
  }, [lastTxEvent, fetchAnalyticsData])

  return (
    <PageWrapper>
      <div className="fd-analytics-stack">
        {error ? <div className="fd-page-error">{error}</div> : null}

        <Card className="fd-analytics-hero">
          <div className="fd-analytics-hero-head">
            <div className="fd-analytics-title-wrap">
              <div className="fd-analytics-icon">
                <BarChart3 size={20} />
              </div>
              <div>
                <h2>Long-term Fraud Trends</h2>
                <p>Historical analysis of fraud rates vs transaction volume</p>
              </div>
            </div>

            <div className="fd-analytics-chip">
              <span>Precision:</span>
              <strong>{(precision * 100).toFixed(1)}%</strong>
            </div>
          </div>

          <div className="fd-analytics-chart-lg">
            {loading ? <div className="fd-page-loading">Loading analytics...</div> : <FraudRateTrendChart data={trendData} />}
          </div>
        </Card>

        <section className="fd-analytics-grid-two">
          <Card className="fd-analytics-panel">
            <div className="fd-analytics-panel-head">
              <Smartphone size={18} />
              <h3>Device & Channel Risk</h3>
            </div>
            <div className="fd-analytics-chart-md">
              <DeviceChannelChart data={deviceChannelData} />
            </div>
          </Card>

          <Card className="fd-analytics-panel">
            <div className="fd-analytics-panel-head">
              <ShoppingBag size={18} />
              <h3>Merchant Category High-Risk</h3>
            </div>
            <div className="fd-analytics-chart-md">
              <MerchantCategoryChart data={merchantData} />
            </div>
          </Card>
        </section>

        <section className="fd-analytics-grid-two">
          <Card className="fd-analytics-panel fd-analytics-map-panel">
            <div className="fd-analytics-panel-head">
              <Globe size={18} />
              <h3>Global Fraud Hotspots</h3>
            </div>

            <div className="fd-analytics-map">
              <div className="fd-analytics-map-layer" />
              <div className="fd-analytics-map-center">
                <Globe size={44} />
                <p>Geographic Map Component</p>
                <span>Connect React Leaflet with transaction coordinates to visualize real-time spatial clusters.</span>
              </div>
              <div className="fd-analytics-map-badge">
                <div />
                <span>Critical Cluster</span>
              </div>
            </div>
          </Card>

          <Card className="fd-analytics-panel">
            <div className="fd-analytics-panel-head">
              <Clock size={18} />
              <h3>Temporal Density Heatmap</h3>
            </div>
            <div className="fd-analytics-heatmap-wrap">
              <TimeHeatmapChart data={heatmapData} />
            </div>
          </Card>
        </section>
      </div>
    </PageWrapper>
  )
}

export default AnalyticsPage
