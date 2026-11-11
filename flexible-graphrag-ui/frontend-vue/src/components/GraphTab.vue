<template>
  <div class="pa-2">
    <!-- Toolbar -->
    <div class="d-flex align-center flex-wrap ga-1 mb-2">
      <div class="text-body-2 flex-grow-1" style="min-width: 200px">
        <template v-if="request">Graph for: <strong>{{ request.label }}</strong></template>
        <template v-else>No graph selected</template>
        <span v-if="data" class="text-medium-emphasis">
          · {{ counts.nodes }} nodes<template v-if="counts.chunks"> ({{ counts.nodes - counts.chunks }} entities, {{ counts.chunks }} chunks)</template>
          · {{ counts.edges }} relationships · {{ data.store }} · {{ data.doc_count ?? 0 }} document(s)
        </span>
      </div>
      <v-select v-model="layout" :items="layouts" item-title="title" item-value="value" density="compact"
                variant="outlined" hide-details style="max-width: 170px" />
      <v-btn icon="mdi-magnify-plus-outline" size="small" variant="text" title="Zoom in" @click="view?.zoomIn()" />
      <v-btn icon="mdi-magnify-minus-outline" size="small" variant="text" title="Zoom out" @click="view?.zoomOut()" />
      <v-btn icon="mdi-fit-to-screen-outline" size="small" variant="text" title="Fit to screen" @click="view?.fit()" />
      <v-btn icon="mdi-refresh" size="small" variant="text" title="Reload" :disabled="!request || loading" @click="load" />
      <v-btn icon="mdi-download" size="small" variant="text" title="Save as PNG" :disabled="!counts.nodes" @click="savePng" />
      <v-btn icon="mdi-dock-right" size="small" variant="text" :color="panelOpen ? 'primary' : undefined"
             :title="panelOpen ? 'Hide side panel' : 'Show side panel'" @click="panelOpen = !panelOpen" />
    </div>

    <v-alert v-if="data?.truncated" type="warning" variant="tonal" density="compact" class="mb-2">
      Showing the first part of a large graph. Double-click a node to expand its neighbours.
    </v-alert>
    <v-alert v-if="data?.unsigned?.length" type="info" variant="tonal" density="compact" class="mb-2">
      Documents from {{ data.unsigned.join(', ') }} are left out: sign in to include them.
    </v-alert>

    <div class="graph-frame">
      <!-- Canvas -->
      <div class="graph-canvas">
        <div ref="container" style="position: absolute; inset: 0"></div>
        <div v-if="loading || error || !request || empty" class="graph-overlay">
          <v-progress-circular v-if="loading" indeterminate color="primary" />
          <div v-else :class="error ? 'text-error' : 'text-medium-emphasis'">
            {{ error || (!request
              ? 'Use “View graph” on the Processing tab (after an ingest), on Hybrid Search results or on AI Chat replies.'
              : data?.message || 'No graph for these documents.') }}
          </div>
        </div>
      </div>

      <!-- Side panel -->
      <div v-if="panelOpen" class="graph-panel">
        <!-- Details first: what was clicked stays in view without scrolling past the lists -->
        <div class="section-title" @click="open.details = !open.details">{{ open.details ? '▾' : '▸' }} Details</div>
        <div v-if="open.details" class="pl-2 text-body-2">
          <div v-if="!selected" class="text-medium-emphasis">
            Click a node or relationship. Double-click a node to expand its neighbours.
          </div>
          <template v-else-if="selected.kind === 'node' && selected.node.kind === 'chunk'">
            <div><strong>Chunk</strong> of {{ docNames(selected.node.doc_ids) }}</div>
            <pre class="chunk-text">{{ selected.node.properties.text }}</pre>
          </template>
          <template v-else-if="selected.kind === 'node'">
            <div><strong>{{ selected.node.label }}</strong></div>
            <div class="text-caption text-medium-emphasis">{{ selected.node.type }}</div>
            <table class="props"><tbody>
              <tr v-for="(v, k) in selected.node.properties" :key="k"><td class="prop-name">{{ k }}</td><td>{{ show(v) }}</td></tr>
            </tbody></table>
          </template>
          <template v-else-if="selected.kind === 'edge'">
            <div style="word-break: break-word">
              {{ selected.edge.source.startsWith('chunk:') ? 'Chunk' : selected.edge.source }}
              <strong>-{{ selected.edge.type }}→</strong> {{ selected.edge.target }}
            </div>
            <table class="props"><tbody>
              <tr v-for="(v, k) in selected.edge.properties" :key="k"><td class="prop-name">{{ k }}</td><td>{{ show(v) }}</td></tr>
            </tbody></table>
            <div v-if="selected.edge.doc_ids?.length" class="mt-1">From: {{ docNames(selected.edge.doc_ids) }}</div>
          </template>
        </div>
        <v-divider class="my-2" />

        <div class="section-title" @click="open.nodes = !open.nodes">{{ open.nodes ? '▾' : '▸' }} Nodes ({{ counts.nodes }})</div>
        <div v-if="open.nodes" class="pl-2">
          <div class="d-flex align-center text-body-2 my-1">
            <span class="flex-grow-1">Entities ({{ counts.nodes - counts.chunks }})</span>
            <v-btn size="x-small" variant="text" color="primary" @click="act(() => view?.setAllTypesVisible(true))">All</v-btn>
            <v-btn size="x-small" variant="text" color="primary" @click="act(() => view?.setAllTypesVisible(false))">None</v-btn>
          </div>
          <div class="type-list">
            <label v-for="t in types" :key="t.type" class="type-row">
              <input type="checkbox" :checked="t.visible" @change="act(() => view?.setTypeVisible(t.type, ($event.target as HTMLInputElement).checked))" />
              <span class="swatch" :style="{ background: t.color }"></span>{{ t.type }} ({{ t.count }})
            </label>
          </div>
          <label v-if="counts.chunks" class="type-row mt-1">
            <input type="checkbox" :checked="chunksVisible" @change="toggleChunks(($event.target as HTMLInputElement).checked)" />
            <span class="swatch" style="background: #9aa1a9; border-radius: 2px"></span>Chunks ({{ counts.chunks }})
          </label>
        </div>
        <v-divider class="my-2" />

        <div class="section-title" @click="open.rels = !open.rels">{{ open.rels ? '▾' : '▸' }} Relationships ({{ counts.edges }})</div>
        <div v-if="open.rels" class="pl-2">
          <div class="d-flex justify-end">
            <v-btn size="x-small" variant="text" color="primary" @click="act(() => view?.setAllRelationshipsVisible(true))">All</v-btn>
            <v-btn size="x-small" variant="text" color="primary" @click="act(() => view?.setAllRelationshipsVisible(false))">None</v-btn>
          </div>
          <div class="type-list">
            <label v-for="t in rels" :key="t.type" class="type-row">
              <input type="checkbox" :checked="t.visible" @change="act(() => view?.setRelationshipVisible(t.type, ($event.target as HTMLInputElement).checked))" />
              {{ t.type }} ({{ t.count }})
            </label>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, nextTick, onBeforeUnmount, onMounted, PropType, reactive, ref, shallowRef, watch } from 'vue';
