import React, { useState } from 'react';
import { Send, Bot, User, Loader2, Plus, MessageSquare, Lightbulb, Copy, Download, X, ThumbsUp, ThumbsDown } from 'lucide-react';
import { useChat } from '../../hooks/useWidgets';
import { API_BASE, getToken } from '../../api';

interface ChatWidgetProps {
  appId?: string;
  appMode?: string;
  appParams?: Record<string, any>;
}

export const ChatWidget: React.FC<ChatWidgetProps> = ({ appId, appMode, appParams }) => {
  const {
    messages,
    input,
    setInput,
    isLoading,
    messagesEndRef,
    handleSend,
    handleKeyDown,
    sessions,
    currentSessionId,
    loadSession,
    createNewChat,
    isSummarizing,
    summaryText,
    extractKnowledge,
    variableDefs,
    variablesNeeded,
    submitVariables,
    pendingPlan,
    setPendingPlan,
    approvePlan
  } = useChat(appId, appMode, appParams);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});
  const [feedbackSent, setFeedbackSent] = useState<Record<string, string>>({});

  const sendFeedback = async (msg: { id: string; content: string }, rating: 'up' | 'down') => {
    if (!currentSessionId || feedbackSent[msg.id]) return;
    const comment = rating === 'down'
      ? window.prompt('어떤 점이 아쉬웠나요? (선택)') || undefined
      : undefined;
    try {
      const res = await fetch(`${API_BASE}/api/v1/conversations/${currentSessionId}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${getToken()}` },
        body: JSON.stringify({ rating, message_id: msg.id, message_content: msg.content, comment })
      });
      if (res.ok) setFeedbackSent(prev => ({ ...prev, [msg.id]: rating }));
    } catch (err) {
      console.error(err);
    }
  };

  const missingRequired = variableDefs.some(
    (v: any) => v.required && !(variableValues[v.key] || '').trim()
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'row', height: '100%', gap: '1rem' }}>
      {/* History Sidebar */}
      <div style={{
        width: '240px',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--surface-color)',
        borderRadius: 'var(--radius-lg)',
        border: '1px solid var(--border-color)',
        overflow: 'hidden'
      }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-color)' }}>
          <button
            onClick={createNewChat}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
              padding: '0.6rem', borderRadius: 'var(--radius-md)',
              backgroundColor: 'var(--primary-color)', color: 'white',
              border: 'none', cursor: 'pointer', fontWeight: 500
            }}
          >
            <Plus size={16} /> New Chat
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem' }}>
          {sessions.length === 0 ? (
            <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              No history yet.
            </div>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              {sessions.map(session => (
                <li key={session.id}>
                  <button
                    onClick={() => loadSession(session.id)}
                    style={{
                      width: '100%', textAlign: 'left', padding: '0.6rem',
                      display: 'flex', alignItems: 'center', gap: '0.5rem',
                      borderRadius: 'var(--radius-md)', border: 'none', cursor: 'pointer',
                      backgroundColor: currentSessionId === session.id ? 'var(--bg-color)' : 'transparent',
                      color: currentSessionId === session.id ? 'var(--primary-color)' : 'var(--text-secondary)',
                      fontWeight: currentSessionId === session.id ? 600 : 400,
                      transition: 'all 0.2s'
                    }}
                  >
                    <MessageSquare size={14} />
                    <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontSize: '0.85rem' }}>
                      {session.title || 'Untitled Session'}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', backgroundColor: 'var(--surface-color)', borderRadius: 'var(--radius-lg)', border: '1px solid var(--border-color)', overflow: 'hidden', position: 'relative' }}>
      {/* Chat Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        
        <div style={{ position: 'sticky', top: 0, zIndex: 10, display: 'flex', justifyContent: 'flex-end', marginBottom: '-2rem' }}>
          <button
            onClick={() => {
              setIsModalOpen(true);
              if (!summaryText && messages.length > 1) {
                extractKnowledge();
              }
            }}
            style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              padding: '0.5rem 1rem', borderRadius: 'var(--radius-full)',
              backgroundColor: 'var(--surface-color)', border: '1px solid var(--border-color)',
              color: 'var(--text-primary)', boxShadow: 'var(--shadow-sm)',
              cursor: 'pointer', fontSize: '0.85rem', fontWeight: 500
            }}
          >
            <Lightbulb size={16} color="#f59e0b" /> 지식 꺼내기
          </button>
        </div>
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
              {/* feedback buttons on assistant replies */}
              {msg.role !== 'user' && msg.id !== 'msg_init' && msg.content && currentSessionId && (
                <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.5rem' }}>
                  {feedbackSent[msg.id] ? (
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>피드백 감사합니다</span>
                  ) : (
                    <>
                      <button onClick={() => sendFeedback(msg, 'up')} title="도움됨"
                        style={{ color: 'var(--text-secondary)', padding: '2px' }}>
                        <ThumbsUp size={13} />
                      </button>
                      <button onClick={() => sendFeedback(msg, 'down')} title="아쉬움"
                        style={{ color: 'var(--text-secondary)', padding: '2px' }}>
                        <ThumbsDown size={13} />
                      </button>
                    </>
                  )}
                </div>
              )}
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

      {/* Conversation variables start-form (dify-style) */}
      {variablesNeeded && (
        <div style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)' }}>
          <h4 style={{ fontWeight: 600, marginBottom: '0.75rem', fontSize: '0.9rem' }}>대화를 시작하기 전에 알려주세요</h4>
          <form
            onSubmit={(e) => { e.preventDefault(); submitVariables(variableValues); }}
            style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}
          >
            {variableDefs.map((v: any) => (
              <div key={v.key} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <label style={{ width: '120px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                  {v.label || v.key}{v.required && <span style={{ color: '#ef4444' }}> *</span>}
                </label>
                <input
                  type="text"
                  value={variableValues[v.key] || ''}
                  onChange={(e) => setVariableValues(prev => ({ ...prev, [v.key]: e.target.value }))}
                  style={{ flex: 1, padding: '0.5rem 0.75rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--surface-color)' }}
                />
              </div>
            ))}
            <button type="submit" className="btn-primary" disabled={missingRequired} style={{ alignSelf: 'flex-end', padding: '0.5rem 1.25rem' }}>
              입력 완료 — 대화 시작
            </button>
          </form>
        </div>
      )}

      {/* Deep-research HITL: editable plan review panel */}
      {pendingPlan && (
        <div style={{ padding: '1rem 1.5rem', borderTop: '1px solid var(--border-color)', backgroundColor: 'var(--bg-color)', maxHeight: '40%', overflowY: 'auto' }}>
          <h4 style={{ fontWeight: 600, marginBottom: '0.25rem', fontSize: '0.9rem' }}>리서치 계획 검토</h4>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.75rem' }}>
            섹션 제목과 검색어를 수정한 뒤 실행하세요. (검색어는 쉼표로 구분)
          </p>
          <input
            type="text"
            value={pendingPlan.title || ''}
            onChange={(e) => setPendingPlan({ ...pendingPlan, title: e.target.value })}
            style={{ width: '100%', padding: '0.5rem 0.75rem', fontWeight: 600, marginBottom: '0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--surface-color)' }}
          />
          {(pendingPlan.sections || []).map((section: any, idx: number) => (
            <div key={idx} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
              <input
                type="text" value={section.heading || ''}
                onChange={(e) => setPendingPlan({
                  ...pendingPlan,
                  sections: pendingPlan.sections.map((s: any, i: number) => i === idx ? { ...s, heading: e.target.value } : s)
                })}
                style={{ flex: 1, padding: '0.45rem 0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--surface-color)' }}
              />
              <input
                type="text" value={(section.queries || []).join(', ')}
                onChange={(e) => setPendingPlan({
                  ...pendingPlan,
                  sections: pendingPlan.sections.map((s: any, i: number) => i === idx ? { ...s, queries: e.target.value.split(',').map((q: string) => q.trim()).filter(Boolean) } : s)
                })}
                placeholder="검색어1, 검색어2"
                style={{ flex: 2, padding: '0.45rem 0.6rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--surface-color)' }}
              />
              <button
                type="button"
                onClick={() => setPendingPlan({ ...pendingPlan, sections: pendingPlan.sections.filter((_: any, i: number) => i !== idx) })}
                style={{ color: '#ef4444' }}
              >
                <X size={15} />
              </button>
            </div>
          ))}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '0.5rem' }}>
            <button
              type="button" className="btn-secondary" style={{ fontSize: '0.8rem' }}
              onClick={() => setPendingPlan({ ...pendingPlan, sections: [...(pendingPlan.sections || []), { heading: '', queries: [] }] })}
            >
              + 섹션 추가
            </button>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn-secondary" onClick={() => setPendingPlan(null)}>취소</button>
              <button type="button" className="btn-primary" onClick={() => approvePlan(pendingPlan)} disabled={isLoading}>
                계획 승인 — 리서치 실행
              </button>
            </div>
          </div>
        </div>
      )}

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
      
      {/* Summary Modal */}
      {isModalOpen && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, 
          backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 100,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          backdropFilter: 'blur(4px)'
        }}>
          <div className="glass-panel" style={{
            width: '90%', maxWidth: '600px', height: '80vh', padding: '2rem', borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-lg)', backgroundColor: 'var(--surface-color)', position: 'relative',
            display: 'flex', flexDirection: 'column'
          }}>
            <button 
              onClick={() => setIsModalOpen(false)}
              style={{ position: 'absolute', top: '1.5rem', right: '1.5rem', color: 'var(--text-secondary)' }}
            >
              <X size={20} />
            </button>
            <h2 style={{ fontSize: '1.5rem', fontWeight: '700', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Lightbulb size={24} color="#f59e0b" /> 대화 지식 추출 (Summary)
            </h2>
            
            <div style={{ flex: 1, overflowY: 'auto', backgroundColor: 'var(--bg-color)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', marginBottom: '1.5rem', whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: '0.95rem' }}>
              {isSummarizing ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
                  <Loader2 className="animate-spin" size={16} /> 대화 내용을 요약하고 지식을 추출하는 중입니다...
                </div>
              ) : null}
              {summaryText || (!isSummarizing && "요약된 내용이 없습니다.")}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
              <button 
                onClick={() => {
                  navigator.clipboard.writeText(summaryText);
                  alert('클립보드에 복사되었습니다.');
                }}
                disabled={isSummarizing || !summaryText}
                className="btn-secondary"
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', backgroundColor: 'var(--surface-color)', cursor: 'pointer' }}
              >
                <Copy size={16} /> 복사하기
              </button>
              <button 
                onClick={() => {
                  const blob = new Blob([summaryText], { type: 'text/markdown' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `session_summary_${currentSessionId || 'new'}.md`;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                }}
                disabled={isSummarizing || !summaryText}
                className="btn-primary"
                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.6rem 1rem', borderRadius: 'var(--radius-md)', border: 'none', backgroundColor: 'var(--primary-color)', color: 'white', cursor: 'pointer' }}
              >
                <Download size={16} /> .md 파일 다운로드
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
