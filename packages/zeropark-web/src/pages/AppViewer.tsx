import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Bot } from 'lucide-react';
import { VendorLayoutEngine } from '../components/VendorLayoutEngine';
import { authFetch } from '../api';

interface AppModel {
  id: string;
  name: string;
  mode: string;
  description: string;
}

const AppViewer: React.FC = () => {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  const [app, setApp] = useState<AppModel | null>(null);
  const [layoutConfig, setLayoutConfig] = useState<any>({
    type: 'default',
    widgets: [{ id: 'chat', position: 'main' }]
  });

  useEffect(() => {
    // Load app info from the server registry
    const fetchApp = async () => {
      try {
        const res = await authFetch(`/api/v1/apps/${appId}`);
        if (res.ok) setApp(await res.json());
      } catch (err) {
        console.error(err);
      }
    };
    fetchApp();

    // Load dynamic layout config from local profile
    const savedProfile = localStorage.getItem('zp_profile');
    if (savedProfile) {
      try {
        const profile = JSON.parse(savedProfile);
        if (profile.branding?.layout) {
          setLayoutConfig(profile.branding.layout);
        }
      } catch (err) {
        console.error("Failed to parse local profile layout", err);
      }
    }
  }, [appId]);

  if (!app) {
    return <div style={{ padding: '2rem' }}>App not found.</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 64px)', backgroundColor: 'var(--bg-color)', margin: '-2rem', overflow: 'hidden' }}>
      {/* Header */}
      <header style={{
        padding: '1rem 2rem',
        borderBottom: '1px solid var(--border-color)',
        backgroundColor: 'var(--surface-color)',
        display: 'flex',
        alignItems: 'center',
        gap: '1rem'
      }}>
        <button onClick={() => navigate('/dashboard')} style={{ color: 'var(--text-secondary)' }}>
          <ArrowLeft size={20} />
        </button>
        <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'var(--primary-color)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Bot size={18} />
        </div>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: '600' }}>{app.name}</h2>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Engine Mode: {app.mode}</span>
        </div>
      </header>

      {/* Dynamic Layout Engine Area */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <VendorLayoutEngine layout={layoutConfig} appId={appId} appMode={app.mode} />
      </div>
    </div>
  );
};

export default AppViewer;
