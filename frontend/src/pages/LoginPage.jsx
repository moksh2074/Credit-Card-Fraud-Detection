import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Mail,
  Lock,
  Loader2,
  Eye,
  EyeOff,
  Fingerprint,
  ShieldCheck,
  ScanFace
} from 'lucide-react'
import axios from 'axios'
import { useAuthStore } from '../store/useAuthStore'

const authOptions = [
  { id: 'fingerprint', label: 'Fingerprint', Icon: Fingerprint },
  { id: 'shield', label: 'Shield Access', Icon: ShieldCheck },
  { id: 'face', label: 'Face Scan', Icon: ScanFace }
]

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

  const toggleMode = () => {
    setIsSignupMode((prev) => !prev)
    setError('')
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

        try {
          await axios.post('/api/v1/auth/register', {
            email: normalizedEmail,
            password: normalizedPassword,
            role: 'admin',
            org_id: 'org_001'
          })
        } catch (registerErr) {
          const detail = registerErr?.response?.data?.detail
          if (detail !== 'Email already registered') {
            throw registerErr
          }
        }
      }

      const response = await axios.post('/api/v1/auth/login', {
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
            {loading ? <Loader2 size={16} className="fd-spin" /> : (isSignupMode ? 'Sign Up & Login' : 'Login')}
          </button>

          <div className="fd-login-divider" aria-hidden="true">
            <span />
            <p>Or</p>
            <span />
          </div>

          <div className="fd-login-alt-grid">
            {authOptions.map(({ id, label, Icon }) => (
              <button key={id} type="button" className="fd-login-alt-btn" aria-label={label}>
                <Icon size={15} />
              </button>
            ))}
          </div>
        </form>
      </section>
    </div>
  )
}

export default LoginPage
