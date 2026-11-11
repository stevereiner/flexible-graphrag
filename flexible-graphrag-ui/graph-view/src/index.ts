/**
 * @flexible-graphrag/graph-view: a framework-free property-graph view on Cytoscape.js.
 *
 * No fetching, no auth, no framework code: the React / Vue / Angular Graph tabs fetch
 * /api/graph/subgraph themselves and hand the result to setGraph().
 */
import cytoscape from 'cytoscape';
import type { Core, ElementDefinition, Layouts, NodeSingular, SingularElementArgument } from 'cytoscape';
import dagre from 'cytoscape-dagre';
import fcose from 'cytoscape-fcose';

import { layoutOptions } from './layouts';
import { colorFor } from './palette';
import { stylesheet } from './style';
import type {
  GraphData, GraphEdge, GraphNode, GraphView, GraphViewEvent, GraphViewEventName,
  GraphViewOptions, LayoutName, Theme, TypeInfo,
} from './types';

export * from './types';
export { colorFor, PALETTE, ENTITY_COLOR } from './palette';

let registered = false;
function register(): void {
  if (registered) return;
  cytoscape.use(fcose);
  cytoscape.use(dagre);
  registered = true;
}

const BACKGROUND: Record<Theme, string> = { light: '#ffffff', dark: '#121212' };

