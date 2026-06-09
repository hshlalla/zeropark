import React from 'react';
import type { Artifact } from '../api';

interface ArtifactCardProps {
  artifact: Artifact;
}

export const ArtifactCard: React.FC<ArtifactCardProps> = ({ artifact }) => {
  const isImage = artifact.mime_type.startsWith('image/');
  const isText = artifact.mime_type.startsWith('text/') || artifact.inline;
  const isDownload = !isImage && !isText && artifact.uri;

  return (
    <div className="glass-panel artifact-card">
      <h3 className="artifact-title">{artifact.title || 'Untitled Artifact'}</h3>
      
      {isImage && artifact.uri && (
        <img src={artifact.uri} alt={artifact.title} className="artifact-image" />
      )}

      {isText && artifact.inline && (
        <div className="markdown-body">
          {/* Simple text rendering for now. In a real app, use react-markdown */}
          <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', margin: 0 }}>
            {artifact.inline}
          </pre>
        </div>
      )}

      {isDownload && artifact.uri && (
        <div>
          <p style={{ color: '#aaa', fontSize: '0.9rem' }}>
            Type: {artifact.mime_type}
          </p>
          <a href={artifact.uri} target="_blank" rel="noreferrer" className="download-btn">
            Download File
          </a>
        </div>
      )}
    </div>
  );
};
