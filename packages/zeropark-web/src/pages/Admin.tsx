import React, { useState, useEffect } from 'react';
import { ShieldAlert, Users, CheckCircle, AlertCircle } from 'lucide-react';
import { getToken, API_BASE } from '../api';

interface UserData {
  id: string;
  email: string;
  full_name: string | null;
  provider: string;
  role: string;
  is_active: boolean;
}

const Admin: React.FC = () => {
  const [users, setUsers] = useState<UserData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    setIsLoading(true);
    setErrorMsg('');
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/v1/admin/users`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (res.ok) {
        setUsers(await res.json());
      } else if (res.status === 403) {
        setErrorMsg("Access Denied: You do not have administrator privileges.");
      } else {
        setErrorMsg("Failed to load user data.");
      }
    } catch (err: any) {
      setErrorMsg(`Network error: ${err.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRoleChange = async (userId: string, newRole: string) => {
    setErrorMsg('');
    setSuccessMsg('');
    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/v1/admin/users/${userId}/role`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ role: newRole })
      });
      
      if (res.ok) {
        setSuccessMsg(`Role updated to ${newRole}`);
        setUsers(prev => prev.map(u => u.id === userId ? { ...u, role: newRole } : u));
        setTimeout(() => setSuccessMsg(''), 3000);
      } else if (res.status === 403) {
        setErrorMsg("Access Denied: You do not have administrator privileges.");
      } else {
        setErrorMsg("Failed to update user role.");
      }
    } catch (err: any) {
      setErrorMsg(`Network error: ${err.message}`);
    }
  };

  if (isLoading) {
    return <div style={{ padding: '2rem' }}>Loading users...</div>;
  }

  if (errorMsg && errorMsg.includes("Access Denied")) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '60vh', color: 'var(--text-secondary)' }}>
        <ShieldAlert size={64} style={{ color: '#ef4444', marginBottom: '1rem' }} />
        <h2 style={{ fontSize: '1.5rem', fontWeight: '700', marginBottom: '0.5rem', color: 'var(--text-primary)' }}>Access Denied</h2>
        <p>{errorMsg}</p>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', paddingBottom: '4rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
        <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #f43f5e, #fb923c)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Users size={24} />
        </div>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: '700' }}>User Management</h1>
          <p style={{ color: 'var(--text-secondary)' }}>Manage access controls and roles across the workspace.</p>
        </div>
      </div>

      {errorMsg && (
        <div style={{ padding: '1rem', borderRadius: 'var(--radius-md)', backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.2)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <AlertCircle size={20} /> {errorMsg}
        </div>
      )}

      {successMsg && (
        <div style={{ padding: '1rem', borderRadius: 'var(--radius-md)', backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#10b981', border: '1px solid rgba(16, 185, 129, 0.2)', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <CheckCircle size={20} /> {successMsg}
        </div>
      )}

      <div className="glass-panel" style={{ borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: 'rgba(0,0,0,0.02)', borderBottom: '1px solid var(--border-color)' }}>
              <th style={{ padding: '1rem 1.5rem', fontWeight: '600', color: 'var(--text-secondary)', fontSize: '0.8rem', textTransform: 'uppercase' }}>Email</th>
              <th style={{ padding: '1rem 1.5rem', fontWeight: '600', color: 'var(--text-secondary)', fontSize: '0.8rem', textTransform: 'uppercase' }}>Name</th>
              <th style={{ padding: '1rem 1.5rem', fontWeight: '600', color: 'var(--text-secondary)', fontSize: '0.8rem', textTransform: 'uppercase' }}>Provider</th>
              <th style={{ padding: '1rem 1.5rem', fontWeight: '600', color: 'var(--text-secondary)', fontSize: '0.8rem', textTransform: 'uppercase' }}>Status</th>
              <th style={{ padding: '1rem 1.5rem', fontWeight: '600', color: 'var(--text-secondary)', fontSize: '0.8rem', textTransform: 'uppercase' }}>Role</th>
            </tr>
          </thead>
          <tbody>
            {users.map(user => (
              <tr key={user.id} style={{ borderBottom: '1px solid var(--border-color)' }}>
                <td style={{ padding: '1rem 1.5rem', fontWeight: '500' }}>{user.email}</td>
                <td style={{ padding: '1rem 1.5rem', color: 'var(--text-secondary)' }}>{user.full_name || '-'}</td>
                <td style={{ padding: '1rem 1.5rem' }}>
                  <span style={{ padding: '0.25rem 0.5rem', borderRadius: '4px', backgroundColor: 'var(--bg-color)', fontSize: '0.8rem', border: '1px solid var(--border-color)' }}>
                    {user.provider}
                  </span>
                </td>
                <td style={{ padding: '1rem 1.5rem' }}>
                  <span style={{ color: user.is_active ? '#10b981' : '#ef4444', fontSize: '0.9rem', fontWeight: '500' }}>
                    {user.is_active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td style={{ padding: '1rem 1.5rem' }}>
                  <select 
                    value={user.role} 
                    onChange={(e) => handleRoleChange(user.id, e.target.value)}
                    style={{ 
                      padding: '0.5rem', 
                      borderRadius: 'var(--radius-sm)', 
                      border: '1px solid var(--border-color)', 
                      backgroundColor: 'var(--bg-color)', 
                      color: 'var(--text-primary)',
                      outline: 'none',
                      cursor: 'pointer'
                    }}
                  >
                    <option value="user">User</option>
                    <option value="admin">Admin</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {users.length === 0 && (
          <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>No users found.</div>
        )}
      </div>
    </div>
  );
};

export default Admin;