export function createGraphView(container: HTMLElement, options: GraphViewOptions = {}): GraphView {
  register();
  let layout: LayoutName = options.layout ?? 'force';
  let theme: Theme = options.theme ?? 'light';
  const maxLabel = options.maxLabelLength ?? 28;
  const hiddenTypes = new Set<string>();
  const hiddenRels = new Set<string>();
  let chunksVisible = true;
  const listeners: Record<GraphViewEventName, Set<(e: GraphViewEvent) => void>> = {
    select: new Set(), expand: new Set(), background: new Set(),
  };
  let running: Layouts | null = null;

  const cy: Core = cytoscape({
    container,
    style: stylesheet(theme),
    minZoom: 0.05,
    maxZoom: 4,
    wheelSensitivity: 0.3,
    boxSelectionEnabled: false,
  });

  const emit = (name: GraphViewEventName, e: GraphViewEvent) => listeners[name].forEach((fn) => fn(e));

  const caption = (s: string) => (s.length > maxLabel ? s.slice(0, maxLabel - 1) + '…' : s);

  const nodeElement = (n: GraphNode): ElementDefinition => ({
    group: 'nodes',
    data: { id: n.id, caption: caption(n.label || n.id), type: n.type, kind: n.kind ?? 'entity',
            color: colorFor(n.type), raw: n },
  });

  const edgeElement = (e: GraphEdge): ElementDefinition => ({
    group: 'edges',
    data: { id: e.id, source: e.source, target: e.target, type: e.type, kind: e.kind ?? 'fact',
            raw: { ...e, doc_ids: [...(e.doc_ids ?? [])] } },
  });

  const isChunk = (el: SingularElementArgument) => el.data('kind') === 'chunk';

  /** Hidden: entities of a hidden type, chunks when chunks are off, relationships (MENTIONS
   *  included) of a hidden type; an edge also disappears with either end. */
  const applyVisibility = () => {
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        n.toggleClass('hidden', isChunk(n) ? !chunksVisible : hiddenTypes.has(n.data('type')));
      });
      cy.edges().forEach((e) => {
        e.toggleClass('hidden', hiddenRels.has(e.data('type')));
      });
    });
  };

  /** After showing something: lay out again, keeping what is placed roughly where it is. */
  const shown = (visible: boolean) => {
    applyVisibility();
    if (visible) run(false);
  };

  const count = (els: { forEach(fn: (el: SingularElementArgument) => void): unknown }, visible: (t: string) => boolean, color: (t: string) => string) => {
    const counts = new Map<string, number>();
    els.forEach((el) => {
      const t = el.data('type') as string;
      counts.set(t, (counts.get(t) ?? 0) + 1);
    });
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([type, n]) => ({ type, count: n, color: color(type), visible: visible(type) }));
  };

  const highlight = (center: SingularElementArgument | null) => {
    cy.batch(() => {
      if (!center) {
        cy.elements().removeClass('faded');
        return;
      }
      const keep = center.isNode() ? center.closedNeighborhood() : center.union(center.connectedNodes());
      cy.elements().addClass('faded');
      keep.removeClass('faded');
    });
  };

  const run = (randomize: boolean) => {
    running?.stop();
    running = cy.elements(':visible').layout(layoutOptions(layout, cy.nodes().length, randomize));
    running.run();
  };

  const zoomBy = (factor: number) => {
    const level = Math.min(cy.maxZoom(), Math.max(cy.minZoom(), cy.zoom() * factor));
    cy.animate({ zoom: { level, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }, duration: 150 });
  };

  /** Adds what is missing; returns the nodes that were new. */
  const add = (data: GraphData) => {
    const known = new Set(cy.nodes().map((n) => n.id()));
    const fresh: ElementDefinition[] = [];
    for (const n of data.nodes ?? []) {
      if (!known.has(n.id)) {
        fresh.push(nodeElement(n));
        known.add(n.id);
      }
    }
    for (const e of data.edges ?? []) {
      if (!known.has(e.source) || !known.has(e.target)) continue;
      const existing = cy.getElementById(e.id);
      if (existing.nonempty()) {
        const raw = existing.data('raw') as GraphEdge;
        for (const d of e.doc_ids ?? []) if (!raw.doc_ids.includes(d)) raw.doc_ids.push(d);
      } else {
        fresh.push(edgeElement(e));
      }
    }
    return cy.add(fresh).nodes();
  };

  cy.on('tap', 'node', (evt) => {
    const n = evt.target as NodeSingular;
    highlight(n);
    emit('select', { kind: 'node', id: n.id(), node: n.data('raw') });
  });
  cy.on('tap', 'edge', (evt) => {
    highlight(evt.target);
    emit('select', { kind: 'edge', id: evt.target.id(), edge: evt.target.data('raw') });
  });
  cy.on('tap', (evt) => {
    if (evt.target === cy) {
      highlight(null);
      emit('background', { kind: 'background' });
    }
  });
  cy.on('dbltap', 'node', (evt) => {
    const n = evt.target as NodeSingular;
    emit('expand', { kind: 'node', id: n.id(), node: n.data('raw') });
  });

  return {
    setGraph(data) {
      running?.stop();
      cy.batch(() => {
        cy.elements().remove();
        add(data);
      });
      applyVisibility();
      run(true);
    },

    mergeGraph(data) {
      const fresh = add(data);
      applyVisibility();
      if (fresh.empty()) return;
      // Start new nodes next to a node they connect to, so the layout grows outward from there.
      fresh.forEach((n) => {
        const anchor = n.neighborhood('node').difference(fresh).first() as NodeSingular;
        if (anchor.nonempty()) {
          const p = anchor.position();
          n.position({ x: p.x + (Math.random() - 0.5) * 60, y: p.y + (Math.random() - 0.5) * 60 });
        }
      });
      run(false);
    },

    setLayout(name) {
      layout = name;
      run(true);
    },

    setTheme(next) {
      theme = next;
      cy.style(stylesheet(theme));
    },

    setTypeVisible(type, visible) {
      if (visible) hiddenTypes.delete(type);
      else hiddenTypes.add(type);
      shown(visible);
    },

    setAllTypesVisible(visible) {
      hiddenTypes.clear();
      if (!visible) cy.nodes().forEach((n) => { if (!isChunk(n)) hiddenTypes.add(n.data('type')); });
      shown(visible);
    },

    types(): TypeInfo[] {
      return count(cy.nodes().filter((n) => !isChunk(n)), (t) => !hiddenTypes.has(t), colorFor);
    },

    setRelationshipVisible(type, visible) {
      if (visible) hiddenRels.delete(type);
      else hiddenRels.add(type);
      shown(visible);
    },

    setAllRelationshipsVisible(visible) {
      hiddenRels.clear();
      if (!visible) cy.edges().forEach((e) => { hiddenRels.add(e.data('type')); });
      shown(visible);
    },

    relationshipTypes(): TypeInfo[] {
      // MENTIONS (chunk links) last, after the facts
      const all = count(cy.edges(), (t) => !hiddenRels.has(t), () => '');
      return [...all.filter((r) => r.type !== 'MENTIONS'), ...all.filter((r) => r.type === 'MENTIONS')];
    },

    setChunksVisible(visible) {
      chunksVisible = visible;
      shown(visible);
    },

    chunkCount: () => cy.nodes().filter((n) => isChunk(n)).length,

    setSelection(ids) {
      cy.batch(() => {
        cy.elements().unselect();
        ids.forEach((id) => cy.getElementById(id).select());
      });
      const sel = cy.$(':selected');
      const one = sel.length === 1 ? sel[0] : null;
      highlight(one);
      if (one?.isNode()) emit('select', { kind: 'node', id: one.id(), node: one.data('raw') });
      else if (one) emit('select', { kind: 'edge', id: one.id(), edge: one.data('raw') });
    },

    focus(ids) {
      const els = cy.collection();
      ids.forEach((id) => els.merge(cy.getElementById(id)));
      if (els.nonempty()) cy.animate({ fit: { eles: els.closedNeighborhood(), padding: 60 }, duration: 300 });
    },

    fit() {
      cy.fit(cy.elements(':visible'), 30);
    },

    zoomIn() {
      zoomBy(1.25);
    },

    zoomOut() {
      zoomBy(1 / 1.25);
    },

    resize() {
      cy.resize();
    },

    toPng() {
      return cy.png({ output: 'blob-promise', full: true, scale: 2, bg: BACKGROUND[theme] });
    },

    nodeCount: () => cy.nodes().length,
    edgeCount: () => cy.edges().length,

    on(event, fn) {
      listeners[event].add(fn);
      return () => listeners[event].delete(fn);
    },

    destroy() {
      running?.stop();
      Object.values(listeners).forEach((s) => s.clear());
      cy.destroy();
    },
  };
}
