import { useState, useEffect, useRef } from 'react'
import { useAuthStore } from '../store/useAuthStore'

export const useSSE = (url) => {
  const [lastEvent, setLastEvent] = useState(null)
  const token = useAuthStore(state => state.token)
  const reconnectTimerRef = useRef(null)

  useEffect(() => {
    if (!token) return

    let isMounted = true
    let eventSource = null

    const connect = () => {
      if (!isMounted) return

      eventSource = new EventSource(`${url}?token=${token}`)

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          setLastEvent(data)
        } catch (err) {
          console.error('Error parsing SSE event:', err)
        }
      }

      eventSource.onerror = (err) => {
        console.error('SSE Error:', err)
        eventSource.close()

        if (isMounted) {
          reconnectTimerRef.current = window.setTimeout(connect, 3000)
        }
      }
    }

    connect()

    return () => {
      isMounted = false
      if (eventSource) eventSource.close()
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
      }
    }
  }, [url, token])

  return lastEvent
}
