import React from 'react';
import { useStats } from '../../hooks/useWidgets';
import { Activity } from 'lucide-react';

export const StatsWidget: React.FC = () => {
  const { stats } = useStats();

  if (!stats) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)' }}>
        Loading stats...
      </div>
    );
  }

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
      <h3 style={{ fontSize: '1.1rem', fontWeight: '700', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <Activity size={18} style={{ color: 'var(--primary-color)' }} /> System Stats
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', backgroundColor: 'var(--bg-color)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Total Users</span>
          <span style={{ fontSize: '1.1rem', fontWeight: '700' }}>{stats.total_users}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', backgroundColor: 'var(--bg-color)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Google Logins</span>
          <span style={{ fontSize: '1.1rem', fontWeight: '700' }}>{stats.google_users}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', backgroundColor: 'var(--bg-color)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Total Workflows</span>
          <span style={{ fontSize: '1.1rem', fontWeight: '700' }}>{stats.total_workflows !== undefined ? stats.total_workflows : '-'}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', backgroundColor: 'var(--bg-color)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-color)' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Chat Sessions</span>
          <span style={{ fontSize: '1.1rem', fontWeight: '700' }}>{stats.total_chats !== undefined ? stats.total_chats : '-'}</span>
        </div>
      </div>
    </div>
  );
};
