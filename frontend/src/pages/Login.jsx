import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { GoogleLogin } from '@react-oauth/google'
import './Auth.css'

export default function Login({ onLogin }) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPhonePrompt, setShowPhonePrompt] = useState(false)
  const [phoneNumber, setPhoneNumber] = useState('')
  const [googleData, setGoogleData] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!email.trim() || !password) {
      setError('Please enter email and password.')
      return
    }
    setLoading(true)
    try {
      const response = await fetch("http://localhost:8000/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          email: email.trim(),
          password: password
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Login failed.');
      }

      onLogin({
        email: data.email,
        name: `${data.first_name} ${data.last_name}`,
        username: data.username,
        role: data.role,
        profile_image: data.profile_image
      })
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'Login failed.')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSuccess = async (credentialResponse) => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch("http://localhost:8000/google-login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          token: credentialResponse.credential
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Google Login failed.');
      }

      // Log in directly
      onLogin({
        email: data.email,
        name: `${data.first_name} ${data.last_name}`,
        username: data.username,
        role: data.role,
        profile_image: data.profile_image
      })
      navigate('/', { replace: true })

    } catch (err) {
      setError(err.message || 'Google Login failed.')
    } finally {
      setLoading(false)
    }
  }

  const handlePhoneSubmit = async (e) => {
    e.preventDefault();
    if (!phoneNumber.trim()) {
      setError('Please enter a phone number.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const response = await fetch("http://localhost:8000/update-google-phone", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          email: googleData.email,
          phone: phoneNumber.trim()
        })
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to update phone number.');
      }

      onLogin(googleData);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err.message || 'Phone update failed.');
    } finally {
      setLoading(false);
    }
  }

  // Phone prompt removed

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Conversational AI</h1>
        <p className="auth-subtitle">Sign in to continue</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          {error && <div className="auth-error">{error}</div>}
          <label className="auth-label">
            Email
            <input
              type="email"
              className="auth-input"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              disabled={loading}
            />
          </label>
          <label className="auth-label">
            Password
            <input
              type="password"
              className="auth-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
              disabled={loading}
            />
          </label>
          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="auth-divider">
          <span>OR</span>
        </div>

        <div className="google-login-container" style={{ display: 'flex', justifyContent: 'center', margin: '20px 0' }}>
          <GoogleLogin
            onSuccess={handleGoogleSuccess}
            onError={() => {
              setError('Google Login failed.');
            }}
            useOneTap
          />
        </div>

        <p className="auth-footer">
          Don't have an account? <Link to="/signup">Sign up</Link>
        </p>
      </div>
    </div>
  )
}
