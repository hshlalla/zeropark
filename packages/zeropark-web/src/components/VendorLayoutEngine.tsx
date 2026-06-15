import React from 'react';
import { ChatWidget } from './widgets/ChatWidget';
import { KnowledgeWidget } from './widgets/KnowledgeWidget';
import { StatsWidget } from './widgets/StatsWidget';
// custom slots mapping (lazy-load or direct import configuration)
import * as CustomSlots from '../custom-slots';

interface WidgetConfig {
  id: string;
  position?: string | { x: number; y: number; w: number; h: number };
}

interface LayoutConfig {
  type: string;
  widgets: WidgetConfig[];
}

interface VendorLayoutEngineProps {
  layout: LayoutConfig;
  appId?: string;
  appMode?: string;
  appParams?: Record<string, any>;
}

export const VendorLayoutEngine: React.FC<VendorLayoutEngineProps> = ({ layout, appId, appMode, appParams }) => {
  // Render widget instance by its ID
  const renderWidget = (widgetId: string) => {
    // Check if custom slots override the widget
    const SlotComponent = (CustomSlots as any)[`Custom_${widgetId}`] || (CustomSlots as any)[widgetId];
    if (SlotComponent) {
      return <SlotComponent appId={appId} appMode={appMode} appParams={appParams} />;
    }

    switch (widgetId) {
      case 'chat':
        return <ChatWidget appId={appId} appMode={appMode} appParams={appParams} />;
      case 'knowledge':
        return <KnowledgeWidget />;
      case 'stats':
        return <StatsWidget />;
      default:
        return <div style={{ padding: '1rem', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-md)' }}>Unknown Widget: {widgetId}</div>;
    }
  };

  const layoutType = layout?.type || 'default';
  const widgets = layout?.widgets || [];

  if (layoutType === 'grid') {
    // Basic CSS Grid layout representation
    return (
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(12, 1fr)',
        gap: '1.5rem',
        height: '100%',
        width: '100%',
        padding: '1rem'
      }}>
        {widgets.map((w, idx) => {
          let gridArea = 'span 4'; // fallback
          if (w.position && typeof w.position === 'object') {
            const pos = w.position;
            gridArea = `${pos.y + 1} / ${pos.x + 1} / span ${pos.h} / span ${pos.w}`;
          } else if (w.position === 'left') {
            gridArea = 'span 8';
          } else if (w.position?.startsWith('right')) {
            gridArea = 'span 4';
          }
          return (
            <div key={`${w.id}-${idx}`} style={{ gridArea, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
              {renderWidget(w.id)}
            </div>
          );
        })}
      </div>
    );
  }

  if (layoutType === 'columns') {
    // Double Column Flex Layout
    return (
      <div style={{
        display: 'flex',
        gap: '1.5rem',
        height: '100%',
        width: '100%',
        padding: '1rem'
      }}>
        <div style={{ flex: 2, display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
          {widgets.filter(w => w.position === 'left' || !w.position).map((w, idx) => (
            <div key={`${w.id}-${idx}`} style={{ flex: 1, height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              {renderWidget(w.id)}
            </div>
          ))}
        </div>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1.5rem', height: '100%', overflow: 'hidden' }}>
          {widgets.filter(w => w.position === 'right' || w.position === 'right_top' || w.position === 'right_bottom').map((w, idx) => (
            <div key={`${w.id}-${idx}`} style={{ flex: w.position === 'right' ? 1 : 'unset', height: w.position === 'right' ? '100%' : '50%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              {renderWidget(w.id)}
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Default Standard Chat Layout
  return (
    <div style={{ display: 'flex', height: '100%', width: '100%', justifyContent: 'center', overflow: 'hidden' }}>
      <div style={{ width: '100%', maxWidth: '900px', height: '100%', padding: '1rem', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {renderWidget('chat')}
      </div>
    </div>
  );
};
