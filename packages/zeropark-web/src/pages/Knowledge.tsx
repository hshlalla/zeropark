import React, { useState, useRef } from 'react';
import { UploadCloud, FileText, CheckCircle, AlertCircle } from 'lucide-react';
import { getToken } from '../api';

const Knowledge: React.FC = () => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'success' | 'error'>('idle');
  const [statusMessage, setStatusMessage] = useState('');
  
  const inputRef = useRef<HTMLInputElement>(null);

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

      const res = await fetch('http://localhost:8000/api/v1/rag/upload', {
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
