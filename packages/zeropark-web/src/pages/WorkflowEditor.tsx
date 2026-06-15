import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { 
  ReactFlow, 
  MiniMap, 
  Controls, 
  Background, 
  useNodesState, 
  useEdgesState, 
  addEdge
} from '@xyflow/react';
import type { Connection, Edge, Node } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { ArrowLeft, Save, Play, Settings, Trash2, CheckCircle, XCircle, MinusCircle, FolderOpen, Upload, Download, Rocket } from 'lucide-react';
import { API_BASE, authFetch, isAdmin } from '../api';

interface NodeRun {
  node_id: string;
  node_type: string;
  status: 'succeeded' | 'failed' | 'skipped';
  duration_ms: number;
  output_preview: string;
  error: string | null;
}

// Visual treatment per run status, applied onto the React Flow nodes so the
// canvas itself shows where the run broke.
const RUN_STYLES: Record<string, React.CSSProperties> = {
  succeeded: { border: '2px solid #10b981', boxShadow: '0 0 0 3px rgba(16,185,129,0.15)' },
  failed:    { border: '2px solid #ef4444', boxShadow: '0 0 0 3px rgba(239,68,68,0.2)' },
  skipped:   { border: '2px dashed #94a3b8', opacity: 0.55 },
};

const initialNodes: Node[] = [
  { id: '1', position: { x: 100, y: 100 }, data: { label: 'Start', type: 'trigger' }, type: 'input' },
];
const initialEdges: Edge[] = [];

