import React, { useState, useRef, useEffect } from 'react';
import { UploadCloud, FileText, CheckCircle, AlertCircle, FolderLock, Plus } from 'lucide-react';
import { getToken, API_BASE, authFetch, isAdmin } from '../api';

interface RagCollection {
  id: string;
  name: string;
  description: string | null;
  allowed_roles: string[];
}

const Knowledge: React.FC = () => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState('');

  // Collections: where the upload goes + who can read it
  const [collections, setCollections] = useState<RagCollection[]>([]);
  const [selectedCollection, setSelectedCollection] = useState('default');
  const [newCollectionName, setNewCollectionName] = useState('');
  const [newCollectionAdminOnly, setNewCollectionAdminOnly] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  const fetchCollections = async () => {
    try {
      const res = await authFetch('/api/v1/rag/collections');
      if (res.ok) {
        const data = await res.json();
        setCollections(data.collections);
        if (data.collections.length > 0 && !data.collections.some((c: RagCollection) => c.id === selectedCollection)) {
          setSelectedCollection(data.collections[0].id);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => { fetchCollections(); }, []);

  const handleCreateCollection = async () => {
    if (!newCollectionName.trim()) return;
    const res = await authFetch('/api/v1/rag/collections', {
      method: 'POST',
      body: JSON.stringify({
        name: newCollectionName,
        allowed_roles: newCollectionAdminOnly ? ['admin'] : ['user', 'admin'],
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      alert(err?.error?.message || err?.detail || '컬렉션 생성에 실패했습니다.');
      return;
    }
    setNewCollectionName('');
    setNewCollectionAdminOnly(false);
    await fetchCollections();
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
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

      const res = await fetch(`${API_BASE}/api/v1/rag/upload?collection_id=${encodeURIComponent(selectedCollection)}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
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

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', paddingBottom: '4rem' }}>
      <h1 style={{ fontSize: '1.5rem', fontWeight: '700', marginBottom: '1.5rem' }}>Knowledge Base</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
        Upload documents (txt, pdf, etc.) to enhance your agents with custom knowledge retrieval capabilities (RAG).
      </p>

      {/* Collection selector: where uploads go + who can read them */}
      <div className="glass-panel" style={{ padding: '1.25rem', borderRadius: 'var(--radius-lg)', marginBottom: '1.5rem' }}>
        <h3 style={{ fontWeight: '600', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <FolderLock size={18} style={{ color: 'var(--primary-color)' }} /> 업로드 대상 컬렉션
        </h3>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem' }}>
          {collections.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelectedCollection(c.id)}
              style={{
                padding: '0.5rem 0.9rem', borderRadius: 'var(--radius-md)', fontSize: '0.85rem',
                border: `1px solid ${selectedCollection === c.id ? 'var(--primary-color)' : 'var(--border-color)'}`,
                backgroundColor: selectedCollection === c.id ? 'rgba(37, 99, 235, 0.08)' : 'var(--bg-color)',
                color: selectedCollection === c.id ? 'var(--primary-color)' : 'var(--text-secondary)',
                fontWeight: selectedCollection === c.id ? 600 : 500, cursor: 'pointer'
              }}
              title={c.description || ''}
            >
              {c.name}
              <span style={{ marginLeft: '0.4rem', fontSize: '0.7rem', opacity: 0.8 }}>
                {c.allowed_roles.includes('user') ? '전체 공개' : '관리자 전용'}
              </span>
            </button>
          ))}
        </div>

        {isAdmin() && (
          <div style={{ display: 'flex', gap: '0.6rem', marginTop: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="text"
              value={newCollectionName}
              onChange={(e) => setNewCollectionName(e.target.value)}
              placeholder="새 컬렉션 이름 (예: 인사규정)"
              style={{ flex: '1 1 200px', padding: '0.5rem 0.75rem', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)', backgroundColor: 'var(--bg-color)' }}
            />
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              <input type="checkbox" checked={newCollectionAdminOnly} onChange={(e) => setNewCollectionAdminOnly(e.target.checked)} />
              관리자 전용
            </label>
            <button className="btn-secondary" onClick={handleCreateCollection} style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <Plus size={15} /> 컬렉션 추가
            </button>
          </div>
        )}
      </div>

      {/* Drag & Drop Zone */}
      <div 
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `2px dashed ${dragActive ? 'var(--primary-color)' : 'var(--border-color)'}`,
          backgroundColor: dragActive ? 'rgba(37, 99, 235, 0.05)' : 'var(--surface-color)',
          borderRadius: 'var(--radius-lg)',
          padding: '4rem 2rem',
          textAlign: 'center',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
          marginBottom: '2rem'
        }}
      >
        <UploadCloud size={48} style={{ color: dragActive ? 'var(--primary-color)' : 'var(--text-secondary)', margin: '0 auto 1rem' }} />
        <h3 style={{ fontSize: '1.1rem', fontWeight: '600', marginBottom: '0.5rem' }}>Click or drag files here to upload</h3>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Supports .txt files for now.</p>
        <input 
          ref={inputRef}
          type="file" 
          multiple
          onChange={handleChange}
          style={{ display: 'none' }}
        />
      </div>

      {/* File List */}
      {selectedFiles.length > 0 && (
        <div className="glass-panel" style={{ padding: '1.5rem', borderRadius: 'var(--radius-lg)', marginBottom: '2rem' }}>
          <h3 style={{ fontWeight: '600', marginBottom: '1rem' }}>Selected Files ({selectedFiles.length})</h3>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {selectedFiles.map((file, i) => (
              <li key={i} style={{ 
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', 
                padding: '0.75rem', backgroundColor: 'var(--bg-color)', borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border-color)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <FileText size={18} style={{ color: 'var(--primary-color)' }} />
                  <span style={{ fontSize: '0.9rem', fontWeight: '500' }}>{file.name}</span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{(file.size / 1024).toFixed(1)} KB</span>
                </div>
                <button 
                  onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                  style={{ color: 'var(--text-secondary)', fontSize: '0.8rem', textDecoration: 'underline' }}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1.5rem' }}>
            <button 
              onClick={handleUpload} 
              disabled={isUploading}
              className="btn-primary"
            >
              {isUploading ? 'Uploading...' : 'Save & Process'}
            </button>
          </div>
        </div>
      )}

      {/* Status Message */}
      {uploadStatus !== 'idle' && (
        <div style={{ 
          padding: '1rem', 
          borderRadius: 'var(--radius-md)', 
          display: 'flex', alignItems: 'center', gap: '0.75rem',
          backgroundColor: uploadStatus === 'success' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
          color: uploadStatus === 'success' ? '#10b981' : '#ef4444',
          border: `1px solid ${uploadStatus === 'success' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`
        }}>
          {uploadStatus === 'success' ? <CheckCircle size={20} /> : <AlertCircle size={20} />}
          <span style={{ fontWeight: '500' }}>{statusMessage}</span>
        </div>
      )}
    </div>
  );
};

export default Knowledge;
