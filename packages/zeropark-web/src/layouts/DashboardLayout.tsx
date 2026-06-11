import React, { useEffect, useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, BookOpen, Settings, LogOut, Activity, ScrollText } from 'lucide-react';
import { removeToken, getToken, API_BASE } from '../api';

const SIDEBAR_WIDTH = '260px';
const HEADER_HEIGHT = '64px';

interface ProfileData {
  branding: {
    product_name: string;
    logo_url: string | null;
    primary_color: string;
    client_name: string | null;
    layout: {
      type: string;
      widgets: any[];
    };
  };
  environment: string;
  capabilities: string[];
  features: Record<string, boolean>;
}

const DashboardLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [profile, setProfile] = useState<ProfileData | null>(null);

  useEffect(() => {
    const fetchProfile = async () => {
      try {
        const token = getToken();
        if (!token) return;
        const res = await fetch(`${API_BASE}/api/v1/profile`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });
        if (res.ok) {
          const data: ProfileData = await res.json();
          setProfile(data);
          
          // Apply dynamic CSS variable injection
          if (data.branding.primary_color) {
            document.documentElement.style.setProperty('--primary-color', data.branding.primary_color);
            document.documentElement.style.setProperty('--primary-hover', `${data.branding.primary_color}dd`);
          }
          
          localStorage.setItem('zp_profile', JSON.stringify(data));
        }
      } catch (err) {
        console.error("Failed to fetch profile", err);
      }
    };

    fetchProfile();
  }, []);

  const handleLogout = () => {
    removeToken();
    navigate('/login');
  };

  const navItems = [
    { label: 'Apps', path: '/dashboard', icon: <LayoutDashboard size={20} /> },
    { label: 'Knowledge (RAG)', path: '/dashboard/knowledge', icon: <BookOpen size={20} /> },
    { label: 'Workflow Runs', path: '/dashboard/workflow-runs', icon: <ScrollText size={20} /> },
    { label: 'Admin Stats', path: '/dashboard/admin', icon: <Activity size={20} /> },
    { label: 'Settings', path: '/dashboard/settings', icon: <Settings size={20} /> },
  ];

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* Sidebar */}
      <aside style={{
        width: SIDEBAR_WIDTH,
        backgroundColor: 'var(--surface-color)',
        borderRight: '1px solid var(--border-color)',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {/* Logo Area */}
        <div style={{
          height: HEADER_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          padding: '0 1.5rem',
          borderBottom: '1px solid var(--border-color)',
          fontWeight: '700',
          fontSize: '1.2rem',
          gap: '0.75rem'
        }}>
          <div style={{
            width: '32px', height: '32px', background: 'var(--primary-color)',
            borderRadius: '8px', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center',
            overflow: 'hidden'
          }}>
            {profile?.branding.logo_url ? (
              <img src={profile.branding.logo_url} alt="logo" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              profile?.branding.client_name?.[0] || profile?.branding.product_name?.[0] || 'Z'
            )}
          </div>
          {profile?.branding.client_name ? `${profile.branding.client_name} AI` : (profile?.branding.product_name || 'Zeropark')}
        </div>

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '1.5rem 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          {navItems.map((item) => (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              style={{
                display: 'flex', alignItems: 'center', gap: '0.75rem',
                padding: '0.75rem 1rem',
                borderRadius: 'var(--radius-md)',
                backgroundColor: location.pathname === item.path ? 'rgba(37, 99, 235, 0.1)' : 'transparent',
                color: location.pathname === item.path ? 'var(--primary-color)' : 'var(--text-secondary)',
                fontWeight: location.pathname === item.path ? '600' : '500',
                textAlign: 'left',
                width: '100%',
                transition: 'all 0.2s ease'
              }}
              onMouseOver={(e) => {
                if(location.pathname !== item.path) {
                  e.currentTarget.style.backgroundColor = 'var(--bg-color)';
                }
              }}
              onMouseOut={(e) => {
                if(location.pathname !== item.path) {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }
              }}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>

        {/* User Profile Area */}
        <div style={{
          padding: '1rem',
          borderTop: '1px solid var(--border-color)'
        }}>
          <button 
            onClick={handleLogout}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.75rem', width: '100%',
              padding: '0.75rem 1rem', color: 'var(--text-secondary)', borderRadius: 'var(--radius-md)'
            }}
          >
            <LogOut size={20} />
            Log out
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        {/* Top Header */}
        <header style={{
          height: HEADER_HEIGHT,
          backgroundColor: 'var(--surface-color)',
          borderBottom: '1px solid var(--border-color)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          padding: '0 2rem'
        }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '1rem'
          }}>
            <span style={{ 
              fontSize: '0.75rem', 
              padding: '0.25rem 0.5rem', 
              backgroundColor: 'rgba(16, 185, 129, 0.1)', 
              color: 'var(--success-color)',
              borderRadius: 'var(--radius-full)',
              fontWeight: '600'
            }}>Active Workspace</span>
            <div style={{ width: '36px', height: '36px', borderRadius: '50%', backgroundColor: 'var(--primary-color)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              U
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main style={{ flex: 1, overflow: 'auto', padding: '2rem', backgroundColor: 'var(--bg-color)' }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
};

export default DashboardLayout;
