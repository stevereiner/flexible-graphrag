import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Divider,
  FormControlLabel,
  IconButton,
  MenuItem,
  Select,
  Tooltip,
  Typography,
} from '@mui/material';
import { Theme } from '@mui/material/styles';
import ZoomInIcon from '@mui/icons-material/ZoomIn';
import ZoomOutIcon from '@mui/icons-material/ZoomOut';
import FitScreenIcon from '@mui/icons-material/FitScreen';
import RefreshIcon from '@mui/icons-material/Refresh';
import DownloadIcon from '@mui/icons-material/Download';
import ViewSidebarIcon from '@mui/icons-material/ViewSidebar';
import axios from 'axios';
import type { GraphData, GraphView, GraphViewEvent, LayoutName, TypeInfo } from '@flexible-graphrag/graph-view';
import { GraphRequest } from '../types/api';

interface GraphTabProps {
  currentTheme: Theme;
  isDarkMode: boolean;
  /** The Graph tab is the selected tab (it stays mounted, hidden, so the graph keeps its layout). */
  active: boolean;
  request: GraphRequest | null;
}

type Selected = Extract<GraphViewEvent, { kind: 'node' } | { kind: 'edge' }> | null;

const errorText = (err: unknown) =>
  axios.isAxiosError(err) ? err.response?.data?.detail || err.message : String(err);

/** One document's display name from the response's `documents` map. */
const docName = (docs: GraphData['documents'], id: string) => {
  const m = docs?.[id] || {};
  return String(m.file_name || m.title || m.file_path || id);
};

const Section: React.FC<{ title: string; open: boolean; onToggle: () => void; children: React.ReactNode }> =
  ({ title, open, onToggle, children }) => (
    <Box sx={{ mb: 1 }}>
      <Typography variant="subtitle2" onClick={onToggle} sx={{ cursor: 'pointer', userSelect: 'none' }}>
        {open ? '▾' : '▸'} {title}
      </Typography>
      {open && <Box sx={{ pl: 1 }}>{children}</Box>}
    </Box>
  );

const TypeList: React.FC<{ items: TypeInfo[]; onToggle: (type: string, on: boolean) => void }> =
  ({ items, onToggle }) => (
    <Box sx={{ maxHeight: '28vh', overflow: 'auto' }}>
      {items.map((t) => (
        <FormControlLabel
          key={t.type}
          sx={{ display: 'flex', m: 0, '& .MuiFormControlLabel-label': { fontSize: 13 } }}
          control={<Checkbox size="small" sx={{ p: 0.25 }} checked={t.visible}
                             onChange={(e) => onToggle(t.type, e.target.checked)} />}
          label={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              {t.color && <Box sx={{ width: 10, height: 10, borderRadius: '50%', bgcolor: t.color }} />}
              {t.type} ({t.count})
            </Box>
          }
        />
      ))}
    </Box>
  );

