import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import TransactionTable from '../components/tables/TransactionTable'
import TransactionDetailDrawer from '../components/fraud/TransactionDetailDrawer'
import { Filter, Search, Download, Calendar, RotateCcw } from 'lucide-react'
import api from '../services/api'
import { useSSE } from '../hooks/useSSE'

const PAGE_SIZE = 25

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
  is_flagged:
    tx.processing_status === 'ALERTED' ||
    tx.predicted_class === 'FRAUD' ||
    ['HIGH', 'CRITICAL'].includes(tx.risk_level || ''),
  is_approved:
    tx.processing_status === 'RESOLVED' && tx.predicted_class !== 'FRAUD'
      ? true
      : tx.predicted_class !== 'FRAUD' && ['LOW', 'MEDIUM'].includes(tx.risk_level || ''),
})

const TransactionsPage = () => {
  const [selectedTx, setSelectedTx] = useState(null)
  const [transactions, setTransactions] = useState([])
  const [total, setTotal] = useState(0)
  const [flaggedTotal, setFlaggedTotal] = useState(0)
  const [approvedTotal, setApprovedTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [last24Hours, setLast24Hours] = useState(false)
  const [showFilters, setShowFilters] = useState(false)
  const [riskFilter, setRiskFilter] = useState('')
  const [channelFilter, setChannelFilter] = useState('')

  const liveRefreshRef = useRef(0)
  const requestIdRef = useRef(0)
  const lastTxEvent = useSSE('/api/v1/stream/transactions')

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / PAGE_SIZE)), [total])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(1)
      setSearch(searchInput.trim())
    }, 350)

    return () => window.clearTimeout(timer)
  }, [searchInput])

  const fetchTransactions = useCallback(async ({ silent = false } = {}) => {
    const requestId = ++requestIdRef.current

    if (!silent) {
      setLoading(true)
      setError('')
    }

    try {
      const params = {
        page,
        size: PAGE_SIZE,
        synthetic_only: true,
      }

      if (search) params.search = search
      if (riskFilter) params.risk_level = riskFilter
      if (channelFilter) params.channel = channelFilter
      if (last24Hours) {
        const since = new Date(Date.now() - 24 * 60 * 60 * 1000)
        params.start_date = since.toISOString()
      }

      const response = await api.get('/transactions', { params })
      const payload = response.data
      const rows = Array.isArray(payload.items) ? payload.items : []
      const mappedRows = rows.map(mapTransaction)

      if (requestId !== requestIdRef.current) return
      setTransactions(mappedRows)
      setTotal(payload.total || 0)
      setFlaggedTotal(
        typeof payload.flagged_count === 'number'
          ? payload.flagged_count
          : mappedRows.filter((tx) => tx.is_flagged).length,
      )
      setApprovedTotal(
        typeof payload.approved_count === 'number'
          ? payload.approved_count
          : mappedRows.filter((tx) => tx.is_approved).length,
      )
    } catch (err) {
      console.error('Failed to fetch transactions:', err)
      if (requestId !== requestIdRef.current) return
      setTransactions([])
      setTotal(0)
      setFlaggedTotal(0)
      setApprovedTotal(0)
      setError('Failed to load transactions from backend.')
    } finally {
      if (requestId === requestIdRef.current && !silent) setLoading(false)
    }
  }, [page, search, riskFilter, channelFilter, last24Hours])

  useEffect(() => {
    fetchTransactions()
  }, [fetchTransactions])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      fetchTransactions({ silent: true })
    }, 5000)

    return () => window.clearInterval(intervalId)
  }, [fetchTransactions])

  useEffect(() => {
    if (!lastTxEvent || lastTxEvent.status === 'keep-alive') return
    const eventType = String(lastTxEvent.event_type || 'transaction_ingested').toLowerCase()
    if (!['transaction_ingested', 'alert_updated'].includes(eventType)) return

    const now = Date.now()
    if (now - liveRefreshRef.current < 1200) return
    liveRefreshRef.current = now

    // Keep live feed focused on freshest page when simulation runs.
    if (eventType === 'transaction_ingested' && page !== 1) {
      setPage(1)
      return
    }

    fetchTransactions({ silent: true })
  }, [lastTxEvent, page, fetchTransactions])

  useEffect(() => {
    if (!selectedTx) return
    const latest = transactions.find((tx) => tx.transaction_id === selectedTx.transaction_id)
    if (latest && latest !== selectedTx) {
      setSelectedTx(latest)
    }
  }, [transactions, selectedTx])

  const flaggedCount = useMemo(() => flaggedTotal, [flaggedTotal])
  const approvedCount = useMemo(() => approvedTotal, [approvedTotal])

  const handleExportCSV = async () => {
    try {
      const params = {}
      params.synthetic_only = true
      if (search) params.search = search
      if (riskFilter) params.risk_level = riskFilter
      if (channelFilter) params.channel = channelFilter
      if (last24Hours) {
        const since = new Date(Date.now() - 24 * 60 * 60 * 1000)
        params.start_date = since.toISOString()
      }

      const response = await api.get('/transactions/export', {
        params,
        responseType: 'blob',
      })

      const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8;' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', `transactions_export_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`)
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to export transactions:', err)
      setError('Export failed. Please try again.')
    }
  }

  const resetFilters = () => {
    setRiskFilter('')
    setChannelFilter('')
    setLast24Hours(false)
    setPage(1)
  }

  return (
    <PageWrapper>
      <div className="fd-tab-stack">
        <section className="fd-transactions-toolbar">
          <div className="fd-transactions-toolbar-left">
            <label className="fd-toolbar-search" htmlFor="fd-transactions-search">
              <Search size={15} />
              <input
                id="fd-transactions-search"
                type="text"
                placeholder="Search transaction ID, merchant, or card..."
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </label>

            <div className="fd-toolbar-actions">
              <Button
                variant="secondary"
                className={`fd-tab-btn ${last24Hours ? 'fd-tab-btn-active' : ''}`}
                onClick={() => {
                  setPage(1)
                  setLast24Hours(prev => !prev)
                }}
              >
                <Calendar size={14} />
                Last 24 Hours
              </Button>
              <Button
                variant="secondary"
                className={`fd-tab-btn ${showFilters ? 'fd-tab-btn-active' : ''}`}
                onClick={() => setShowFilters(prev => !prev)}
              >
                <Filter size={14} />
                Filters
              </Button>
            </div>
          </div>

          <Button variant="secondary" className="fd-tab-btn fd-tab-btn-export" onClick={handleExportCSV}>
            <Download size={14} />
            Export CSV
          </Button>
        </section>

        {showFilters ? (
          <section className="fd-filter-panel">
            <div className="fd-filter-item">
              <label htmlFor="fd-risk-filter">Risk</label>
              <select
                id="fd-risk-filter"
                value={riskFilter}
                onChange={(e) => {
                  setPage(1)
                  setRiskFilter(e.target.value)
                }}
              >
                <option value="">All</option>
                <option value="LOW">Low</option>
                <option value="MEDIUM">Medium</option>
                <option value="HIGH">High</option>
                <option value="CRITICAL">Critical</option>
              </select>
            </div>

            <div className="fd-filter-item">
              <label htmlFor="fd-channel-filter">Channel</label>
              <select
                id="fd-channel-filter"
                value={channelFilter}
                onChange={(e) => {
                  setPage(1)
                  setChannelFilter(e.target.value)
                }}
              >
                <option value="">All</option>
                <option value="ONLINE">Online</option>
                <option value="POS">POS</option>
                <option value="ATM">ATM</option>
              </select>
            </div>

            <Button variant="secondary" className="fd-tab-btn-small" onClick={resetFilters}>
              <RotateCcw size={13} />
              Reset
            </Button>
          </section>
        ) : null}

        <section className="fd-tab-stat-grid">
          <div className="fd-tab-stat fd-tab-stat-default">
            <span>Selected Period</span>
            <p>{last24Hours ? 'Last 24 Hours' : 'All Time'}</p>
          </div>
          <div className="fd-tab-stat fd-tab-stat-default">
            <span>Transactions</span>
            <p>{total}</p>
          </div>
          <div className="fd-tab-stat fd-tab-stat-alert">
            <span>Flagged</span>
            <p>{flaggedCount}</p>
          </div>
          <div className="fd-tab-stat fd-tab-stat-success">
            <span>Approved</span>
            <p>{approvedCount}</p>
          </div>
        </section>

        {error ? <div className="fd-page-error">{error}</div> : null}

        <Card className="fd-table-card-shell">
          {loading ? (
            <div className="fd-page-loading">Loading transactions...</div>
          ) : (
            <TransactionTable transactions={transactions} onRowClick={(tx) => setSelectedTx(tx)} />
          )}

          <div className="fd-table-card-footer">
            <span>
              Showing {transactions.length === 0 ? 0 : (page - 1) * PAGE_SIZE + 1} to {(page - 1) * PAGE_SIZE + transactions.length} of {total} results
            </span>
            <div className="fd-table-pager">
              <Button variant="secondary" className="fd-tab-btn-small" disabled={page <= 1} onClick={() => setPage(prev => Math.max(1, prev - 1))}>
                Previous
              </Button>
              <Button variant="secondary" className="fd-tab-btn-small" disabled={page >= totalPages} onClick={() => setPage(prev => Math.min(totalPages, prev + 1))}>
                Next
              </Button>
            </div>
          </div>
        </Card>
      </div>

      <TransactionDetailDrawer transaction={selectedTx} onClose={() => setSelectedTx(null)} />
    </PageWrapper>
  )
}

export default TransactionsPage
