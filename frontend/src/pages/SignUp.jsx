import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { GoogleLogin } from '@react-oauth/google'
import './Auth.css'

export default function SignUp({ onSignUp }) {
  const navigate = useNavigate()
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  // OTP States
  const [showOtpPrompt, setShowOtpPrompt] = useState(false)
  const [otp, setOtp] = useState('')
  const [registeredEmail, setRegisteredEmail] = useState('')

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!firstName.trim() || !lastName.trim() || !phone.trim() || !email.trim() || !password || !confirmPassword) {
      setError('Please fill in all fields.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters.')
      return
    }
    setLoading(true)
    try {
      const response = await fetch("http://localhost:8000/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          phone_number: parseInt(phone.trim(), 10),
          email: email.trim(),
          password: password
        })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Sign up failed.');
      }

      // OTP Sent successfully
      setRegisteredEmail(email.trim())
      setShowOtpPrompt(true)

    } catch (err) {
      setError(err.message || 'Sign up failed.')
    } finally {
      setLoading(false)
    }
  }

  const handleOtpSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!otp.trim()) {
      setError('Please enter the OTP.')
      return
    }

    setLoading(true)
    try {
      const response = await fetch("http://localhost:8000/verify-otp", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          email: registeredEmail,
          otp: otp.trim()
        })
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || 'Verification failed.');
      }

      // Log in directly after verifying
      onSignUp({
        email: data.email,
        name: `${data.first_name} ${data.last_name}`,
        username: data.username,
        role: data.role,
        profile_image: data.profile_image
      })
      navigate('/', { replace: true })

    } catch (err) {
      setError(err.message || 'Verification failed.')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleSuccess = async (credentialResponse) => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch('http://localhost:8000/google-login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          token: credentialResponse.credential,
          login_type: "signup"
        }),
      })
      const data = await res.json()
      if (!res.ok) {
        throw new Error(data.detail || 'Google sign up failed.')
      }

      // Removed redirect required phone block
      onSignUp({
        email: data.email,
        name: `${data.first_name} ${data.last_name}`,
        username: data.username,
        role: data.role,
        profile_image: data.profile_image
      })
      navigate('/', { replace: true })
    } catch (err) {
      setError(err.message || 'Google sign up failed.')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleError = () => {
    setError('Google Sign Up was unsuccessful. Try again later.')
  }

  if (showOtpPrompt) {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 className="auth-title">Verify Email</h1>
          <p className="auth-subtitle">We sent a verification code to {registeredEmail}.</p>
          <form className="auth-form" onSubmit={handleOtpSubmit}>
            {error && <div className="auth-error">{error}</div>}
            <label className="auth-label">
              One Time Password (OTP)
              <input
                type="text"
                className="auth-input"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                placeholder="Enter 6-digit OTP"
                autoComplete="one-time-code"
                disabled={loading}
              />
            </label>
            <button type="submit" className="auth-submit" disabled={loading}>
              {loading ? 'Verifying…' : 'Verify Account'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1 className="auth-title">Conversational AI</h1>
        <p className="auth-subtitle">Create your account</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          {error && <div className="auth-error">{error}</div>}

          <div className="google-login-container">
            <GoogleLogin
              onSuccess={handleGoogleSuccess}
              onError={handleGoogleError}
              useOneTap
              text="signup_with"
            />
          </div>

          <div className="auth-divider">
            <span>or sign up with email</span>
          </div>

          <div className="auth-row">
            <label className="auth-label">
              First Name
              <input
                type="text"
                className="auth-input"
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder="First"
                autoComplete="given-name"
                disabled={loading}
              />
            </label>
            <label className="auth-label">
              Last Name
              <input
                type="text"
                className="auth-input"
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="Last"
                autoComplete="family-name"
                disabled={loading}
              />
            </label>
          </div>
          <label className="auth-label">
            Phone Number
            <input
              type="text"
              className="auth-input"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="e.g. 1234567890"
              autoComplete="tel"
              disabled={loading}
            />
          </label>
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
              autoComplete="new-password"
              disabled={loading}
            />
          </label>
          <label className="auth-label">
            Confirm password
            <input
              type="password"
              className="auth-input"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="new-password"
              disabled={loading}
            />
          </label>
          <button type="submit" className="auth-submit" disabled={loading}>
            {loading ? 'Creating account…' : 'Sign up'}
          </button>
        </form>
        <p className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
