import React, { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  Mail,
  Lock,
  Loader2,
  Eye,
  EyeOff,
  Cloud
} from 'lucide-react'
import axios from 'axios'
import { useAuthStore } from '../store/useAuthStore'

const GoogleLogo = () => (
  <svg className="fd-login-google-logo" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
    <path fill="#FBBC05" d="M5.84 14.1c-.22-.66-.35-1.36-.35-2.1s.13-1.44.35-2.1V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l3.66-2.84z" />
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06L5.84 9.9c.87-2.6 3.3-4.52 6.16-4.52z" />
  </svg>
)

const LoginPage = () => {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSignupMode, setIsSignupMode] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const login = useAuthStore((state) => state.login)
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  useEffect(() => {
    const authError = searchParams.get('auth_error')
    if (authError) {
      setError(authError)
    }
  }, [searchParams])

  const toggleMode = () => {
    setIsSignupMode((prev) => !prev)
    setError('')
  }

  const startGoogleAuth = () => {
    const params = new URLSearchParams({
      provider: 'google',
      mode: isSignupMode ? 'signup' : 'login'
    })
    window.location.assign(`/api/v1/auth/appid/login?${params.toString()}`)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')

    const normalizedEmail = email.trim().toLowerCase()
    const normalizedPassword = password.trim()
    const normalizedConfirmPassword = confirmPassword.trim()

    try {
      if (isSignupMode) {
        if (!normalizedPassword || normalizedPassword.length < 6) {
          setError('Password must be at least 6 characters.')
          return
        }

        if (normalizedPassword !== normalizedConfirmPassword) {
          setError('Passwords do not match.')
          return
        }
      }

      const endpoint = isSignupMode
        ? '/api/v1/auth/appid/cloud-directory/register'
        : '/api/v1/auth/appid/cloud-directory/login'

      const response = await axios.post(endpoint, {
        email: normalizedEmail,
        password: normalizedPassword
      })

      const { access_token, user: userData } = response.data
      const user = userData || { email: normalizedEmail, name: normalizedEmail.split('@')[0], role: 'admin' }

      login(user, access_token)
      navigate('/dashboard')
    } catch (err) {
      console.error('Login error:', err)
      if (err.response && err.response.data && err.response.data.detail) {
        setError(err.response.data.detail)
      } else {
        setError('Connection failed. Please check if the backend is running.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fd-login-page">
      <div className="fd-login-bg" aria-hidden="true" />
      <div className="fd-login-grid" aria-hidden="true" />

      <section className="fd-login-card fd-fade-up" aria-label="Login form">
        <div className="fd-login-orbital" aria-hidden="true">
          <span className="fd-login-orbit-ring" />
          <span className="fd-login-orbit-core" />
        </div>

        <h1 className="fd-login-title">Welcome Back</h1>
        <p className="fd-login-subtitle">
          {isSignupMode ? 'Already have an account?' : "Don't have an account yet?"}{' '}
          <button type="button" className="fd-login-link fd-login-link-btn" onClick={toggleMode}>
            {isSignupMode ? 'Login' : 'Sign up'}
          </button>
        </p>

        <form onSubmit={handleSubmit} className="fd-login-form">
          <div className="fd-login-provider-pill">
            <Cloud size={13} />
            <span>IBM App ID Cloud Directory</span>
          </div>

          <label className="fd-login-field" htmlFor="fd-login-email">
            <span className="fd-login-icon" aria-hidden="true">
              <Mail size={14} />
            </span>
            <input
              id="fd-login-email"
              type="email"
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="fd-login-input"
              required
              autoComplete="email"
            />
          </label>

          <label className="fd-login-field" htmlFor="fd-login-password">
            <span className="fd-login-icon" aria-hidden="true">
              <Lock size={14} />
            </span>
            <input
              id="fd-login-password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="fd-login-input fd-login-input-password"
              required
              autoComplete={isSignupMode ? 'new-password' : 'current-password'}
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              className="fd-login-see-password"
              aria-label={showPassword ? 'Hide password' : 'See password'}
            >
              {showPassword ? <EyeOff size={12} /> : <Eye size={12} />}
              <span>{showPassword ? 'Hide' : 'See'}</span>
            </button>
          </label>

          {isSignupMode ? (
            <label className="fd-login-field" htmlFor="fd-login-confirm-password">
              <span className="fd-login-icon" aria-hidden="true">
                <Lock size={14} />
              </span>
              <input
                id="fd-login-confirm-password"
                type={showPassword ? 'text' : 'password'}
                placeholder="Confirm password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="fd-login-input"
                required
                autoComplete="new-password"
              />
            </label>
          ) : null}

          {error ? <div className="fd-login-error">{error}</div> : null}

          <button type="submit" disabled={loading} className="fd-login-submit">
            {loading ? <Loader2 size={16} className="fd-spin" /> : (isSignupMode ? 'Create Cloud Account' : 'Login with Cloud Directory')}
          </button>

          <div className="fd-login-divider" aria-hidden="true">
            <span />
            <p>Or</p>
            <span />
          </div>

          <button
            type="button"
            className="fd-login-google-btn"
            onClick={startGoogleAuth}
          >
            <GoogleLogo />
            <span>{isSignupMode ? 'Sign up with Google' : 'Continue with Google'}</span>
          </button>
        </form>
      </section>
    </div>
  )
}

export default LoginPage
