import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, X, Compass, Activity, Trash2 } from 'lucide-react';
import { API_BASE, authFetch, isAdmin } from '../api';
import { StatsWidget } from '../components/widgets/StatsWidget';

interface AppInfo {
  id: string;
  name: string;
  mode: string;
  description: string | null;
  published?: boolean;
  created_at?: string | null;
}

interface BackendMode {
  primary: string;
  pipeline: string[];
  description: string;
  available?: boolean;
}

const Dashboard: React.FC = () => {
  const navigate = useNavigate();
  const [apps, setApps] = useState<AppInfo[]>([]);
  const [modes, setModes] = useState<Record<string, BackendMode>>({});
  
  // Modal states
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [appName, setAppName] = useState('');
  const [selectedMode, setSelectedMode] = useState('');

  useEffect(() => {

    // 2. Fetch Available Modes (Templates)
    const fetchModes = async () => {
      try {
        const res = await fetch(`${API_BASE}/modes`);
        if(res.ok) {
          const data = await res.json();
          setModes(data.modes);
          // default to the first mode this deployment can actually serve
          const firstAvailable = Object.keys(data.modes).find(
            (k) => data.modes[k].available !== false
          );
          if (firstAvailable) setSelectedMode(firstAvailable);
        }
      } catch (err) {
        console.error(err);
      }
    };

    // 3. Load apps from the SERVER registry (admin builds, everyone uses)
    fetchApps();
    fetchModes();
  }, []);

  const fetchApps = async () => {
    try {
      const res = await authFetch('/api/v1/apps');
      if (res.ok) setApps((await res.json()).apps);
    } catch (err) {
      console.error(err);
    }
  };

  const handleCreateApp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appName || !selectedMode) return;
    try {
      const res = await authFetch('/api/v1/apps', {
        method: 'POST',
        body: JSON.stringify({
          name: appName,
          mode: selectedMode,
          description: modes[selectedMode]?.description || 'Custom Agent Workspace',
          published: true,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        alert(err?.error?.message || err?.detail || '에이전트 생성에 실패했습니다.');
        return;
      }
      await fetchApps();
    } catch (err) {
      console.error(err);
    }
    // Reset modal
    setAppName('');
    setIsModalOpen(false);
  };

  const handleDeleteApp = async (e: React.MouseEvent, appId: string) => {
    e.stopPropagation(); // don't navigate into the app being deleted
    const target = apps.find(a => a.id === appId);
    if (!window.confirm(`'${target?.name ?? appId}' 에이전트를 삭제할까요? 모든 사용자에게서 사라집니다.`)) return;
    const res = await authFetch(`/api/v1/apps/${appId}`, { method: 'DELETE' });
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      alert(err?.error?.message || err?.detail || '삭제 권한이 없습니다.');
      return;
    }
    await fetchApps();
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
        {isAdmin() && (
          <button
            onClick={() => setIsModalOpen(true)}
            className="btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 1.5rem', fontSize: '1rem' }}
          >
            <Plus size={20} /> Create Agent
          </button>
        )}
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
              <div style={{ position: 'absolute', top: '1rem', right: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
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
                {isAdmin() && (
                <button
                  onClick={(e) => handleDeleteApp(e, app.id)}
                  title="에이전트 삭제 (모든 사용자에게서 제거됨)"
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    width: '28px', height: '28px', borderRadius: '8px',
                    color: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.08)',
                    border: '1px solid rgba(239, 68, 68, 0.25)', cursor: 'pointer'
                  }}
                  onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.18)'}
                  onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.08)'}
                >
                  <Trash2 size={15} />
                </button>
                )}
              </div>

              <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #10b981, #059669)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Activity size={24} />
              </div>
              <div>
                <h3 style={{ fontSize: '1.2rem', fontWeight: '700', marginBottom: '0.25rem', paddingRight: '100px' }}>{app.name}</h3>
                <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                  {app.mode}{app.created_at ? ` • Created ${new Date(app.created_at).toLocaleDateString()}` : ''}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Stats Section */}
      <div style={{ marginTop: '3rem', maxWidth: '500px' }}>
        <StatsWidget />
      </div>

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
                  {Object.entries(modes).map(([modeId, modeData]) => {
                    const unavailable = modeData.available === false;
                    return (
                    <label
                      key={modeId}
                      style={{
                        display: 'flex', alignItems: 'flex-start', gap: '1rem',
                        padding: '1rem', borderRadius: 'var(--radius-md)',
                        border: `1px solid ${selectedMode === modeId ? 'var(--primary-color)' : 'var(--border-color)'}`,
                        backgroundColor: selectedMode === modeId ? 'rgba(37, 99, 235, 0.05)' : 'transparent',
                        cursor: unavailable ? 'not-allowed' : 'pointer',
                        opacity: unavailable ? 0.45 : 1,
                        transition: 'all 0.2s ease'
                      }}
                    >
                      <input
                        type="radio"
                        name="mode"
                        value={modeId}
                        checked={selectedMode === modeId}
                        disabled={unavailable}
                        onChange={() => setSelectedMode(modeId)}
                        style={{ marginTop: '0.25rem' }}
                      />
                      <div>
                        <div style={{ fontWeight: '600', marginBottom: '0.25rem' }}>
                          {modeId}
                          {unavailable && <span style={{ marginLeft: '0.5rem', fontSize: '0.7rem', color: 'var(--text-secondary)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.1rem 0.4rem' }}>미구성</span>}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{modeData.description}</div>
                      </div>
                    </label>
                    );
                  })}
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
