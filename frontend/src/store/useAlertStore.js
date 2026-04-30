import { create } from 'zustand'

const normalizeStatus = (status) => String(status || '').toLowerCase()

const isOpenAlert = (status) => {
  const value = normalizeStatus(status)
  return value === 'open' || value === 'new' || value === 'acknowledged' || value === 'investigating'
}

export const useAlertStore = create((set) => ({
  openAlertCount: 0,
  alerts: [],
  setAlerts: (alerts) =>
    set({
      alerts,
      openAlertCount: alerts.filter(a => isOpenAlert(a.status)).length
    }),
  addAlert: (alert) =>
    set((state) => ({
      alerts: [alert, ...state.alerts],
      openAlertCount: state.openAlertCount + (isOpenAlert(alert.status) ? 1 : 0)
    })),
  updateAlert: (updatedAlert) =>
    set((state) => {
      const alerts = state.alerts.map(alert => alert.id === updatedAlert.id ? { ...alert, ...updatedAlert } : alert)
      return {
        alerts,
        openAlertCount: alerts.filter(a => isOpenAlert(a.status)).length
      }
    })
}))
