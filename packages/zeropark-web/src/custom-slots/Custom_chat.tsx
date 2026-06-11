import React from 'react';
import { ChatWidget } from '../components/widgets/ChatWidget';
import { ShieldAlert } from 'lucide-react';

interface CustomChatProps {
  appId?: string;
  appMode?: string;
}

export const Custom_chat: React.FC<CustomChatProps> = ({ appId, appMode }) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Vibe Coded Custom Banner for Vendor */}
      <div style={{
        padding: '0.5rem 1rem',
        backgroundColor: 'rgba(37, 99, 235, 0.08)',
        border: '1px solid rgba(37, 99, 235, 0.2)',
        borderRadius: 'var(--radius-md)',
        marginBottom: '0.75rem',
        display: 'flex',
        alignItems: 'center',
        gap: '0.5rem',
        fontSize: '0.8rem',
        color: 'var(--primary-color)',
        fontWeight: '600'
      }}>
        <ShieldAlert size={14} />
        Customized via Vibe Coding (Samsung Enterprise Workspace Engine Enabled)
      </div>

      {/* Render the standard ChatWidget */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
        <ChatWidget appId={appId} appMode={appMode} />
      </div>
    </div>
  );
};
export default Custom_chat;
