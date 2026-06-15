import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, X, Compass, Activity, Trash2, Pencil } from 'lucide-react';
import { API_BASE, authFetch, isAdmin } from '../api';
import { StatsWidget } from '../components/widgets/StatsWidget';

interface VariableDef {
  key: string;
  label: string;
  required?: boolean;
}

interface AppInfo {
  id: string;
  name: string;
  mode: string;
  description: string | null;
  system_prompt?: string | null;
  params?: Record<string, any>;
  published?: boolean;
  created_at?: string | null;
}

interface RagCollection {
  id: string;
  name: string;
  allowed_roles: string[];
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
  
  // Modal states (shared by create & edit)
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingAppId, setEditingAppId] = useState<string | null>(null);
  const [appName, setAppName] = useState('');
  const [selectedMode, setSelectedMode] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState('');
  const [variables, setVariables] = useState<VariableDef[]>([]);
  const [collectionIds, setCollectionIds] = useState<string[]>([]);

  // deployment options for the modal
  const [modelChoices, setModelChoices] = useState<string[]>([]);
  const [collections, setCollections] = useState<RagCollection[]>([]);

  const resetModal = () => {
    setEditingAppId(null);
    setAppName('');
    setSystemPrompt('');
    setModel('');
    setTemperature('');
    setVariables([]);
    setCollectionIds([]);
  };

  const openEditModal = (app: AppInfo) => {
    setEditingAppId(app.id);
    setAppName(app.name);
    setSelectedMode(app.mode);
    setSystemPrompt(app.system_prompt || '');
    setModel(app.params?.model || '');
    setTemperature(app.params?.temperature != null ? String(app.params.temperature) : '');
    setVariables(app.params?.variables || []);
    setCollectionIds(app.params?.collection_ids || []);
    setIsModalOpen(true);
  };

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

    // model choices for the agent modal (admin)
    const fetchProfile = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/profile`);
        if (res.ok) setModelChoices((await res.json()).models || []);
      } catch (err) {
        console.error(err);
      }
    };

    const fetchCollections = async () => {
      try {
        const res = await authFetch('/api/v1/rag/collections');
        if (res.ok) setCollections((await res.json()).collections || []);
      } catch (err) {
        console.error(err);
      }
    };

    // 3. Load apps from the SERVER registry (admin builds, everyone uses)
    fetchApps();
    fetchModes();
    fetchProfile();
    if (isAdmin()) fetchCollections();
  }, []);

  const fetchApps = async () => {
    try {
      const res = await authFetch('/api/v1/apps');
      if (res.ok) setApps((await res.json()).apps);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSubmitApp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!appName || !selectedMode) return;

    const params: Record<string, any> = {};
    if (model) params.model = model;
    if (temperature !== '' && !isNaN(Number(temperature))) params.temperature = Number(temperature);
    const validVariables = variables.filter(v => v.key.trim());
    if (validVariables.length) params.variables = validVariables;
    if (collectionIds.length) params.collection_ids = collectionIds;

    const payload = {
      name: appName,
      mode: selectedMode,
      description: modes[selectedMode]?.description || 'Custom Agent Workspace',
      system_prompt: systemPrompt || null,
      params,
      published: true,
    };

    try {
      const res = editingAppId
        ? await authFetch(`/api/v1/apps/${editingAppId}`, { method: 'PATCH', body: JSON.stringify(payload) })
        : await authFetch('/api/v1/apps', { method: 'POST', body: JSON.stringify(payload) });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        alert(err?.error?.message || err?.detail || '에이전트 저장에 실패했습니다.');
        return;
      }
      await fetchApps();
    } catch (err) {
      console.error(err);
    }
    resetModal();
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
                  if (isAdmin()) {
                    navigate(`/dashboard/app/${app.id}`);
                  } else {
                    window.open(`/app/${app.id}`, '_blank');
                  }
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
                <>
                <button
                  onClick={(e) => { e.stopPropagation(); openEditModal(app); }}
                  title="에이전트 편집"
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    width: '28px', height: '28px', borderRadius: '8px',
                    color: 'var(--primary-color)', backgroundColor: 'rgba(37, 99, 235, 0.08)',
                    border: '1px solid rgba(37, 99, 235, 0.25)', cursor: 'pointer'
                  }}
                >
                  <Pencil size={14} />
                </button>
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
                </>
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
              onClick={() => { resetModal(); setIsModalOpen(false); }}
              style={{ position: 'absolute', top: '1.5rem', right: '1.5rem', color: 'var(--text-secondary)' }}
            >
              <X size={20} />
            </button>
            <h2 style={{ fontSize: '1.5rem', fontWeight: '700', marginBottom: '1.5rem' }}>
              {editingAppId ? 'Edit Agent' : 'Create New App'}
            </h2>

            <form onSubmit={handleSubmitApp} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
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

              {/* persona + model parameters */}
              <div>
                <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem', fontWeight: '500' }}>
                  <span>System Prompt (페르소나, 변수는 {'{{key}}'})</span>
                  <button
                    type="button"
                    onClick={async () => {
                      const intent = window.prompt('이 에이전트가 무엇을 하길 원하나요? (한 줄)');
                      if (!intent) return;
                      const res = await authFetch('/api/v1/apps/enhance-prompt', {
                        method: 'POST', body: JSON.stringify({ intent })
                      });
                      if (res.ok) setSystemPrompt((await res.json()).prompt);
                      else alert('프롬프트 생성에 실패했습니다.');
                    }}
                    style={{ fontSize: '0.75rem', color: 'var(--primary-color)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '0.2rem 0.6rem', cursor: 'pointer' }}
                  >
                    ✨ 자동 생성
                  </button>
                </label>
                <textarea
                  rows={3}
                  value={systemPrompt}
                  onChange={(e) => setSystemPrompt(e.target.value)}
                  placeholder="예: 너는 {{name}}님을 돕는 {{product}} 전담 상담사다. 항상 존댓말을 쓴다."
                  style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', resize: 'vertical' }}
                />
              </div>

              <div style={{ display: 'flex', gap: '1rem' }}>
                <div style={{ flex: 2 }}>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>Model</label>
                  {modelChoices.length > 0 ? (
                    <select
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)' }}
                    >
                      <option value="">(배포 기본값)</option>
                      {modelChoices.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  ) : (
                    <input
                      type="text" value={model} onChange={(e) => setModel(e.target.value)}
                      placeholder="(배포 기본값)"
                      style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)' }}
                    />
                  )}
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>Temperature</label>
                  <input
                    type="number" min={0} max={2} step={0.1}
                    value={temperature}
                    onChange={(e) => setTemperature(e.target.value)}
                    placeholder="0.7"
                    style={{ width: '100%', padding: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)' }}
                  />
                </div>
              </div>

              {/* conversation variables collected from the user at chat start */}
              <div>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>대화 변수 (채팅 시작 시 사용자 입력 폼)</label>
                {variables.map((v, idx) => (
                  <div key={idx} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
                    <input
                      type="text" value={v.key} placeholder="key (예: name)"
                      onChange={(e) => setVariables(vs => vs.map((x, i) => i === idx ? { ...x, key: e.target.value } : x))}
                      style={{ flex: 1, padding: '0.5rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)' }}
                    />
                    <input
                      type="text" value={v.label} placeholder="라벨 (예: 성함)"
                      onChange={(e) => setVariables(vs => vs.map((x, i) => i === idx ? { ...x, label: e.target.value } : x))}
                      style={{ flex: 1, padding: '0.5rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)' }}
                    />
                    <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'flex', gap: '0.25rem', alignItems: 'center' }}>
                      <input
                        type="checkbox" checked={!!v.required}
                        onChange={(e) => setVariables(vs => vs.map((x, i) => i === idx ? { ...x, required: e.target.checked } : x))}
                      /> 필수
                    </label>
                    <button type="button" onClick={() => setVariables(vs => vs.filter((_, i) => i !== idx))} style={{ color: '#ef4444' }}>
                      <X size={16} />
                    </button>
                  </div>
                ))}
                <button
                  type="button" className="btn-secondary"
                  onClick={() => setVariables(vs => [...vs, { key: '', label: '', required: false }])}
                  style={{ fontSize: '0.85rem' }}
                >
                  + 변수 추가
                </button>
              </div>

              {/* knowledge scope: pin the agent to specific RAG collections */}
              {collections.length > 0 && (
                <div>
                  <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: '500' }}>지식 범위 (RAG 컬렉션 고정 — 미선택 시 사용자 권한 전체)</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                    {collections.map(c => {
                      const selected = collectionIds.includes(c.id);
                      return (
                        <button
                          key={c.id} type="button"
                          onClick={() => setCollectionIds(ids => selected ? ids.filter(i => i !== c.id) : [...ids, c.id])}
                          style={{
                            padding: '0.4rem 0.8rem', borderRadius: 'var(--radius-md)', fontSize: '0.85rem',
                            border: `1px solid ${selected ? 'var(--primary-color)' : 'var(--border-color)'}`,
                            backgroundColor: selected ? 'rgba(37, 99, 235, 0.08)' : 'var(--bg-color)',
                            color: selected ? 'var(--primary-color)' : 'var(--text-secondary)', cursor: 'pointer'
                          }}
                        >
                          {c.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem', marginTop: '1rem' }}>
                <button type="button" onClick={() => { resetModal(); setIsModalOpen(false); }} className="btn-secondary">Cancel</button>
                <button type="submit" className="btn-primary" disabled={!appName.trim() || !selectedMode}>
                  {editingAppId ? 'Save Changes' : 'Create Agent'}
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