export const GraphTab: React.FC<GraphTabProps> = ({ currentTheme, isDarkMode, active, request }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<GraphView | null>(null);
  // Bumped each time a view is created (also on a hot reload), so the effects below re-attach
  const [ready, setReady] = useState(0);
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [layout, setLayout] = useState<LayoutName>('force');
  const [selected, setSelected] = useState<Selected>(null);
  const [panelOpen, setPanelOpen] = useState(true);
  const [open, setOpen] = useState({ nodes: true, rels: true, details: true });
  const [chunksVisible, setChunksVisible] = useState(true);
  const [rev, setRev] = useState(0);  // bumped when the view's contents change: re-read its lists
  const bump = () => setRev((r) => r + 1);

  // Cytoscape is loaded only when the app starts (not on every tab switch), in its own chunk
  useEffect(() => {
    let disposed = false;
    import('@flexible-graphrag/graph-view').then(({ createGraphView }) => {
      if (disposed || !containerRef.current) return;
      const view = createGraphView(containerRef.current, { theme: isDarkMode ? 'dark' : 'light' });
      view.on('select', (e) => setSelected(e as Selected));
      view.on('background', () => setSelected(null));
      viewRef.current = view;
      if (import.meta.env.DEV) (window as any).fgGraphView = view;  // poke from devtools
      setReady((n) => n + 1);
    });
    return () => {
      disposed = true;
      viewRef.current?.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    viewRef.current?.setTheme(isDarkMode ? 'dark' : 'light');
  }, [isDarkMode, ready]);

  // A hidden container has no size: re-measure (and fit) when the tab is shown
  useEffect(() => {
    if (!active || !viewRef.current) return;
    const id = requestAnimationFrame(() => {
      viewRef.current?.resize();
      viewRef.current?.fit();
    });
    return () => cancelAnimationFrame(id);
  }, [active, ready]);

  // Side panel shown / hidden: the canvas changed width; keep the user's zoom
  useEffect(() => {
    const id = requestAnimationFrame(() => viewRef.current?.resize());
    return () => cancelAnimationFrame(id);
  }, [panelOpen]);

  const load = useCallback(async () => {
    const view = viewRef.current;
    if (!view || !request) return;
    setLoading(true);
    setError('');
    setSelected(null);
    try {
      const res = await axios.post<GraphData>('/api/graph/subgraph', { ...request.body, include_chunks: true });
      setData(res.data);
      view.setGraph(res.data);
      view.setChunksVisible(chunksVisible);
    } catch (err) {
      setData(null);
      view.setGraph({ nodes: [], edges: [] });
      setError(errorText(err));
    } finally {
      setLoading(false);
      bump();
    }
  }, [request, chunksVisible]);

  // A new request (View graph on another tab) loads it
  useEffect(() => {
    if (ready && request) load();  // a new request, or a new view
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, request?.key]);

  // Double-click: the node's neighbours from the same documents
  useEffect(() => {
    const view = viewRef.current;
    if (!view || !request) return;
    return view.on('expand', async (e) => {
      if (e.kind !== 'node') return;
      try {
        const res = await axios.post<GraphData>('/api/graph/neighbors',
          { ...request.body, node_id: e.id, include_chunks: true, limit: 100 });
        setData((d) => d && { ...d, documents: { ...d.documents, ...res.data.documents } });
        view.mergeGraph(res.data);
        bump();
      } catch (err) {
        setError(errorText(err));
      }
    });
  }, [ready, request]);

  const view = viewRef.current;
  const types = view ? view.types() : [];
  const rels = view ? view.relationshipTypes() : [];
  const chunkCount = view ? view.chunkCount() : 0;
  const nodeCount = view ? view.nodeCount() : 0;
  const edgeCount = view ? view.edgeCount() : 0;
  void rev;

  const toggle = (fn: () => void) => { fn(); bump(); };

  const savePng = async () => {
    if (!view) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await view.toPng());
    a.download = 'graph.png';
    a.click();
  };

  const empty = !loading && !error && request && data && data.nodes.length === 0;
  const docs = data?.documents;

  return (
    <Box sx={{ p: 2 }}>
      {/* Toolbar */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', mb: 1 }}>
        <Typography variant="body2" sx={{ flexGrow: 1, minWidth: 200 }}>
          {request ? <>Graph for: <strong>{request.label}</strong></> : 'No graph selected'}
          {data && (
            <span style={{ opacity: 0.75 }}>
              {' · '}{nodeCount} nodes{chunkCount ? ` (${nodeCount - chunkCount} entities, ${chunkCount} chunks)` : ''}
              {' · '}{edgeCount} relationships · {data.store} · {data.doc_count ?? 0} document(s)
            </span>
          )}
        </Typography>
        <Select size="small" value={layout} sx={{ minWidth: 140 }}
                onChange={(e) => { const l = e.target.value as LayoutName; setLayout(l); view?.setLayout(l); }}>
          <MenuItem value="force">Force</MenuItem>
          <MenuItem value="hierarchical">Hierarchical</MenuItem>
          <MenuItem value="concentric">Concentric</MenuItem>
        </Select>
        <Tooltip title="Zoom in"><IconButton size="small" onClick={() => view?.zoomIn()}><ZoomInIcon /></IconButton></Tooltip>
        <Tooltip title="Zoom out"><IconButton size="small" onClick={() => view?.zoomOut()}><ZoomOutIcon /></IconButton></Tooltip>
        <Tooltip title="Fit to screen"><IconButton size="small" onClick={() => view?.fit()}><FitScreenIcon /></IconButton></Tooltip>
        <Tooltip title="Reload"><span>
          <IconButton size="small" onClick={load} disabled={!request || loading}><RefreshIcon /></IconButton>
        </span></Tooltip>
        <Tooltip title="Save as PNG"><span>
          <IconButton size="small" onClick={savePng} disabled={!nodeCount}><DownloadIcon /></IconButton>
        </span></Tooltip>
        <Tooltip title={panelOpen ? 'Hide side panel' : 'Show side panel'}>
          <IconButton size="small" onClick={() => setPanelOpen((o) => !o)} color={panelOpen ? 'primary' : 'default'}>
            <ViewSidebarIcon />
          </IconButton>
        </Tooltip>
      </Box>

      {data?.truncated && (
        <Alert severity="warning" sx={{ mb: 1 }}>
          Showing the first part of a large graph. Double-click a node to expand its neighbours.
        </Alert>
      )}
      {!!data?.unsigned?.length && (
        <Alert severity="info" sx={{ mb: 1 }}>
          Documents from {data.unsigned.join(', ')} are left out: sign in to include them.
        </Alert>
      )}

      <Box sx={{ display: 'flex', height: 'calc(100vh - 290px)', minHeight: 480,
                 border: 1, borderColor: 'divider', borderRadius: 1 }}>
        {/* Canvas */}
        <Box sx={{ position: 'relative', flex: 1, minWidth: 0 }}>
          <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
          {(loading || error || !request || empty) && (
            <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
                       justifyContent: 'center', pointerEvents: 'none', p: 4, textAlign: 'center' }}>
              {loading ? <CircularProgress /> : (
                <Typography color={error ? 'error' : 'text.secondary'}>
                  {error || (!request
                    ? 'Use "View graph" on the Processing tab (after an ingest) or on Hybrid Search results.'
                    : data?.message || 'No graph for these documents.')}
                </Typography>
              )}
            </Box>
          )}
        </Box>

        {/* Side panel */}
        {panelOpen && (
          <Box sx={{ width: 300, flexShrink: 0, borderLeft: 1, borderColor: 'divider', p: 1.5, overflow: 'auto',
                     bgcolor: currentTheme.palette.background.paper }}>
            {/* Details first: what was clicked stays in view without scrolling past the lists */}
            <Section title="Details" open={open.details}
                     onToggle={() => setOpen((o) => ({ ...o, details: !o.details }))}>
              <Details selected={selected} docs={docs} />
            </Section>
            <Divider sx={{ my: 1 }} />
            <Section title={`Nodes (${nodeCount})`} open={open.nodes}
                     onToggle={() => setOpen((o) => ({ ...o, nodes: !o.nodes }))}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, my: 0.5 }}>
                <Typography variant="body2" sx={{ flexGrow: 1 }}>Entities ({nodeCount - chunkCount})</Typography>
                <Button size="small" sx={{ minWidth: 0 }} onClick={() => toggle(() => view?.setAllTypesVisible(true))}>All</Button>
                <Button size="small" sx={{ minWidth: 0 }} onClick={() => toggle(() => view?.setAllTypesVisible(false))}>None</Button>
              </Box>
              <TypeList items={types} onToggle={(t, on) => toggle(() => view?.setTypeVisible(t, on))} />
              {chunkCount > 0 && (
                <FormControlLabel
                  sx={{ display: 'flex', m: 0, mt: 0.5, '& .MuiFormControlLabel-label': { fontSize: 13 } }}
                  control={<Checkbox size="small" sx={{ p: 0.25 }} checked={chunksVisible}
                                     onChange={(e) => { setChunksVisible(e.target.checked); toggle(() => view?.setChunksVisible(e.target.checked)); }} />}
                  label={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                      <Box sx={{ width: 10, height: 10, borderRadius: '2px', bgcolor: '#9aa1a9' }} />
                      Chunks ({chunkCount})
                    </Box>
                  }
                />
              )}
            </Section>
            <Divider sx={{ my: 1 }} />
            <Section title={`Relationships (${edgeCount})`} open={open.rels}
                     onToggle={() => setOpen((o) => ({ ...o, rels: !o.rels }))}>
              <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 0.5 }}>
                <Button size="small" sx={{ minWidth: 0 }} onClick={() => toggle(() => view?.setAllRelationshipsVisible(true))}>All</Button>
                <Button size="small" sx={{ minWidth: 0 }} onClick={() => toggle(() => view?.setAllRelationshipsVisible(false))}>None</Button>
              </Box>
              <TypeList items={rels} onToggle={(t, on) => toggle(() => view?.setRelationshipVisible(t, on))} />
            </Section>
          </Box>
        )}
      </Box>
    </Box>
  );
};

