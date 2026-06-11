import React from 'react';
import { UploadCloud, FileText, CheckCircle, AlertCircle } from 'lucide-react';
import { useKnowledge } from '../../hooks/useWidgets';

export const KnowledgeWidget: React.FC = () => {
  const {
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
  } = useKnowledge();

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      backgroundColor: 'var(--surface-color)',
      borderRadius: 'var(--radius-lg)',
      border: '1px solid var(--border-color)',
      padding: '1.5rem',
      overflowY: 'auto'
    }}>
      <h3 style={{ fontSize: '1.1rem', fontWeight: '700', marginBottom: '0.5rem' }}>Knowledge Base (RAG)</h3>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1rem' }}>
        Upload documents (.txt) to enhance your agents.
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
          backgroundColor: dragActive ? 'rgba(37, 99, 235, 0.05)' : 'var(--bg-color)',
          borderRadius: 'var(--radius-md)',
          padding: '2rem 1rem',
          textAlign: 'center',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
          marginBottom: '1rem'
        }}
      >
        <UploadCloud size={32} style={{ color: dragActive ? 'var(--primary-color)' : 'var(--text-secondary)', margin: '0 auto 0.5rem' }} />
        <h4 style={{ fontSize: '0.9rem', fontWeight: '600', marginBottom: '0.25rem' }}>Click or drag files here</h4>
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
        <div style={{ backgroundColor: 'var(--bg-color)', padding: '1rem', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)', marginBottom: '1rem' }}>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
            {selectedFiles.map((file, i) => (
              <li key={i} style={{ 
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', 
                padding: '0.5rem', backgroundColor: 'var(--surface-color)', borderRadius: 'var(--radius-md)',
                border: '1px solid var(--border-color)'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', minWidth: 0 }}>
                  <FileText size={16} style={{ color: 'var(--primary-color)', flexShrink: 0 }} />
                  <span style={{ fontSize: '0.8rem', fontWeight: '500', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
                </div>
                <button 
                  onClick={(e) => { e.stopPropagation(); removeFile(i); }}
                  style={{ color: 'var(--text-secondary)', fontSize: '0.75rem', textDecoration: 'underline', flexShrink: 0, marginLeft: '0.5rem' }}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '1rem' }}>
            <button 
              onClick={handleUpload} 
              disabled={isUploading}
              className="btn-primary"
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}
            >
              {isUploading ? 'Uploading...' : 'Save & Process'}
            </button>
          </div>
        </div>
      )}

      {/* Status Message */}
      {uploadStatus !== 'idle' && (
        <div style={{ 
          padding: '0.75rem', 
          borderRadius: 'var(--radius-md)', 
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          backgroundColor: uploadStatus === 'success' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
          color: uploadStatus === 'success' ? '#10b981' : '#ef4444',
          border: `1px solid ${uploadStatus === 'success' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)'}`,
          fontSize: '0.8rem'
        }}>
          {uploadStatus === 'success' ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
          <span style={{ fontWeight: '500' }}>{statusMessage}</span>
        </div>
      )}
    </div>
  );
};
