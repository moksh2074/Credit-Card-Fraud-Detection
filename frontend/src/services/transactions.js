import api from './api'

export const getTransactions = async (params = {}) => {
  const { data } = await api.get('/transactions', { params })
  return data
}

export const getTransactionById = async (id) => {
  const { data } = await api.get(`/transactions/${id}`)
  return data
}

export const searchTransactions = async (query) => {
  const { data } = await api.get('/transactions/search', { params: { query } })
  return data
}
