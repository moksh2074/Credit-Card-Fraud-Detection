import api from './api'

export const startGenerator = async (config) => {
  const { data } = await api.post('/generator/start', config)
  return data
}

export const stopGenerator = async () => {
  const { data } = await api.post('/generator/stop')
  return data
}

export const getGeneratorStatus = async () => {
  const { data } = await api.get('/generator/status')
  return data
}
