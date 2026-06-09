import React, { useState } from 'react';
import { executeTask } from './api';
import type { TaskResult } from './api';
import { ArtifactCard } from './components/ArtifactCard';
import './index.css'; // Make sure this is imported to apply our Glassmorphism UI

function App() {
  const [prompt, setPrompt] = useState('');
  const [mode, setMode] = useState<string>('research');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TaskResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const modes = [
    { id: 'research', label: 'Research' },
    { id: 'workflow', label: 'Deep Think (Agent)' },
    { id: 'slides', label: 'Create Slides' },
    { id: 'sheets', label: 'Create Sheets' },
    { id: 'browse', label: 'Browse Web' }
  ];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await executeTask({
        prompt,
        capability: mode
      });
      setResult(res);
      if (res.status === 'failed') {
        setError(res.error || 'Task failed without an error message.');
      }
    } catch (err: any) {
      setError(err.message || 'An unknown error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="header">
        <h1 className="logo">Zeropark</h1>
      </div>

      <form className="search-container" onSubmit={handleSubmit}>
        <div className="mode-selector">
          {modes.map(m => (
            <button
              key={m.id}
              type="button"
              className={`mode-chip ${mode === m.id ? 'active' : ''}`}
              onClick={() => setMode(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>

        <input
          type="text"
          className="glass-input"
          placeholder={`Ask Zeropark to ${modes.find(m => m.id === mode)?.label.toLowerCase()}...`}
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          disabled={loading}
          autoFocus
        />

        <div style={{ textAlign: 'center' }}>
          <button type="submit" className="glass-button" disabled={loading || !prompt.trim()}>
            {loading ? <div className="loader" /> : 'Execute'}
          </button>
        </div>
      </form>

      {error && (
        <div className="glass-panel" style={{ borderColor: 'rgba(255, 100, 100, 0.5)' }}>
          <h3 style={{ color: '#ff8888', marginTop: 0 }}>Error</h3>
          <p>{error}</p>
        </div>
      )}

      {result && result.artifacts && result.artifacts.length > 0 && (
        <div className="results-area">
          <h2 style={{ paddingLeft: '1rem', color: '#fff', fontSize: '1.4rem' }}>
            Results ({result.artifacts.length})
          </h2>
          {result.artifacts.map((artifact, idx) => (
            <ArtifactCard key={idx} artifact={artifact} />
          ))}
        </div>
      )}
      
      {result && result.sources && result.sources.length > 0 && (
        <div className="glass-panel" style={{ marginTop: '2rem' }}>
          <h3 style={{ marginTop: 0 }}>Sources</h3>
          <ul style={{ color: '#cbd5e1', fontSize: '0.9rem' }}>
            {result.sources.map((src, idx) => (
              <li key={idx}><a href={src.url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-hover)' }}>{src.url}</a> ({src.provider_id})</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

export default App;
