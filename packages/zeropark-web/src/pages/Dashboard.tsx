import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getToken } from '../api';
import { Plus, X, Bot, Zap, Filter, Compass, Activity } from 'lucide-react';

interface AppInfo {
  id: string;
  name: string;
  mode: string;
  description: string;
  createdAt: string;
}

interface BackendMode {
  primary: string;
  pipeline: string[];
  description: string;
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState<any>(null);
  const [apps, setApps] = useState<AppInfo[]>([]);
  const [modes, setModes] = useState<Record<string, BackendMode>>({});
  
  // Modal states
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [appName, setAppName] = useState('');
  const [selectedMode, setSelectedMode] = useState('');

  useEffect(() => {
    // 1. Fetch Backend Stats
    const fetchStats = async () => {
      try {
        const token = getToken();
        if(!token) return;
        const res = await fetch('http://localhost:8000/api/v1/admin/stats', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if(res.ok) setStats(await res.json());
      } catch (err) {
        console.error(err);
      }
    };

    // 2. Fetch Available Modes (Templates)
    const fetchModes = async () => {
      try {
        const res = await fetch('http://localhost:8000/modes');
        if(res.ok) {
          const data = await res.json();
          setModes(data.modes);
          if (Object.keys(data.modes).length > 0) {
            setSelectedMode(Object.keys(data.modes)[0]);
          }
        }
      } catch (err) {
        console.error(err);
      }
    };

    // 3. Load user apps from localStorage
    const savedApps = localStorage.getItem('zp_apps');
    if (savedApps) {
      setApps(JSON.parse(savedApps));
    }

    fetchStats();
    fetchModes();
  }, []);

  const handleCreateApp = (e: React.FormEvent) => {
    e.preventDefault();
    if (!appName || !selectedMode) return;

    const newApp: AppInfo = {
      id: `app_${Date.now()}`,
      name: appName,
      mode: selectedMode,
      description: modes[selectedMode]?.description || 'Custom Agent Workspace',
      createdAt: new Date().toISOString()
    };

    const updatedApps = [...apps, newApp];
    setApps(updatedApps);
    localStorage.setItem('zp_apps', JSON.stringify(updatedApps));
    
    // Reset modal
    setAppName('');
    setIsModalOpen(false);
  };

  return (
    <div style={{ paddingBottom: '4rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h1 style={{ fontSize: '2rem', fontWeight: '800', marginBottom: '0.5rem', background: 'linear-gradient(to right, var(--primary-color), #a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Welcome back, Admin
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: '1.1rem' }}>Manage your AI Agents and automated workflows.</p>
        </div>
        <button 
          onClick={() => setIsModalOpen(true)}
          className="btn-primary" 
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1.5rem', fontSize: '1rem' }}
        >
          <Plus size={20} /> Create Agent
        </button>
      </div>

      <div>
        <h2 style={{ fontSize: '1.25rem', fontWeight: '700', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Compass size={24} style={{ color: 'var(--primary-color)' }} /> Client Agents
        </h2>
        
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
          gap: '1.5rem'
        }}>
          {apps.map(app => (
            <div 
              key={app.id}
              onClick={() => {
                if (app.mode.toLowerCase().includes('workflow') || app.name.toLowerCase().includes('analyzer')) {
                  navigate(`/dashboard/workflow/${app.id}`);
                } else {
                  navigate(`/dashboard/app/${app.id}`);
                }
              }}
              style={{
                padding: '1.5rem', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-sm)',
                cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: '1rem',
                border: '1px solid var(--border-color)', position: 'relative'
              }}
            >
              <div style={{ position: 'absolute', top: '1rem', right: '1rem', display: 'flex', gap: '0.5rem' }}>
                <span style={{ 
                  padding: '0.25rem 0.5rem', 
                  backgroundColor: 'var(--bg-color)', 
                  border: '1px solid var(--border-color)', 
                  borderRadius: '16px', 
                  fontSize: '0.75rem', 
                  color: 'var(--text-secondary)' 
                }}>
                  {app.mode}
                </span>
              </div>

              <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #10b981, #059669)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Activity size={24} />
              </div>
              <div>
                <h3 style={{ fontSize: '1.2rem', fontWeight: '700', marginBottom: '0.25rem', paddingRight: '100px' }}>{app.name}</h3>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {app.mode} • Created {new Date(app.createdAt).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Stats Section */}
      {stats && (
        <div style={{ marginTop: '3rem' }}>
          <h2 style={{ fontSize: '1.2rem', fontWeight: '600', marginBottom: '1rem' }}>System Overview</h2>
          <div style={{ display: 'flex', gap: '1.5rem', flexWrap: 'wrap' }}>
            <div className="glass-panel" style={{ flex: '1 1 200px', padding: '1.5rem', borderRadius: 'var(--radius-md)' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Total Users</p>
              <h3 style={{ fontSize: '2rem', fontWeight: '700' }}>{stats.total_users}</h3>
            </div>
            <div className="glass-panel" style={{ flex: '1 1 200px', padding: '1.5rem', borderRadius: 'var(--radius-md)' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Google Logins</p>
              <h3 style={{ fontSize: '2rem', fontWeight: '700' }}>{stats.google_users}</h3>
            </div>
            <div className="glass-panel" style={{ flex: '1 1 200px', padding: '1.5rem', borderRadius: 'var(--radius-md)' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Available Templates</p>
              <h3 style={{ fontSize: '2rem', fontWeight: '700' }}>{Object.keys(modes).length}</h3>
            </div>
          </div>
        </div>
      )}

      {/* Create App Modal */}
      {isModalOpen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
          backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 50,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          backdropFilter: 'blur(4px)'
        }}>
          <div className="glass-panel" style={{
            width: '100%', maxWidth: '500px', padding: '2rem', borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-lg)', backgroundColor: 'var(--surface-color)', position: 'relative'
          }}>
            <button 
              onClick={() => setIsModalOpen(false)}
              style={{ position: 'absolute', top: '1.5rem', right: '1.5rem', color: 'var(--text-secondary)' }}
            >
              <X size={20} />
            </button>
            <h2 style={{ fontSize: '1.5rem', fontWeight: '700', marginBottom: '1.5rem' }}>Create New App</h2>
            
            <form onSubmit={handleCreateApp} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>App Name</label>
                <input 
                  type="text" 
                  value={appName}
                  onChange={(e) => setAppName(e.target.value)}
                  placeholder="e.g. Customer Support Bot"
                  style={{
                    width: '100%', padding: '0.75rem', borderRadius: 'var(--radius-md)',
                    border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)',
                    color: 'var(--text-primary)', outline: 'none'
                  }}
                  autoFocus
                  required
                />
              </div>

              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>App Template (Mode)</label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '200px', overflowY: 'auto' }}>
                  {Object.entries(modes).map(([modeId, modeData]) => (
                    <label 
                      key={modeId} 
                      style={{
                        display: 'flex', alignItems: 'flex-start', gap: '1rem',
                        padding: '1rem', borderRadius: 'var(--radius-md)',
                        border: `1px solid ${selectedMode === modeId ? 'var(--primary-color)' : 'var(--border-color)'}`,
                        backgroundColor: selectedMode === modeId ? 'rgba(37, 99, 235, 0.05)' : 'transparent',
                        cursor: 'pointer', transition: 'all 0.2s ease'
                      }}
                    >
                      <input 
                        type="radio" 
                        name="mode" 
                        value={modeId} 
                        checked={selectedMode === modeId}
                        onChange={() => setSelectedMode(modeId)}
                        style={{ marginTop: '0.25rem' }}
                      />
                      <div>
                        <div style={{ fontWeight: '600', marginBottom: '0.25rem' }}>{modeId}</div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{modeData.description}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '1rem' }}>
                <button type="button" onClick={() => setIsModalOpen(false)} className="btn-secondary">Cancel</button>
                <button type="submit" className="btn-primary" disabled={!appName.trim() || !selectedMode}>
                  Create Agent
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default Dashboard;
