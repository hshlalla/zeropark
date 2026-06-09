import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Send, Bot, User, ArrowLeft, Loader2 } from 'lucide-react';
import { getToken } from '../api';

interface AppModel {
  id: string;
  name: string;
  mode: string;
  description: string;
}

interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
}

const AppViewer: React.FC = () => {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  const [app, setApp] = useState<AppModel | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Load app info
    const savedApps = localStorage.getItem('zp_apps');
    if (savedApps) {
      const apps: AppModel[] = JSON.parse(savedApps);
      const found = apps.find(a => a.id === appId);
      if (found) {
        setApp(found);
        // Initial greeting
        setMessages([{
          id: 'msg_init',
          role: 'ai',
          content: `Hello! I am ${found.name}. I'm running on the "${found.mode}" engine. How can I help you today?`
        }]);
      }
    }
  }, [appId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || isLoading || !app) return;

    const userText = input.trim();
    setInput('');
    
    // Add user message to UI
    const newUserMsg: Message = { id: `msg_${Date.now()}`, role: 'user', content: userText };
    setMessages(prev => [...prev, newUserMsg]);
    setIsLoading(true);

    try {
      const token = getToken();
      const res = await fetch('http://localhost:8000/api/v1/tasks', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          prompt: userText,
          mode: app.mode,
          params: {}
        })
      });

      if (res.ok) {
        const data = await res.json();
        // data could contain plan, result, or raw string based on backend implementation
        // For now, let's just display the raw JSON or a fallback message to prove integration
        const aiResponse = data.plan 
          ? `Engine Execution Plan: ${JSON.stringify(data.plan)}\nTask ID: ${data.task_id}`
          : JSON.stringify(data, null, 2);

        setMessages(prev => [...prev, {
          id: `msg_ai_${Date.now()}`,
          role: 'ai',
          content: aiResponse
        }]);
      } else {
        const errData = await res.json();
        setMessages(prev => [...prev, {
          id: `msg_err_${Date.now()}`,
          role: 'ai',
          content: `Error: ${errData.detail || errData.error?.message || 'Unknown error occurred'}`
        }]);
      }
    } catch (err: any) {
      setMessages(prev => [...prev, {
        id: `msg_err_${Date.now()}`,
        role: 'ai',
        content: `Network Error: ${err.message}`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!app) {
    return <div style={{ padding: '2rem' }}>App not found.</div>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', backgroundColor: 'var(--bg-color)', margin: '-2rem' }}>
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

      {/* Chat Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        {messages.map(msg => (
          <div key={msg.id} style={{
            display: 'flex',
            gap: '1rem',
            alignItems: 'flex-start',
            flexDirection: msg.role === 'user' ? 'row-reverse' : 'row'
          }}>
            {/* Avatar */}
            <div style={{
              width: '36px', height: '36px', borderRadius: '50%', flexShrink: 0,
              backgroundColor: msg.role === 'user' ? 'var(--text-primary)' : 'var(--primary-color)',
              color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
            </div>
            
            {/* Message Bubble */}
            <div style={{
              maxWidth: '70%',
              padding: '1rem',
              borderRadius: 'var(--radius-lg)',
              backgroundColor: msg.role === 'user' ? 'rgba(37, 99, 235, 0.1)' : 'var(--surface-color)',
              color: msg.role === 'user' ? 'var(--text-primary)' : 'var(--text-primary)',
              border: msg.role === 'user' ? '1px solid rgba(37, 99, 235, 0.2)' : '1px solid var(--border-color)',
              boxShadow: 'var(--shadow-sm)',
              whiteSpace: 'pre-wrap',
              fontFamily: msg.role === 'ai' ? 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' : 'inherit',
              fontSize: msg.role === 'ai' ? '0.9rem' : '1rem'
            }}>
              {msg.content}
            </div>
          </div>
        ))}
        {isLoading && (
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', color: 'var(--text-secondary)' }}>
            <div style={{ width: '36px', height: '36px', borderRadius: '50%', background: 'var(--primary-color)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={18} />
            </div>
            <Loader2 className="animate-spin" size={20} />
            <span style={{ fontSize: '0.9rem' }}>Executing engines...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div style={{
        padding: '1.5rem 2rem',
        backgroundColor: 'var(--surface-color)',
        borderTop: '1px solid var(--border-color)'
      }}>
        <form 
          onSubmit={handleSend}
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: '1rem',
            backgroundColor: 'var(--bg-color)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-lg)',
            padding: '0.5rem',
            boxShadow: 'var(--shadow-sm)'
          }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your prompt here... (Shift+Enter for new line)"
            style={{
              flex: 1,
              minHeight: '44px',
              maxHeight: '200px',
              padding: '0.5rem 1rem',
              backgroundColor: 'transparent',
              border: 'none',
              outline: 'none',
              resize: 'none',
              fontFamily: 'inherit',
              fontSize: '1rem'
            }}
            rows={1}
          />
          <button 
            type="submit" 
            disabled={!input.trim() || isLoading}
            style={{
              width: '44px',
              height: '44px',
              borderRadius: 'var(--radius-md)',
              backgroundColor: input.trim() && !isLoading ? 'var(--primary-color)' : 'var(--border-color)',
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s ease',
              cursor: input.trim() && !isLoading ? 'pointer' : 'not-allowed'
            }}
          >
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
};

export default AppViewer;
