import React, { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuthStore } from '../store/useAuthStore'

const AuthCallbackPage = () => {
  const [message, setMessage] = useState('Completing secure sign in...')
  const location = useLocation()
  const navigate = useNavigate()
  const login = useAuthStore((state) => state.login)

  useEffect(() => {
    const params = new URLSearchParams(location.hash.replace(/^#/, ''))
    const accessToken = params.get('access_token')
    const email = params.get('email')

    if (!accessToken || !email) {
      setMessage('Authentication failed. Returning to login...')
      window.setTimeout(() => navigate('/login', { replace: true }), 900)
      return
    }

    login(
      {
        email,
        name: params.get('name') || email.split('@')[0],
        role: params.get('role') || 'analyst'
      },
      accessToken
    )
    navigate('/dashboard', { replace: true })
  }, [location.hash, login, navigate])

  return (
    <div className="fd-auth-callback-page">
      <section className="fd-auth-callback-card fd-fade-up" aria-live="polite">
        <Loader2 size={24} className="fd-spin" />
        <p>{message}</p>
      </section>
    </div>
  )
}

export default AuthCallbackPage
