import { useState, useEffect, useRef } from 'react';
import { getToken, API_BASE, handleAuthError } from '../api';

// ==========================================
// 1. useChat Hook
// ==========================================

export interface Message {
  id: string;
  role: 'user' | 'ai';
  content: string;
}

export interface AppModel {
  id: string;
  name: string;
  mode: string;
  description: string;
}

export const useChat = (appId: string | undefined, appMode: string | undefined) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (appId && appMode) {
      // Initialize greeting
      setMessages([
        {
          id: 'msg_init',
          role: 'ai',
          content: `Hello! I'm running on the "${appMode}" engine. How can I help you today?`
        }
      ]);
    }
  }, [appId, appMode]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (customPrompt?: string) => {
    const textToSend = customPrompt !== undefined ? customPrompt : input;
    if (!textToSend.trim() || isLoading || !appMode) return;

    const userText = textToSend.trim();
    if (customPrompt === undefined) {
      setInput('');
    }

    const newUserMsg: Message = { id: `msg_${Date.now()}`, role: 'user', content: userText };
    setMessages(prev => [...prev, newUserMsg]);
    setIsLoading(true);

    try {
      const token = getToken();
      const res = await fetch(`${API_BASE}/api/v1/tasks/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          prompt: userText,
          mode: appMode,
          params: {}
        })
      });

      if (!res.ok) {
        if (handleAuthError(res)) return;
        const errData = await res.json().catch(() => ({}));
        setMessages(prev => [
          ...prev,
          {
            id: `msg_err_${Date.now()}`,
            role: 'ai',
            content: `Error: ${errData.detail || errData.error?.message || 'Unknown error occurred'}`
          }
        ]);
        setIsLoading(false);
        return;
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder('utf-8');

      let aiContent = '';
      const aiMessageId = `msg_ai_${Date.now()}`;

      setMessages(prev => [
        ...prev,
        {
          id: aiMessageId,
          role: 'ai',
          content: ''
        }
      ]);

      let done = false;
      let buffer = '';

      while (!done) {
        const { value, done: readerDone } = await reader!.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.substring(6).trim();
              if (!dataStr) continue;

              try {
                const event = JSON.parse(dataStr);

                if (event.type === 'log') {
                  aiContent += `\n> ${event.message}\n\n`;
                } else if (event.type === 'token') {
                  aiContent += event.message || '';
                } else if (event.type === 'done') {
                  const taskData = event.data || {};
                  const inlineArtifact = (taskData.artifacts || []).find(
                    (a: any) => typeof a.inline === 'string' && a.inline
                  );
                  const fileArtifacts = (taskData.artifacts || []).filter((a: any) => a.uri);

                  if (inlineArtifact) {
                    aiContent = inlineArtifact.inline;
                  } else if (fileArtifacts.length > 0) {
                    aiContent +=
                      '\n\n' +
                      fileArtifacts.map((a: any) => `[${a.kind}] ${a.title || a.id}: ${a.uri}`).join('\n');
                  }
                } else if (event.type === 'error') {
                  aiContent += `\n\nError: ${event.message}`;
                }

                setMessages(prev =>
                  prev.map(m => (m.id === aiMessageId ? { ...m, content: aiContent.trim() } : m))
                );
              } catch (e) {
                console.error('SSE parse error', e, dataStr);
              }
            }
          }
        }
      }
    } catch (err: any) {
      setMessages(prev => [
        ...prev,
        {
          id: `msg_err_${Date.now()}`,
          role: 'ai',
          content: `Network Error: ${err.message}`
        }
      ]);
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

  return {
    messages,
    input,
    setInput,
    isLoading,
    messagesEndRef,
    handleSend,
    handleKeyDown
  };
};

// ==========================================
// 2. useKnowledge Hook
// ==========================================

export const useKnowledge = () => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const newFiles = Array.from(e.dataTransfer.files);
      setSelectedFiles(prev => [...prev, ...newFiles]);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const newFiles = Array.from(e.target.files);
      setSelectedFiles(prev => [...prev, ...newFiles]);
    }
  };

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;
    setIsUploading(true);
    setUploadStatus('idle');

    try {
      const token = getToken();
      const formData = new FormData();
      selectedFiles.forEach(file => {
        formData.append('files', file);
      });

      const res = await fetch(`${API_BASE}/api/v1/rag/upload`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`
        },
        body: formData
      });

      if (res.ok) {
        setUploadStatus('success');
        setStatusMessage('Knowledge base successfully updated.');
        setSelectedFiles([]);
      } else {
        const errorData = await res.json();
        setUploadStatus('error');
        setStatusMessage(errorData.detail || 'Failed to upload documents.');
      }
    } catch (err: any) {
      setUploadStatus('error');
      setStatusMessage(`Network error: ${err.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  return {
    dragActive,
    selectedFiles,
    isUploading,
    uploadStatus,
    statusMessage,
    inputRef,
    handleDrag,
    handleDrop,
    handleChange,
    removeFile,
    handleUpload
  };
};

// ==========================================
// 3. useStats Hook
// ==========================================

export interface BackendMode {
  primary: string;
  pipeline: string[];
  description: string;
  available?: boolean;
}

export const useStats = () => {
  const [stats, setStats] = useState<any>(null);
  const [modes, setModes] = useState<Record<string, BackendMode>>({});
  const [selectedMode, setSelectedMode] = useState('');

  const fetchStats = async () => {
    try {
      const token = getToken();
      if (!token) return;
      const res = await fetch(`${API_BASE}/api/v1/admin/stats`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) setStats(await res.json());
    } catch (err) {
      console.error(err);
    }
  };

  const fetchModes = async () => {
    try {
      const res = await fetch(`${API_BASE}/modes`);
      if (res.ok) {
        const data = await res.json();
        setModes(data.modes);
        const firstAvailable = Object.keys(data.modes).find(
          k => data.modes[k].available !== false
        );
        if (firstAvailable) setSelectedMode(firstAvailable);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchStats();
    fetchModes();
  }, []);

  return {
    stats,
    modes,
    selectedMode,
    setSelectedMode,
    refreshStats: fetchStats,
    refreshModes: fetchModes
  };
};
