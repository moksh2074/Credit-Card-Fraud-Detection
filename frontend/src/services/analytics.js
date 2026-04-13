import api from './api'

export const getFraudSummary = async (params = {}) => {
  const { data } = await api.get('/analytics/fraud-summary', { params })
  return data
}

export const getFraudRateTrend = async (params = {}) => {
  const { data } = await api.get('/analytics/fraud-rate-trend', { params })
  return data
}

export const getRiskDistribution = async (params = {}) => {
  const { data } = await api.get('/analytics/risk-distribution', { params })
  return data
}

export const getDeviceChannelStats = async (params = {}) => {
  const { data } = await api.get('/analytics/device-channel', { params })
  return data
}

export const getMerchantCategoryStats = async (params = {}) => {
  const { data } = await api.get('/analytics/merchant-category', { params })
  return data
}

export const getTimeHeatmap = async (params = {}) => {
  const { data } = await api.get('/analytics/time-heatmap', { params })
  return data
}

export const getModelPerformance = async (params = {}) => {
  const { data } = await api.get('/analytics/model-performance', { params })
  return data
}