const WorkflowEditor: React.FC = () => {
  const { appId } = useParams<{ appId: string }>();
  const navigate = useNavigate();
  
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executionLog, setExecutionLog] = useState<string | null>(null);
  const [nodeRuns, setNodeRuns] = useState<NodeRun[] | null>(null);
  const [lastRunId, setLastRunId] = useState<string | null>(null);

  // Saved workflows (server registry)
  const [savedList, setSavedList] = useState<{ id: string; name: string }[]>([]);
  const [showLoadPanel, setShowLoadPanel] = useState(false);
  const [currentWorkflowId, setCurrentWorkflowId] = useState<string | null>(null);
  const [workflowName, setWorkflowName] = useState('Untitled Workflow');
  const importInputRef = React.useRef<HTMLInputElement>(null);

  const fetchSaved = async () => {
    const res = await authFetch('/api/v1/workflow/saved');
    if (res.ok) setSavedList((await res.json()).workflows);
  };

  const handleSaveWorkflow = async () => {
    const name = window.prompt('워크플로 이름', workflowName);
    if (!name) return;
    setWorkflowName(name);
    const definition = { nodes, edges };
    const res = currentWorkflowId
      ? await authFetch(`/api/v1/workflow/saved/${currentWorkflowId}`, { method: 'PUT', body: JSON.stringify({ name, definition }) })
      : await authFetch('/api/v1/workflow/saved', { method: 'POST', body: JSON.stringify({ name, definition }) });
    if (res.ok) {
      const data = await res.json();
      setCurrentWorkflowId(data.id || currentWorkflowId);
      alert('저장되었습니다.');
    } else {
      alert('저장에 실패했습니다.');
    }
  };

  // Publish the current (saved) workflow as an App so users can run it from
  // the dashboard without opening the editor.
  const handlePublishAsApp = async () => {
    let wfId = currentWorkflowId;
    if (!wfId) {
      // must be saved first so the App can point at a stable definition
      const name = window.prompt('발행하려면 먼저 저장합니다. 워크플로 이름:', workflowName);
      if (!name) return;
      setWorkflowName(name);
      const saveRes = await authFetch('/api/v1/workflow/saved', {
        method: 'POST', body: JSON.stringify({ name, definition: { nodes, edges } })
      });
      if (!saveRes.ok) { alert('저장에 실패했습니다.'); return; }
      wfId = (await saveRes.json()).id;
      setCurrentWorkflowId(wfId);
    }
    const appName = window.prompt('앱 이름', workflowName) || workflowName;
    const res = await authFetch('/api/v1/apps', {
      method: 'POST',
      body: JSON.stringify({
        name: appName,
        mode: 'workflow',
        description: '발행된 워크플로 앱',
        params: { workflow_id: wfId },
        published: true,
      }),
    });
    if (res.ok) alert(`'${appName}' 앱으로 발행되었습니다. 대시보드에서 실행할 수 있습니다.`);
    else alert('발행에 실패했습니다 (admin 권한 필요).');
  };

  const handleLoadWorkflow = async (id: string) => {
    const res = await authFetch(`/api/v1/workflow/saved/${id}`);
    if (!res.ok) return;
    const data = await res.json();
    setNodes(data.definition.nodes || []);
    setEdges(data.definition.edges || []);
    setCurrentWorkflowId(data.id);
    setWorkflowName(data.name);
    setNodeRuns(null);
    setShowLoadPanel(false);
  };

  // When opened from a published workflow App (/dashboard/workflow/:appId),
  // resolve the app's workflow_id and load that saved definition.
  useEffect(() => {
    if (!appId) return;
    (async () => {
      const res = await authFetch(`/api/v1/apps/${appId}`);
      if (!res.ok) return;
      const app = await res.json();
      const wfId = app.params?.workflow_id;
      if (wfId) handleLoadWorkflow(wfId);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appId]);

  const handleExport = () => {
    const blob = new Blob(
      [JSON.stringify({ name: workflowName, definition: { nodes, edges } }, null, 2)],
      { type: 'application/json' }
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${workflowName.replace(/\s+/g, '_')}.workflow.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      const definition = parsed.definition || parsed; // accept bare {nodes,edges} too
      if (!definition.nodes) throw new Error('nodes 없음');
      setNodes(definition.nodes);
      setEdges(definition.edges || []);
      setWorkflowName(parsed.name || file.name.replace(/\.workflow\.json$/, ''));
      setCurrentWorkflowId(null); // imported = new document until saved
      setNodeRuns(null);
    } catch (err: any) {
      alert(`가져오기 실패: ${err.message}`);
    } finally {
      e.target.value = '';
    }
  };

  // When node selection changes
  const onSelectionChange = useCallback(({ nodes }: { nodes: Node[] }) => {
    setSelectedNode(nodes.length > 0 ? nodes[0] : null);
  }, []);

  const onConnect = useCallback((params: Connection) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

  const addNode = (type: string, label: string) => {
    const newNode: Node = {
      id: `${type}_${Date.now()}`,
      position: { x: Math.random() * 200 + 200, y: Math.random() * 200 + 100 },
      data: { label, type, prompt: '' },
    };
    setNodes((nds) => [...nds, newNode]);
  };

  const updateNodeData = (id: string, key: string, value: string) => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id === id) {
          const updatedNode = { ...n, data: { ...n.data, [key]: value } };
          // If this is the currently selected node, update its state too so the input reflects the change
          if (selectedNode && selectedNode.id === id) {
            setSelectedNode(updatedNode);
          }
          return updatedNode;
        }
        return n;
      })
    );
  };

  const deleteSelectedNode = () => {
    if (!selectedNode) return;
    // Remove the node
    setNodes((nds) => nds.filter((n) => n.id !== selectedNode.id));
    // Remove any edges connected to this node
    setEdges((eds) => eds.filter((e) => e.source !== selectedNode.id && e.target !== selectedNode.id));
    // Clear selection
    setSelectedNode(null);
  };

  // Paint run results onto the canvas: green = succeeded, red = failed,
  // grey dashed = skipped (downstream of a failure or an untaken branch).
  const applyRunStyles = useCallback((runs: NodeRun[]) => {
    const byId = new Map(runs.map(r => [r.node_id, r]));
    setNodes((nds) => nds.map((n) => {
      const run = byId.get(n.id);
      return { ...n, style: run ? { ...RUN_STYLES[run.status] } : {} };
    }));
  }, [setNodes]);

  const handleRunWorkflow = async () => {
    setIsExecuting(true);
    setExecutionLog(null);
    setNodeRuns(null);

    try {
      // Format nodes and edges to match backend Pydantic models exactly.
      // The visual 'trigger' start node maps to the engine's 'input' node.
      const formattedNodes = nodes.map(n => {
        const rawType = (n.data.type as string) || 'unknown';
        const engineType = rawType === 'trigger' ? 'input' : rawType;
        return { id: n.id, data: { ...n.data, type: engineType } };
      });

      const formattedEdges = edges.map((e) => ({
        source: e.source,
        target: e.target
      }));

      const res = await fetch(`${API_BASE}/api/v1/workflow/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          nodes: formattedNodes,
          edges: formattedEdges,
          initial_inputs: { trigger_time: new Date().toISOString() }
        })
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => null);
        throw new Error(errBody?.error?.message || errBody?.detail || `Failed to execute workflow: ${res.statusText}`);
      }

      const data = await res.json();
      const runs: NodeRun[] = data.node_runs || [];
      setNodeRuns(runs);
      setLastRunId(data.run_id || null);
      applyRunStyles(runs);
    } catch (err: any) {
      setExecutionLog(`Execution Failed:\n\n${err.message}`);
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div style={{ display: 'flex', height: '100%', margin: '-2rem', backgroundColor: 'var(--bg-color)' }}>
      {/* Sidebar Palette */}
      <div style={{ 
        width: '250px', 
        borderRight: '1px solid var(--border-color)', 
        backgroundColor: 'var(--surface-color)',
        display: 'flex', flexDirection: 'column'
      }}>
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button onClick={() => navigate('/dashboard')} style={{ color: 'var(--text-secondary)' }}>
            <ArrowLeft size={20} />
          </button>
          <h2 style={{ fontWeight: '600' }}>Workflow Builder</h2>
        </div>
        
        <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <h3 style={{ fontSize: '0.8rem', textTransform: 'uppercase', color: 'var(--text-secondary)', marginBottom: '0.5rem' }}>Add Nodes</h3>
          <button className="btn-secondary" onClick={() => addNode('llm', 'LLM Node')}>+ LLM Node</button>
          <button className="btn-secondary" onClick={() => addNode('sandbox', 'Python Sandbox')}>+ Python Sandbox</button>
          <button className="btn-secondary" onClick={() => addNode('crawl', 'Web Crawl')}>+ Web Crawl</button>
          <button className="btn-secondary" onClick={() => addNode('search', 'Web Search')}>+ Web Search</button>
          <button className="btn-secondary" onClick={() => addNode('browse', 'Browser (RPA)')}>+ Browser Use</button>
          <button className="btn-secondary" onClick={() => addNode('slides', 'Slides Generator')}>+ Slides Generator</button>
          <button className="btn-secondary" onClick={() => addNode('sheets', 'Sheets Manager')}>+ Sheets Manager</button>
          <button className="btn-secondary" onClick={() => addNode('mcp', 'Custom MCP Client')}>+ Custom MCP</button>
          <button className="btn-secondary" onClick={() => addNode('rag', 'Knowledge Retrieval')}>+ RAG Node</button>
        </div>
      </div>

      {/* Main Canvas Area */}
      <div style={{ flex: 1, position: 'relative' }}>
        <div style={{
          position: 'absolute', top: '1rem', right: '1rem', zIndex: 10,
          display: 'flex', gap: '0.5rem'
        }}>
          <button className="btn-secondary" onClick={handleSaveWorkflow} style={{ padding: '0.5rem 1rem' }}>
            <Save size={16} style={{marginRight:'0.5rem'}}/> Save
          </button>
          <button
            className="btn-secondary"
            onClick={async () => { await fetchSaved(); setShowLoadPanel(v => !v); }}
            style={{ padding: '0.5rem 1rem' }}
          >
            <FolderOpen size={16} style={{marginRight:'0.5rem'}}/> Load
          </button>
          <button className="btn-secondary" onClick={handleExport} title="JSON으로 내보내기" style={{ padding: '0.5rem 0.8rem' }}>
            <Download size={16} />
          </button>
          <button className="btn-secondary" onClick={() => importInputRef.current?.click()} title="JSON 가져오기" style={{ padding: '0.5rem 0.8rem' }}>
            <Upload size={16} />
          </button>
          <input ref={importInputRef} type="file" accept=".json" onChange={handleImportFile} style={{ display: 'none' }} />
          {isAdmin() && (
            <button className="btn-secondary" onClick={handlePublishAsApp} title="앱으로 발행 (대시보드에서 실행)" style={{ padding: '0.5rem 1rem' }}>
              <Rocket size={16} style={{marginRight:'0.5rem'}}/> Publish
            </button>
          )}
          <button className="btn-primary" onClick={handleRunWorkflow} disabled={isExecuting} style={{ padding: '0.5rem 1rem', display: 'flex', alignItems: 'center' }}>
            <Play size={16} style={{marginRight:'0.5rem'}}/> {isExecuting ? 'Running...' : 'Run'}
          </button>
        </div>

        {/* saved workflow list */}
        {showLoadPanel && (
          <div style={{
            position: 'absolute', top: '4rem', right: '1rem', zIndex: 20,
            width: '300px', maxHeight: '320px', overflowY: 'auto',
            backgroundColor: 'var(--surface-color)', border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', padding: '0.75rem'
          }}>
            <h4 style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '0.5rem' }}>저장된 워크플로</h4>
            {savedList.length === 0 && <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>저장된 워크플로가 없습니다.</span>}
            {savedList.map(w => (
              <div key={w.id} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <button
                  onClick={() => handleLoadWorkflow(w.id)}
                  style={{ flex: 1, textAlign: 'left', padding: '0.45rem 0.6rem', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', color: 'var(--text-primary)' }}
                  onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-color)'}
                  onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                >
                  {w.name}
                </button>
                <button
                  onClick={async () => {
                    if (!window.confirm(`'${w.name}' 삭제할까요?`)) return;
                    await authFetch(`/api/v1/workflow/saved/${w.id}`, { method: 'DELETE' });
                    fetchSaved();
                  }}
                  style={{ color: '#ef4444', padding: '0.3rem' }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </div>
        )}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onSelectionChange={onSelectionChange}
          fitView
        >
          <Controls />
          <MiniMap />
          <Background gap={12} size={1} color="var(--border-color)" />
        </ReactFlow>

        {/* Fatal error panel (request-level failure) */}
        {executionLog && (
          <div style={{
            position: 'absolute', bottom: '1rem', left: '1rem', right: '1rem', zIndex: 10,
            backgroundColor: 'var(--surface-color)',
            border: '1px solid rgba(239,68,68,0.4)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-lg)',
            padding: '1rem',
            maxHeight: '200px',
            overflowY: 'auto'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <h4 style={{ fontWeight: '600', fontSize: '0.9rem', color: '#ef4444' }}>Execution Error</h4>
              <button onClick={() => setExecutionLog(null)} style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>Close</button>
            </div>
            <pre style={{ fontSize: '0.85rem', fontFamily: 'monospace', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
              {executionLog}
            </pre>
          </div>
        )}

        {/* Per-node run results panel */}
        {nodeRuns && (
          <div style={{
            position: 'absolute', bottom: '1rem', left: '1rem', right: '1rem', zIndex: 10,
            backgroundColor: 'var(--surface-color)',
            border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-lg)',
            boxShadow: 'var(--shadow-lg)',
            padding: '1rem',
            maxHeight: '260px',
            overflowY: 'auto'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <h4 style={{ fontWeight: '600', fontSize: '0.9rem' }}>
                Run Result
                {nodeRuns.some(r => r.status === 'failed')
                  ? <span style={{ color: '#ef4444', marginLeft: '0.5rem' }}>— failed</span>
                  : <span style={{ color: '#10b981', marginLeft: '0.5rem' }}>— succeeded</span>}
                {lastRunId && <span style={{ color: 'var(--text-secondary)', fontWeight: 400, fontSize: '0.75rem', marginLeft: '0.75rem' }}>run {lastRunId.slice(0, 8)}</span>}
              </h4>
              <button onClick={() => { setNodeRuns(null); applyRunStyles([]); }} style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>Close</button>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {nodeRuns.map((run) => (
                <div
                  key={run.node_id}
                  onClick={() => {
                    const node = nodes.find(n => n.id === run.node_id);
                    if (node) setSelectedNode(node);
                  }}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: '0.6rem',
                    padding: '0.5rem 0.75rem', borderRadius: 'var(--radius-md)',
                    backgroundColor: run.status === 'failed' ? 'rgba(239,68,68,0.07)' : 'var(--bg-color)',
                    cursor: 'pointer', fontSize: '0.85rem'
                  }}
                >
                  {run.status === 'succeeded' && <CheckCircle size={16} style={{ color: '#10b981', flexShrink: 0, marginTop: '2px' }} />}
                  {run.status === 'failed' && <XCircle size={16} style={{ color: '#ef4444', flexShrink: 0, marginTop: '2px' }} />}
                  {run.status === 'skipped' && <MinusCircle size={16} style={{ color: '#94a3b8', flexShrink: 0, marginTop: '2px' }} />}
                  <div style={{ minWidth: 0 }}>
                    <span style={{ fontWeight: 600 }}>{run.node_id}</span>
                    <span style={{ color: 'var(--text-secondary)', marginLeft: '0.5rem' }}>{run.node_type} · {run.duration_ms}ms</span>
                    {run.error && (
                      <div style={{ color: '#ef4444', fontFamily: 'monospace', fontSize: '0.8rem', whiteSpace: 'pre-wrap', marginTop: '0.25rem' }}>
                        {run.error}
                      </div>
                    )}
                    {!run.error && run.output_preview && (
                      <div style={{ color: 'var(--text-secondary)', fontSize: '0.78rem', marginTop: '0.25rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {run.output_preview}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Properties Panel (Right side) */}
      {selectedNode && (
        <div style={{ 
          width: '300px', 
          borderLeft: '1px solid var(--border-color)', 
          backgroundColor: 'var(--surface-color)',
          padding: '1.5rem',
          display: 'flex', flexDirection: 'column', gap: '1rem',
          boxShadow: '-4px 0 15px rgba(0,0,0,0.05)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
            <Settings size={20} />
            <h3 style={{ fontWeight: '600' }}>Node Settings</h3>
          </div>
          
          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Node ID</label>
            <input type="text" value={selectedNode.id} disabled style={{ width: '100%', padding: '0.5rem', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '4px' }} />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Label</label>
            <input 
              type="text" 
              value={selectedNode.data.label as string} 
              onChange={(e) => updateNodeData(selectedNode.id, 'label', e.target.value)}
              style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px' }} 
            />
          </div>

          {selectedNode.data.type === 'llm' && (
            <div>
              <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>System Prompt</label>
              <textarea 
                rows={5}
                value={(selectedNode.data.prompt as string) || ''} 
                onChange={(e) => updateNodeData(selectedNode.id, 'prompt', e.target.value)}
                placeholder="Enter instructions for the LLM..."
                style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px', resize: 'vertical' }} 
              />
            </div>
          )}

          {selectedNode.data.type === 'sandbox' && (
            <div>
              <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Python Code</label>
              <textarea 
                rows={5}
                value={(selectedNode.data.code as string) || ''} 
                onChange={(e) => updateNodeData(selectedNode.id, 'code', e.target.value)}
                placeholder="print('Hello World')"
                style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px', fontFamily: 'monospace' }} 
              />
            </div>
          )}

          {selectedNode.data.type === 'crawl' && (
            <div>
              <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Target URL</label>
              <input 
                type="text" 
                value={(selectedNode.data.url as string) || ''} 
                onChange={(e) => updateNodeData(selectedNode.id, 'url', e.target.value)}
                placeholder="https://example.com"
                style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px' }} 
              />
            </div>
          )}

          {selectedNode.data.type === 'search' && (
            <div>
              <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Search Query</label>
              <input 
                type="text" 
                value={(selectedNode.data.query as string) || ''} 
                onChange={(e) => updateNodeData(selectedNode.id, 'query', e.target.value)}
                placeholder="Enter search keywords..."
                style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px' }} 
              />
            </div>
          )}

          {selectedNode.data.type === 'slides' && (
            <div>
              <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Presentation Prompt</label>
              <textarea 
                rows={4}
                value={(selectedNode.data.prompt as string) || ''} 
                onChange={(e) => updateNodeData(selectedNode.id, 'prompt', e.target.value)}
                placeholder="Make a 5-slide presentation about AI agents..."
                style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px', resize: 'vertical' }} 
              />
            </div>
          )}

          {selectedNode.data.type === 'sheets' && (
            <div>
              <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Spreadsheet Data Prompt</label>
              <textarea 
                rows={4}
                value={(selectedNode.data.prompt as string) || ''} 
                onChange={(e) => updateNodeData(selectedNode.id, 'prompt', e.target.value)}
                placeholder="Generate a table of top 5 tech companies and their stock tickers..."
                style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px', resize: 'vertical' }} 
              />
            </div>
          )}

          {selectedNode.data.type === 'browse' && (
            <div>
              <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Target URL</label>
              <input 
                type="text" 
                value={(selectedNode.data.url as string) || ''} 
                onChange={(e) => updateNodeData(selectedNode.id, 'url', e.target.value)}
                placeholder="https://example.com"
                style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px' }} 
              />
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.5rem' }}>* Loads JS and returns screenshot + text</p>
            </div>
          )}

          {selectedNode.data.type === 'mcp' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Command</label>
                <input 
                  type="text" 
                  value={(selectedNode.data.command as string) || ''} 
                  onChange={(e) => updateNodeData(selectedNode.id, 'command', e.target.value)}
                  placeholder="npx, uvx, python"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px' }} 
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Arguments</label>
                <input 
                  type="text" 
                  value={(selectedNode.data.args as string) || ''} 
                  onChange={(e) => updateNodeData(selectedNode.id, 'args', e.target.value)}
                  placeholder="-y @modelcontextprotocol/server-everything"
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px' }} 
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Tool Name</label>
                <input 
                  type="text" 
                  value={(selectedNode.data.toolName as string) || ''} 
                  onChange={(e) => updateNodeData(selectedNode.id, 'toolName', e.target.value)}
                  placeholder="echo, search, etc."
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px' }} 
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Tool Args (JSON)</label>
                <textarea 
                  rows={3}
                  value={(selectedNode.data.toolArgs as string) || ''} 
                  onChange={(e) => updateNodeData(selectedNode.id, 'toolArgs', e.target.value)}
                  placeholder='{"message": "Hello"}'
                  style={{ width: '100%', padding: '0.5rem', border: '1px solid var(--border-color)', borderRadius: '4px', resize: 'vertical' }} 
                />
              </div>
            </div>
          )}

          <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid var(--border-color)' }}>
            <button 
              onClick={deleteSelectedNode}
              style={{ 
                width: '100%', padding: '0.75rem', display: 'flex', alignItems: 'center', justifyContent: 'center', 
                gap: '0.5rem', backgroundColor: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', 
                border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 'var(--radius-md)',
                fontWeight: '600', cursor: 'pointer', transition: 'all 0.2s ease'
              }}
              onMouseOver={(e) => e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.2)'}
              onMouseOut={(e) => e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)'}
            >
              <Trash2 size={18} /> Delete Node
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default WorkflowEditor;
