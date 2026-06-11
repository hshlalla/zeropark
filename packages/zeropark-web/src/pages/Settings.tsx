import React, { useState, useEffect } from 'react';
import { Settings as SettingsIcon, Key, Save, CheckCircle, Palette, Globe } from 'lucide-react';

const Settings: React.FC = () => {
  const [openAIKey, setOpenAIKey] = useState('');
  const [anthropicKey, setAnthropicKey] = useState('');
  const [theme, setTheme] = useState('dark');
  const [language, setLanguage] = useState('en');
  
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    // Load from LocalStorage
    const storedOpenAI = localStorage.getItem('zp_openai_key') || '';
    const storedAnthropic = localStorage.getItem('zp_anthropic_key') || '';
    const storedTheme = localStorage.getItem('zp_theme') || 'dark';
    const storedLanguage = localStorage.getItem('zp_language') || 'en';

    setOpenAIKey(storedOpenAI);
    setAnthropicKey(storedAnthropic);
    setTheme(storedTheme);
    setLanguage(storedLanguage);
  }, []);

  const handleSave = () => {
    localStorage.setItem('zp_openai_key', openAIKey);
    localStorage.setItem('zp_anthropic_key', anthropicKey);
    localStorage.setItem('zp_theme', theme);
    localStorage.setItem('zp_language', language);

    // Apply theme (In a real app, this would trigger a Context/Provider update)
    if (theme === 'light') {
      document.body.classList.add('light-mode');
    } else {
      document.body.classList.remove('light-mode');
    }

    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 3000);
  };

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', paddingBottom: '4rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '2rem' }}>
        <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'linear-gradient(135deg, #6366f1, #a855f7)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <SettingsIcon size={24} />
        </div>
        <div>
          <h1 style={{ fontSize: '1.5rem', fontWeight: '700' }}>Workspace Settings</h1>
          <p style={{ color: 'var(--text-secondary)' }}>Configure your API keys and workspace preferences.</p>
        </div>
      </div>

      {isSaved && (
        <div style={{ padding: '1rem', borderRadius: 'var(--radius-md)', backgroundColor: 'rgba(16, 185, 129, 0.1)', color: '#10b981', border: '1px solid rgba(16, 185, 129, 0.2)', marginBottom: '2rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <CheckCircle size={20} /> Settings saved successfully!
        </div>
      )}

      {/* API Keys Section */}
      <section className="glass-panel" style={{ padding: '2rem', borderRadius: 'var(--radius-lg)', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
          <Key size={20} style={{ color: 'var(--primary-color)' }} />
          <h2 style={{ fontSize: '1.2rem', fontWeight: '600' }}>API Keys</h2>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', fontWeight: '500' }}>OpenAI API Key</label>
            <input 
              type="password" 
              value={openAIKey}
              onChange={(e) => setOpenAIKey(e.target.value)}
              placeholder="sk-..."
              style={{ width: '100%', padding: '0.75rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)' }}
            />
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Used for GPT-4o and text embeddings.</p>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', fontWeight: '500' }}>Anthropic API Key</label>
            <input 
              type="password" 
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
              placeholder="sk-ant-..."
              style={{ width: '100%', padding: '0.75rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)' }}
            />
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>Used for Claude 3 Opus/Sonnet models.</p>
          </div>
        </div>
      </section>

      {/* Preferences Section */}
      <section className="glass-panel" style={{ padding: '2rem', borderRadius: 'var(--radius-lg)', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
          <Palette size={20} style={{ color: 'var(--primary-color)' }} />
          <h2 style={{ fontSize: '1.2rem', fontWeight: '600' }}>Preferences</h2>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', fontWeight: '500' }}>Theme</label>
            <select 
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              style={{ width: '100%', padding: '0.75rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)' }}
            >
              <option value="dark">Dark Mode (Default)</option>
              <option value="light">Light Mode</option>
            </select>
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <Globe size={16} />
              <label style={{ fontSize: '0.9rem', fontWeight: '500' }}>Language</label>
            </div>
            <select 
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              style={{ width: '100%', padding: '0.75rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', color: 'var(--text-primary)' }}
            >
              <option value="en">English</option>
              <option value="ko">Korean (?쒓뎅??</option>
            </select>
          </div>
        </div>
      </section>

      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button className="btn-primary" onClick={handleSave} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.75rem 2rem', fontSize: '1rem' }}>
          <Save size={20} /> Save Changes
        </button>
      </div>

    </div>
  );
};

export default Settings;
