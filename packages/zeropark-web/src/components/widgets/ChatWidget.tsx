import React from 'react';
import { Send, Bot, User, Loader2 } from 'lucide-react';
import { useChat } from '../../hooks/useWidgets';

interface ChatWidgetProps {
  appId?: string;
  appMode?: string;
}

export const ChatWidget: React.FC<ChatWidgetProps> = ({ appId, appMode }) => {
  const {
    messages,
    input,
    setInput,
    isLoading,
    messagesEndRef,
    handleSend,
    handleKeyDown
  } = useChat(appId, appMode);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', backgroundColor: 'var(--surface-color)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-color)', overflow: 'hidden' }}>
      {/* Chat Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {messages.slice(-50).map(msg => (
          <div key={msg.id} style={{
            display: 'flex',
            gap: '0.75rem',
            alignItems: 'flex-start',
            flexDirection: msg.role === 'user' ? 'row-reverse' : 'row'
          }}>
            {/* Avatar */}
            <div style={{
              width: '32px', height: '32px', borderRadius: '50%', flexShrink: 0,
              backgroundColor: msg.role === 'user' ? 'var(--text-primary)' : 'var(--primary-color)',
              color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
              {msg.role === 'user' ? <User size={16} /> : <Bot size={16} />}
            </div>
            
            {/* Message Bubble */}
            <div style={{
              maxWidth: '75%',
              padding: '0.75rem 1rem',
              borderRadius: 'var(--radius-lg)',
              backgroundColor: msg.role === 'user' ? 'rgba(37, 99, 235, 0.1)' : 'var(--bg-color)',
              color: 'var(--text-primary)',
              border: msg.role === 'user' ? '1px solid rgba(37, 99, 235, 0.2)' : '1px solid var(--border-color)',
              boxShadow: 'var(--shadow-sm)',
              whiteSpace: 'pre-wrap',
              fontFamily: msg.role === 'ai' ? 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' : 'inherit',
              fontSize: msg.role === 'ai' ? '0.85rem' : '0.95rem'
            }}>
              {msg.content}
            </div>
          </div>
        ))}
        {isLoading && (
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', color: 'var(--text-secondary)' }}>
            <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--primary-color)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Bot size={16} />
            </div>
            <Loader2 className="animate-spin" size={16} />
            <span style={{ fontSize: '0.85rem' }}>Executing engines...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div style={{
        padding: '1rem',
        backgroundColor: 'var(--surface-color)',
        borderTop: '1px solid var(--border-color)'
      }}>
        <form 
          onSubmit={(e) => { e.preventDefault(); handleSend(); }}
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: '0.75rem',
            backgroundColor: 'var(--bg-color)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)',
            padding: '0.35rem 0.5rem',
            boxShadow: 'var(--shadow-sm)'
          }}
        >
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your prompt here..."
            style={{
              flex: 1,
              minHeight: '36px',
              maxHeight: '120px',
              padding: '0.4rem 0.6rem',
              backgroundColor: 'transparent',
              border: 'none',
              outline: 'none',
              resize: 'none',
              fontFamily: 'inherit',
              fontSize: '0.95rem'
            }}
            rows={1}
          />
          <button 
            type="submit" 
            disabled={!input.trim() || isLoading}
            style={{
              width: '36px',
              height: '36px',
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
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
};
