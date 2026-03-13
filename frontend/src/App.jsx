import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useCallback } from 'react'
import Login from './pages/Login'
import SignUp from './pages/SignUp'
import Chat from './pages/Chat'
import Layout from './components/Layout'

import AdminDashboard from './pages/AdminDashboard'

function App() {
  const [user, setUser] = useState(null)

  const login = useCallback((userData) => {
    setUser(userData)
    localStorage.setItem('senior_voice_user', JSON.stringify(userData))
  }, [])

  const handleUpdateUser = useCallback((updatedUserData) => {
    setUser(updatedUserData)
    localStorage.setItem('senior_voice_user', JSON.stringify(updatedUserData))
  }, [])

  const logout = useCallback(() => {
    setUser(null)
    localStorage.removeItem('senior_voice_user')
  }, [])

  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login onLogin={login} />} />
      <Route path="/signup" element={user ? <Navigate to="/" replace /> : <SignUp onSignUp={login} />} />
      <Route
        path="/"
        element={
          user ? (
            <Layout user={user} onLogout={logout} onUpdateUser={handleUpdateUser}>
              {user.role === 'admin' ? <AdminDashboard /> : <Chat user={user} />}
            </Layout>
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
      <Route path="*" element={<Navigate to={user ? '/' : '/login'} replace />} />
    </Routes>
  )
}

export default App
