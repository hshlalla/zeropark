import React, { useEffect, useState } from 'react';
import { CheckCircle, XCircle, MinusCircle, RefreshCw, ScrollText } from 'lucide-react';
import { API_BASE } from '../api';

interface RunSummary {
  id: string;
  workflow_name: string | null;
  status: string;
  duration_ms: string | null;
  created_at: string | null;
}

interface NodeRun {
  node_id: string;
  node_type: string;
  status: string;
  duration_ms: number;
  output_preview: string;
  error: string | null;
}

const StatusIcon: React.FC<{ status: string }> = ({ status }) => {
  if (status === 'succeeded') return <CheckCircle size={16} style={{ color: '#10b981' }} />;
  if (status === 'failed') return <XCircle size={16} style={{ color: '#ef4444' }} />;
  return <MinusCircle size={16} style={{ color: '#94a3b8' }} />;
};

const WorkflowRuns: React.FC = () => {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [openRunId, setOpenRunId] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, NodeRun[]>>({});
  const [loading, setLoading] = useState(false);

  const fetchRuns = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/workflow/runs?limit=50`);
      if (res.ok) setRuns((await res.json()).runs);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRuns(); }, []);

  const toggleRun = async (runId: string) => {
    if (openRunId === runId) { setOpenRunId(null); return; }
    setOpenRunId(runId);
    if (!details[runId]) {
      const res = await fetch(`${API_BASE}/api/v1/workflow/runs/${runId}`);
      if (res.ok) {
        const body = await res.json();
        setDetails(prev => ({ ...prev, [runId]: body.node_runs || [] }));
      }
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.6rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <ScrollText size={26} style={{ color: 'var(--primary-color)' }} /> Workflow Runs
          </h1>
          <p style={{ color: 'var(--text-secondary)' }}>워크플로 실행 이력 — 어느 노드에서 왜 실패했는지 노드 단위로 확인합니다.</p>
        </div>
        <button className="btn-secondary" onClick={fetchRuns} disabled={loading} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <RefreshCw size={16} /> {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {runs.length === 0 && !loading && (
        <p style={{ color: 'var(--text-secondary)' }}>아직 실행 이력이 없습니다. Workflow Builder에서 Run을 눌러보세요.</p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {runs.map((run) => (
          <div key={run.id} style={{ border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)', backgroundColor: 'var(--surface-color)' }}>
            <div
              onClick={() => toggleRun(run.id)}
              style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.9rem 1.25rem', cursor: 'pointer' }}
            >
              <StatusIcon status={run.status} />
              <span style={{ fontWeight: 600 }}>{run.workflow_name || 'Untitled workflow'}</span>
              <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', fontFamily: 'monospace' }}>{run.id.slice(0, 8)}</span>
              <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                {run.duration_ms ? `${run.duration_ms}ms` : ''}
                {run.created_at ? ` · ${new Date(run.created_at + 'Z').toLocaleString()}` : ''}
              </span>
            </div>

            {openRunId === run.id && (
              <div style={{ borderTop: '1px solid var(--border-color)', padding: '0.75rem 1.25rem', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {(details[run.id] || []).map((nr) => (
                  <div key={nr.node_id} style={{
                    display: 'flex', alignItems: 'flex-start', gap: '0.6rem', fontSize: '0.85rem',
                    padding: '0.45rem 0.6rem', borderRadius: 'var(--radius-md)',
                    backgroundColor: nr.status === 'failed' ? 'rgba(239,68,68,0.07)' : 'var(--bg-color)'
                  }}>
                    <StatusIcon status={nr.status} />
                    <div style={{ minWidth: 0 }}>
                      <span style={{ fontWeight: 600 }}>{nr.node_id}</span>
                      <span style={{ color: 'var(--text-secondary)', marginLeft: '0.5rem' }}>{nr.node_type} · {nr.duration_ms}ms</span>
                      {nr.error && <div style={{ color: '#ef4444', fontFamily: 'monospace', fontSize: '0.8rem', whiteSpace: 'pre-wrap', marginTop: '0.2rem' }}>{nr.error}</div>}
                      {!nr.error && nr.output_preview && <div style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', marginTop: '0.2rem' }}>{nr.output_preview}</div>}
                    </div>
                  </div>
                ))}
                {details[run.id] && details[run.id].length === 0 && (
                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>노드 로그가 없습니다.</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default WorkflowRuns;
