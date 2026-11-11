import { createGraphView, type GraphData, type LayoutName, type TypeInfo } from '../src/index';

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const view = createGraphView($('graph'));
(window as any).view = view; // for poking from devtools
let scope: Record<string, unknown> = {};
let documents: GraphData['documents'] = {};
let dark = false;

async function post(path: string, body: unknown): Promise<GraphData> {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail ?? r.statusText);
  return j;
}

function status(g?: GraphData, extra = '') {
  const s = g ? `${g.store} · ${g.doc_count ?? '?'} docs${g.truncated ? ' · truncated' : ''}${g.message ? ' · ' + g.message : ''}` : '';
  const chunks = view.chunkCount();
  const nodes = `${view.nodeCount()} nodes` + (chunks ? ` (${view.nodeCount() - chunks} entities, ${chunks} chunks)` : '');
  $('status').textContent = `${nodes} · ${view.edgeCount()} relationships · ${s} ${extra}`;
}

function notice(text: string) {
  $('notice').textContent = text;
  $('notice').style.display = text ? 'block' : 'none';
}

function checklist(el: HTMLElement, items: TypeInfo[], toggle: (type: string, on: boolean) => void) {
  el.innerHTML = '';
  for (const t of items) {
    const label = document.createElement('label');
    label.className = 'type';
    const swatch = t.color ? `<span class="swatch" style="background:${t.color}"></span>` : '';
    label.innerHTML = `<input type="checkbox" ${t.visible ? 'checked' : ''}> ${swatch}${t.type} (${t.count})`;
    label.querySelector('input')!.addEventListener('change', (e) => toggle(t.type, (e.target as HTMLInputElement).checked));
    el.appendChild(label);
  }
}

function legend() {
  checklist($('legend'), view.types(), (t, on) => view.setTypeVisible(t, on));
  checklist($('rels'), view.relationshipTypes(), (t, on) => view.setRelationshipVisible(t, on));
  $('chunk-count').textContent = String(view.chunkCount());
  $('node-count').textContent = String(view.nodeCount());
  $('entity-count').textContent = String(view.nodeCount() - view.chunkCount());
  $('edge-count').textContent = String(view.edgeCount());
}

$('types-all').onclick = () => { view.setAllTypesVisible(true); legend(); };
$('types-none').onclick = () => { view.setAllTypesVisible(false); legend(); };
$('rels-all').onclick = () => { view.setAllRelationshipsVisible(true); legend(); };
$('rels-none').onclick = () => { view.setAllRelationshipsVisible(false); legend(); };
$<HTMLInputElement>('chunks-visible').onchange = (e) => view.setChunksVisible((e.target as HTMLInputElement).checked);

$('load').onclick = async () => {
  const by = $<HTMLSelectElement>('by').value;
  const value = $<HTMLInputElement>('value').value.trim();
  scope = by === 'doc_ids' ? { doc_ids: value.split(',').map((s) => s.trim()).filter(Boolean) } : { processing_id: value };
  try {
    const g = await post('/api/graph/subgraph', { ...scope, limit: Number($<HTMLInputElement>('limit').value),
                                                  include_chunks: true });
    documents = g.documents ?? {};
    view.setGraph(g);
    legend();
    status(g);
    notice(g.nodes.length ? '' : g.message || 'No graph for these documents.');
  } catch (e) {
    view.setGraph({ nodes: [], edges: [] });
    legend();
    $('status').textContent = '';
    notice(String(e));
  }
};

view.on('select', (e) => {
  if (e.kind === 'node' && e.node.kind === 'chunk') {  // a chunk: its text, readable
    const docs = (e.node.doc_ids ?? []).map((d) => String(documents?.[d]?.file_name ?? d)).join(', ');
    $('details').innerHTML = '';
    const head = document.createElement('div');
    head.textContent = `Chunk of ${docs}`;
    const text = document.createElement('pre');
    text.textContent = String(e.node.properties.text ?? '');
    $('details').append(head, text);
    return;
  }
  // name / value rows, as the app tabs show them
  const rows: [string, unknown][] = e.kind === 'node'
    ? [['name', e.node.label], ['type', e.node.type], ...Object.entries(e.node.properties)]
    : e.kind === 'edge'
      ? [['relationship', `${e.edge.source} -${e.edge.type}-> ${e.edge.target}`], ...Object.entries(e.edge.properties),
         ['from', e.edge.doc_ids.map((d) => String(documents?.[d]?.file_name ?? d)).join(', ')]]
      : [];
  const table = document.createElement('table');
  table.style.fontSize = '12px';
  for (const [k, v] of rows) {
    const tr = table.insertRow();
    const name = tr.insertCell();
    name.textContent = k;
    name.style.cssText = 'opacity:.7; padding-right:8px; vertical-align:top';
    tr.insertCell().textContent = typeof v === 'string' ? v : JSON.stringify(v);
  }
  $('details').innerHTML = '';
  $('details').append(table);
});
view.on('background', () => ($('details').textContent = ''));
view.on('expand', async (e) => {
  if (e.kind !== 'node') return;
  try {
    const before = view.edgeCount();
    view.mergeGraph(await post('/api/graph/neighbors', { ...scope, node_id: e.id, limit: 100,
                                                         include_chunks: true }));
    legend();
    status(undefined, `· expanded ${e.node.label} (+${view.edgeCount() - before} edges)`);
  } catch (err) {
    $('status').textContent = String(err);
  }
});

$<HTMLSelectElement>('layout').onchange = (e) => view.setLayout((e.target as HTMLSelectElement).value as LayoutName);
$('fit').onclick = () => view.fit();
$('theme').onclick = () => {
  dark = !dark;
  document.body.classList.toggle('dark', dark);
  $('theme').textContent = dark ? 'Light' : 'Dark';
  view.setTheme(dark ? 'dark' : 'light');
};
$('png').onclick = async () => {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(await view.toPng());
  a.download = 'graph.png';
  a.click();
};
window.addEventListener('resize', () => view.resize());

const params = new URLSearchParams(location.search);
for (const by of ['processing_id', 'doc_ids']) {
  const preset = params.get(by);
  if (preset) {
    $<HTMLSelectElement>('by').value = by;
    $<HTMLInputElement>('value').value = preset;
    $('load').click();
    break;
  }
}
if (!params.get('processing_id') && !params.get('doc_ids')) {
  notice('Pick processing_id or doc_ids, paste the id(s), press Load.');
}
