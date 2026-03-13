import React, { useState, useEffect } from 'react';
import { FaTrash, FaUserShield } from 'react-icons/fa';
import './Chat.css'; // Just reusing your styles for now
import './AdminDashboard.css';

export default function AdminDashboard({ user }) {
    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        fetchUsers();
    }, []);

    const fetchUsers = async () => {
        setLoading(true);
        setError('');
        try {
            const response = await fetch('http://localhost:8000/admin/users');
            if (!response.ok) {
                throw new Error('Failed to fetch users');
            }
            const data = await response.json();
            setUsers(data.users || []);
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleDeleteUser = async (emailToDelete) => {
        if (!window.confirm(`Are you sure you want to permanently delete user ${emailToDelete}?`)) {
            return;
        }

        try {
            const response = await fetch(`http://localhost:8000/admin/users/${emailToDelete}`, {
                method: 'DELETE'
            });

            if (!response.ok) {
                const data = await response.json();
                throw new Error(data.detail || 'Failed to delete user');
            }

            // Remove user from state beautifully without refreshing the whole page
            setUsers(prevUsers => prevUsers.filter(u => u.email !== emailToDelete));

        } catch (err) {
            alert(err.message);
        }
    };
    return (
        <div className="chat-page">
            <div className="chat-welcome" style={{ marginTop: '2rem' }}>
                <h2 className="chat-welcome-title">Admin Dashboard</h2>
                <p className="chat-welcome-subtitle">Welcome back, Administrator.</p>

                <div style={{
                    marginTop: '2rem',
                    width: '100%',
                    maxWidth: '500px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '1rem'
                }}>
                    {/* Top Row Stats */}
                    <div style={{ display: 'flex', gap: '1rem' }}>
                        <div style={{ flex: 1, padding: '1.5rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', textAlign: 'center' }}>
                            <h3 style={{ fontSize: '2rem', color: 'var(--accent)', marginBottom: '0.5rem' }}>{loading ? '--' : users.length}</h3>
                            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Total Registered Users</p>
                        </div>

                        <div style={{ flex: 1, padding: '1.5rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', textAlign: 'center' }}>
                            <h3 style={{ fontSize: '2rem', color: 'var(--accent)', marginBottom: '0.5rem' }}>--</h3>
                            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>Active Chats Today</p>
                        </div>
                    </div>

                    {/* System Status Table */}
                    <div style={{ padding: '1.5rem', background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                        <h4 style={{ marginBottom: '1rem', color: 'var(--text-primary)' }}>System Status</h4>

                        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem 0', borderBottom: '1px solid var(--border)' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Cloud LLM Engine</span>
                            <span style={{ color: 'var(--success)', fontWeight: 'bold' }}>Online</span>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem 0', borderBottom: '1px solid var(--border)' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Qdrant (Vector DB)</span>
                            <span style={{ color: 'var(--success)', fontWeight: 'bold' }}>Online</span>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem 0' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>PostgreSQL</span>
                            <span style={{ color: 'var(--success)', fontWeight: 'bold' }}>Online</span>
                        </div>
                    </div>
                </div>

                {/* User List Table */}
                <div style={{ marginTop: '3rem', width: '100%', maxWidth: '800px' }}>
                    <h3 style={{ color: 'var(--text-primary)', marginBottom: '1rem', borderBottom: '2px solid var(--border)', paddingBottom: '0.5rem' }}>
                        User Management
                    </h3>

                    {loading ? (
                        <p style={{ color: 'var(--text-muted)' }}>Loading users...</p>
                    ) : error ? (
                        <p style={{ color: 'var(--error)' }}>{error}</p>
                    ) : users.length === 0 ? (
                        <p style={{ color: 'var(--text-muted)' }}>No users found.</p>
                    ) : (
                        <div className="admin-table-container">
                            <table className="admin-table">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Email</th>
                                        <th>Role</th>
                                        <th>Verified</th>
                                        <th>Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {users.map(u => (
                                        <tr key={u.email}>
                                            <td>{u.first_name} {u.last_name} <br /><small className="text-muted">@{u.username}</small></td>
                                            <td>{u.email}</td>
                                            <td>
                                                {u.role === 'admin' ? (
                                                    <span className="badge badge-admin"><FaUserShield /> Admin</span>
                                                ) : (
                                                    <span className="badge badge-user">User</span>
                                                )}
                                            </td>
                                            <td>
                                                {u.is_verified ? (
                                                    <span style={{ color: 'var(--success)' }}>Yes</span>
                                                ) : (
                                                    <span style={{ color: 'var(--error)' }}>No</span>
                                                )}
                                            </td>
                                            <td>
                                                {(u.role !== 'admin' && u.email !== user?.email) ? (
                                                    <button
                                                        onClick={() => handleDeleteUser(u.email)}
                                                        className="admin-delete-btn"
                                                        title="Delete User"
                                                    >
                                                        <FaTrash />
                                                    </button>
                                                ) : (
                                                    <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>N/A</span>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

            </div>
        </div>
    );
}
