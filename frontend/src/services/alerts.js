import api from './api'

export const getAlerts = async (params = {}) => {
  const { data } = await api.get('/alerts', { params })
  return data
}

export const updateAlertStatus = async (alertId, status) => {
  const { data } = await api.patch(`/alerts/${alertId}`, { status })
  return data
}

export const getAlertStats = async () => {
  const { data } = await api.get('/alerts/stats')
  return data
}