const Props: React.FC<{ props: Record<string, unknown> }> = ({ props }) => {
  const entries = Object.entries(props || {});
  if (!entries.length) return null;
  return (
    <Box component="table" sx={{ fontSize: 12, borderCollapse: 'collapse', mt: 0.5, width: '100%' }}>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k}>
            <Box component="td" sx={{ pr: 1, opacity: 0.7, verticalAlign: 'top', whiteSpace: 'nowrap' }}>{k}</Box>
            <Box component="td" sx={{ wordBreak: 'break-word' }}>{typeof v === 'string' ? v : JSON.stringify(v)}</Box>
          </tr>
        ))}
      </tbody>
    </Box>
  );
};

const Details: React.FC<{ selected: Selected; docs: GraphData['documents'] }> = ({ selected, docs }) => {
  if (!selected) {
    return <Typography variant="body2" sx={{ opacity: 0.75 }}>
      Click a node or relationship. Double-click a node to expand its neighbours.
    </Typography>;
  }
  if (selected.kind === 'node' && selected.node.kind === 'chunk') {
    const n = selected.node;
    return (
      <Box>
        <Typography variant="body2"><strong>Chunk</strong> of {(n.doc_ids || []).map((d) => docName(docs, d)).join(', ')}</Typography>
        <Typography variant="body2" component="pre"
                    sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, mt: 0.5 }}>
          {String(n.properties.text ?? '')}
        </Typography>
      </Box>
    );
  }
  if (selected.kind === 'node') {
    const n = selected.node;
    return (
      <Box>
        <Typography variant="body2"><strong>{n.label}</strong></Typography>
        <Typography variant="caption" sx={{ opacity: 0.75 }}>{n.type}</Typography>
        <Props props={n.properties} />
      </Box>
    );
  }
  const e = selected.edge;
  return (
    <Box>
      <Typography variant="body2" sx={{ wordBreak: 'break-word' }}>
        {e.source.startsWith('chunk:') ? 'Chunk' : e.source} <strong>-{e.type}→</strong> {e.target}
      </Typography>
      <Props props={e.properties} />
      {!!e.doc_ids?.length && (
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          From: {e.doc_ids.map((d) => docName(docs, d)).join(', ')}
        </Typography>
      )}
    </Box>
  );
};