import axios from 'axios';
import type { GraphData, GraphView, GraphViewEvent, LayoutName, TypeInfo } from '@flexible-graphrag/graph-view';

/** What the Graph tab shows: one ingest job's documents, or a list of doc ids. `key` changes on
 *  every request, so the same scope can be shown again. */
export interface GraphRequest {
  key: number;
  label: string;
  body: { processing_id?: string; doc_ids?: string[] };
}

type Selected = Extract<GraphViewEvent, { kind: 'node' } | { kind: 'edge' }> | null;

const errorText = (err: unknown) =>
  axios.isAxiosError(err) ? err.response?.data?.detail || err.message : String(err);

export default defineComponent({
  name: 'GraphTab',
  props: {
    request: { type: Object as PropType<GraphRequest | null>, default: null },
    /** The Graph tab is the selected tab (it stays mounted, hidden, so the graph keeps its layout). */
    active: { type: Boolean, default: false },
    isDarkMode: { type: Boolean, default: false },
  },
  setup(props) {
    const container = ref<HTMLDivElement | null>(null);
    const view = shallowRef<GraphView | null>(null);
    const data = ref<GraphData | null>(null);
    const loading = ref(false);
    const error = ref('');
    const layout = ref<LayoutName>('force');
    const layouts = [
      { title: 'Force', value: 'force' },
      { title: 'Hierarchical', value: 'hierarchical' },
      { title: 'Concentric', value: 'concentric' },
    ];
    const selected = shallowRef<Selected>(null);
    const panelOpen = ref(true);
    const open = reactive({ details: true, nodes: true, rels: true });
    const chunksVisible = ref(true);
    const rev = ref(0);  // bumped when the view's contents change: re-read its lists

    const types = computed<TypeInfo[]>(() => (rev.value, view.value ? view.value.types() : []));
    const rels = computed<TypeInfo[]>(() => (rev.value, view.value ? view.value.relationshipTypes() : []));
    const counts = computed(() => {
      void rev.value;
      const v = view.value;
      return { nodes: v ? v.nodeCount() : 0, edges: v ? v.edgeCount() : 0, chunks: v ? v.chunkCount() : 0 };
    });
    const empty = computed(() => !loading.value && !error.value && !!props.request && !!data.value && data.value.nodes.length === 0);

    const act = (fn: () => void) => { fn(); rev.value++; };
    const toggleChunks = (on: boolean) => { chunksVisible.value = on; act(() => view.value?.setChunksVisible(on)); };

    const docNames = (ids?: string[]) => (ids || []).map((id) => {
      const m = data.value?.documents?.[id] || {};
      return String(m.file_name || m.title || m.file_path || id);
    }).join(', ');
    const show = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v));

    const load = async () => {
      const v = view.value;
      if (!v || !props.request) return;
      loading.value = true;
      error.value = '';
      selected.value = null;
      try {
        const res = await axios.post<GraphData>('/api/graph/subgraph', { ...props.request.body, include_chunks: true });
        data.value = res.data;
        v.setGraph(res.data);
        v.setChunksVisible(chunksVisible.value);
      } catch (err) {
        data.value = null;
        v.setGraph({ nodes: [], edges: [] });
        error.value = errorText(err);
      } finally {
        loading.value = false;
        rev.value++;
      }
    };

    const expand = async (e: GraphViewEvent) => {
      if (e.kind !== 'node' || !props.request || !view.value) return;
      try {
        const res = await axios.post<GraphData>('/api/graph/neighbors',
          { ...props.request.body, node_id: e.id, include_chunks: true, limit: 100 });
        if (data.value) data.value = { ...data.value, documents: { ...data.value.documents, ...res.data.documents } };
        view.value.mergeGraph(res.data);
        rev.value++;
      } catch (err) {
        error.value = errorText(err);
      }
    };

    const savePng = async () => {
      if (!view.value) return;
      const a = document.createElement('a');
      a.href = URL.createObjectURL(await view.value.toPng());
      a.download = 'graph.png';
      a.click();
    };

    // Cytoscape is loaded once, in its own chunk
    onMounted(async () => {
      const { createGraphView } = await import('@flexible-graphrag/graph-view');
      if (!container.value) return;
      const v = createGraphView(container.value, { theme: props.isDarkMode ? 'dark' : 'light' });
      v.on('select', (e) => { selected.value = e as Selected; });
      v.on('background', () => { selected.value = null; });
      v.on('expand', expand);
      view.value = v;
      if (props.request) load();
    });
    onBeforeUnmount(() => {
      view.value?.destroy();
      view.value = null;
    });

    watch(() => props.request?.key, () => { if (props.request) load(); });
    watch(() => props.isDarkMode, (dark) => view.value?.setTheme(dark ? 'dark' : 'light'));
    watch(layout, (l) => view.value?.setLayout(l));
    // A hidden container has no size: re-measure (and fit) when the tab is shown
    watch(() => props.active, async (on) => {
      if (!on) return;
      await nextTick();
      requestAnimationFrame(() => { view.value?.resize(); view.value?.fit(); });
    });
    // Side panel shown / hidden: the canvas changed width; keep the user's zoom
    watch(panelOpen, async () => {
      await nextTick();
      view.value?.resize();
    });

    return {
      container, view, data, loading, error, layout, layouts, selected, panelOpen, open, chunksVisible,
      types, rels, counts, empty, act, toggleChunks, docNames, show, load, savePng,
    };
  },
});
</script>

<style scoped>
.graph-frame {
  display: flex;
  height: calc(100vh - 300px);
  min-height: 480px;
  border: 1px solid rgba(128, 128, 128, 0.35);
  border-radius: 4px;
}
.graph-canvas { position: relative; flex: 1; min-width: 0; }
.graph-overlay {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  pointer-events: none; padding: 32px; text-align: center;
}
.graph-panel {
  width: 300px; flex-shrink: 0; overflow: auto; padding: 12px;
  border-left: 1px solid rgba(128, 128, 128, 0.35);
}
.section-title { font-weight: 500; font-size: 14px; cursor: pointer; user-select: none; }
.type-list { max-height: 28vh; overflow: auto; }
.type-row { display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer; }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 50%; }
.props { font-size: 12px; border-collapse: collapse; margin-top: 4px; width: 100%; }
.props td { vertical-align: top; word-break: break-word; }
.prop-name { opacity: 0.7; padding-right: 8px; white-space: nowrap; }
.chunk-text { white-space: pre-wrap; word-break: break-word; font-size: 12px; margin-top: 4px; font-family: inherit; }
</style>
