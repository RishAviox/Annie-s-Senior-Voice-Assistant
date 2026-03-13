import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { FaUserCircle } from 'react-icons/fa'
import ProfileModal from './ProfileModal'
import './Layout.css'

export default function Layout({ user, onLogout, onUpdateUser, children }) {
  const [showProfile, setShowProfile] = useState(false)

  return (
    <div className="layout">
      <header className="layout-header">
        <div className="layout-brand">
          <span className="layout-logo">Conversational AI</span>
        </div>
        <div className="layout-user">
          {user?.role === 'admin' && (
            <span style={{ color: '#d1b17d', fontWeight: 'bold', marginRight: '1rem', border: '1px solid #d1b17d', padding: '0.2rem 0.5rem', borderRadius: '4px' }}>
              ★ Admin Access
            </span>
          )}
          <span className="layout-email">{user?.email}</span>
          <button type="button" className="layout-profile-btn" onClick={() => setShowProfile(true)} title="View Profile">
            {user?.profile_image ? (
              <img src={user.profile_image} alt="Profile" className="layout-profile-img" />
            ) : (
              <FaUserCircle size={20} />
            )}
            <span>Profile</span>
          </button>
          <button type="button" className="layout-logout" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>
      <main className="layout-main">
        {children || <Outlet />}
      </main>

      {showProfile && (
        <ProfileModal
          user={user}
          onClose={() => setShowProfile(false)}
          onUpdateUser={onUpdateUser}
        />
      )}
    </div>
  )
}
