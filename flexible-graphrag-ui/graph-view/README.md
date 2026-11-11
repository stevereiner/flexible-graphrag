# @flexible-graphrag/graph-view

Framework-free property-graph view for the Flexible GraphRAG **Graph** tab, built on
[Cytoscape.js](https://js.cytoscape.org/) (force layout via fcose, hierarchical via dagre).
Used by the React, Vue and Angular UIs and by `@flexible-graphrag/angular-ui`.

It does no fetching and no auth: the host app calls the backend
(`POST /api/graph/subgraph`, `POST /api/graph/neighbors`) and hands the result to the view.

```ts
import { createGraphView } from '@flexible-graphrag/graph-view';

const view = createGraphView(document.getElementById('graph')!, { layout: 'force', theme: 'light' });

const res = await fetch('/api/graph/subgraph', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ processing_id: '524d6f13', limit: 500 }),
});
view.setGraph(await res.json());

view.on('select', (e) => console.log(e));            // tap a node or edge
view.on('expand', async (e) => {                     // double-tap a node
  const r = await fetch('/api/graph/neighbors', { /* same scope + node_id: e.id */ });
  view.mergeGraph(await r.json());
});
```

API: `setGraph`, `mergeGraph`, `setLayout('force' | 'hierarchical' | 'concentric')`, `setTheme`,
`setTypeVisible` / `setAllTypesVisible` / `types()` (entity types, for a legend),
`setRelationshipVisible` / `setAllRelationshipsVisible` / `relationshipTypes()`,
`setChunksVisible` / `chunkCount()`, `setSelection`, `focus`, `fit`, `resize` (call when a hidden
tab becomes visible), `toPng`, `nodeCount`, `edgeCount`, `on`, `destroy`.

Chunks (requested with `include_chunks: true`) are nodes with `kind: 'chunk'`, drawn as small grey
squares; their MENTIONS edges to entities have `kind: 'mention'` and are drawn dashed.

Node colours are stable per type across views and apps (`colorFor(type)`).

## Develop

```bash
npm install
npm run build       # -> dist/
npm run demo        # http://localhost:5180, proxies /api to the backend on :8000
                    # http://localhost:5180/?processing_id=<job id> loads a job's graph
```

License: Apache-2.0.
