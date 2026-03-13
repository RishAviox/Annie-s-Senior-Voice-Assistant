import React, { useState, useEffect, useRef } from 'react';
import { FaUserCircle, FaTimes, FaEdit, FaSave, FaCamera } from 'react-icons/fa';
import './ProfileModal.css';

export default function ProfileModal({ user, onClose, onUpdateUser }) {
    const [profileData, setProfileData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [isEditing, setIsEditing] = useState(false);
    const [saving, setSaving] = useState(false);
    const [uploadingImage, setUploadingImage] = useState(false);
    const fileInputRef = useRef(null);

    // Form states
    const [formData, setFormData] = useState({
        first_name: '',
        last_name: '',
        phone: '',
        address1: '',
        address2: '',
        city: '',
        state: '',
        pincode: '',
        country: ''
    });

    useEffect(() => {
        fetchProfile();
    }, [user.email]);

    const fetchProfile = async () => {
        setLoading(true);
        setError('');
        try {
            const response = await fetch(`http://localhost:8000/profile/${user.email}`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to fetch profile');
            }

            const pData = data.data;
            setProfileData(pData);

            // Initialize form data with fetched profile
            setFormData({
                first_name: pData.first_name || '',
                last_name: pData.last_name || '',
                phone: pData.phone || '',
                address1: pData.address1 || '',
                address2: pData.address2 || '',
                city: pData.city || '',
                state: pData.state || '',
                pincode: pData.pincode || '',
                country: pData.country || ''
            });

        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleInputChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({
            ...prev,
            [name]: value
        }));
    };

    const handleImageUpload = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setUploadingImage(true);
        setError('');
        const uploadData = new FormData();
        uploadData.append('file', file);

        try {
            const response = await fetch(`http://localhost:8000/profile/${user.email}/image`, {
                method: 'POST',
                body: uploadData, // FormData shouldn't have Content-Type set manually; browser sets boundary
            });
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Failed to upload image');
            }

            setProfileData(prev => ({
                ...prev,
                profile_image: data.image_url
            }));

            // If we're lifting state up to App
            if (onUpdateUser) {
                onUpdateUser({
                    ...user,
                    profile_image: data.image_url
                });
            }
        } catch (err) {
            setError(err.message || 'Image upload failed');
        } finally {
            setUploadingImage(false);
        }
    };

    const handleSave = async (e) => {
        e.preventDefault();
        setSaving(true);
        setError('');

        try {
            const payload = {
                first_name: formData.first_name,
                last_name: formData.last_name,
                phone: formData.phone,
                address1: formData.address1,
                address2: formData.address2,
                city: formData.city,
                state: formData.state,
                pincode: formData.pincode ? parseInt(formData.pincode, 10) : null,
                country: formData.country
            };

            const response = await fetch(`http://localhost:8000/profile/${user.email}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || 'Failed to update profile');
            }

            // Update local profile state
            setProfileData({
                ...profileData,
                ...formData
            });

            // Update App level user state if name changed
            if (onUpdateUser) {
                onUpdateUser({
                    ...user,
                    name: `${formData.first_name} ${formData.last_name}`.trim(),
                });
            }

            setIsEditing(false);
        } catch (err) {
            setError(err.message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="profile-modal-overlay" onClick={onClose}>
            <div className="profile-modal" onClick={e => e.stopPropagation()}>

                {/* Header */}
                <div className="profile-modal-header">
                    <div className="profile-title">
                        <FaUserCircle size={24} />
                        <h2>User Profile</h2>
                    </div>
                    <button className="icon-btn close-btn" onClick={onClose}>
                        <FaTimes />
                    </button>
                </div>

                {/* Content */}
                <div className="profile-modal-content">
                    {loading ? (
                        <div className="profile-loading">Loading profile data...</div>
                    ) : error && !isEditing ? (
                        <div className="profile-error">{error}</div>
                    ) : (
                        <>
                            {/* Profile Image & Basic Info display */}
                            <div className="profile-banner">
                                <div className="profile-avatar-container" onClick={() => fileInputRef.current?.click()} title="Change Profile Picture">
                                    <div className={`profile-avatar ${uploadingImage ? 'uploading' : ''}`}>
                                        <img
                                            src={profileData?.profile_image || `https://ui-avatars.com/api/?name=${profileData?.first_name}+${profileData?.last_name}&background=1d4ed8&color=fff&size=128&rounded=true`}
                                            alt="User Avatar"
                                        />
                                        <div className="avatar-edit-overlay">
                                            <FaCamera />
                                        </div>
                                    </div>
                                    <input
                                        type="file"
                                        ref={fileInputRef}
                                        style={{ display: 'none' }}
                                        accept="image/*"
                                        onChange={handleImageUpload}
                                    />
                                </div>
                                {!isEditing && (
                                    <div className="profile-basic-info">
                                        <h3>{profileData?.first_name} {profileData?.last_name}</h3>
                                        <p className="profile-username">@{profileData?.username}</p>
                                        <span className="profile-role-badge">{user.role || 'User'}</span>
                                    </div>
                                )}
                                {!isEditing && (
                                    <button className="edit-profile-btn" onClick={() => setIsEditing(true)}>
                                        <FaEdit /> Edit Profile
                                    </button>
                                )}
                            </div>

                            {/* Error for the form */}
                            {error && isEditing && <div className="profile-error">{error}</div>}

                            {/* Form or Display View */}
                            {isEditing ? (
                                <form className="profile-form" onSubmit={handleSave}>

                                    <h4>Personal Details</h4>
                                    <div className="form-row">
                                        <label>
                                            First Name
                                            <input type="text" name="first_name" value={formData.first_name} onChange={handleInputChange} required />
                                        </label>
                                        <label>
                                            Last Name
                                            <input type="text" name="last_name" value={formData.last_name} onChange={handleInputChange} required />
                                        </label>
                                    </div>

                                    <div className="form-row">
                                        <label>
                                            Email (Read Only)
                                            <input type="email" value={profileData?.email || ''} disabled />
                                        </label>
                                        <label>
                                            Phone Number
                                            <input type="tel" name="phone" value={formData.phone} onChange={handleInputChange} />
                                        </label>
                                    </div>

                                    <h4>Address Details</h4>
                                    <label>
                                        Address Line 1
                                        <input type="text" name="address1" value={formData.address1} onChange={handleInputChange} />
                                    </label>
                                    <label>
                                        Address Line 2
                                        <input type="text" name="address2" value={formData.address2} onChange={handleInputChange} />
                                    </label>

                                    <div className="form-row">
                                        <label>
                                            City
                                            <input type="text" name="city" value={formData.city} onChange={handleInputChange} />
                                        </label>
                                        <label>
                                            State
                                            <input type="text" name="state" value={formData.state} onChange={handleInputChange} />
                                        </label>
                                    </div>

                                    <div className="form-row">
                                        <label>
                                            Pincode
                                            <input type="number" name="pincode" value={formData.pincode} onChange={handleInputChange} />
                                        </label>
                                        <label>
                                            Country
                                            <input type="text" name="country" value={formData.country} onChange={handleInputChange} />
                                        </label>
                                    </div>

                                    <div className="profile-form-actions">
                                        <button type="button" className="cancel-btn" onClick={() => setIsEditing(false)} disabled={saving}>
                                            Cancel
                                        </button>
                                        <button type="submit" className="save-btn" disabled={saving}>
                                            <FaSave /> {saving ? 'Saving...' : 'Save Changes'}
                                        </button>
                                    </div>
                                </form>
                            ) : (
                                <div className="profile-display">

                                    <div className="display-section">
                                        <h4>Contact Information</h4>
                                        <div className="display-grid">
                                            <div className="display-item">
                                                <span className="label">Email</span>
                                                <span className="value">{profileData?.email}</span>
                                            </div>
                                            <div className="display-item">
                                                <span className="label">Phone Number</span>
                                                <span className="value">{profileData?.phone || <i className="text-muted">Not provided</i>}</span>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="display-section">
                                        <h4>Address Information</h4>
                                        {profileData?.address1 ? (
                                            <div className="address-card">
                                                <p>{profileData.address1}</p>
                                                {profileData.address2 && <p>{profileData.address2}</p>}
                                                <p>{profileData.city}{profileData.state ? `, ${profileData.state}` : ''} {profileData.pincode}</p>
                                                <p>{profileData.country}</p>
                                            </div>
                                        ) : (
                                            <p className="no-data-msg">No address provided. Click 'Edit Profile' to add your address.</p>
                                        )}
                                    </div>

                                </div>
                            )}
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
