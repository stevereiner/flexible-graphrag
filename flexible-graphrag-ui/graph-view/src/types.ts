/** Shapes returned by POST /api/graph/subgraph and /api/graph/neighbors. */

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  properties: Record<string, unknown>;
  /** 'chunk' for a text chunk (include_chunks); entities have none. */
  kind?: 'chunk';
  /** A chunk's document(s). */
  doc_ids?: string[];
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  properties: Record<string, unknown>;
  /** Documents this relationship was extracted from (within the requested scope). */
  doc_ids: string[];
  /** 'mention' for a chunk -MENTIONS-> entity edge; facts have none. */
  kind?: 'mention';
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Per-document metadata (file_name, source, ...), sent once instead of on every element. */
  documents?: Record<string, Record<string, unknown>>;
  truncated?: boolean;
  store?: string;
  doc_count?: number;
  unsigned?: string[];
  message?: string;
}

export type LayoutName = 'force' | 'hierarchical' | 'concentric';
export type Theme = 'light' | 'dark';

export interface GraphViewOptions {
  layout?: LayoutName;
  theme?: Theme;
  /** Longest node caption before it is shortened with an ellipsis. */
  maxLabelLength?: number;
}

export interface TypeInfo {
  type: string;
  color: string;
  count: number;
  visible: boolean;
}

export type GraphViewEvent =
  | { kind: 'node'; id: string; node: GraphNode }
  | { kind: 'edge'; id: string; edge: GraphEdge }
  | { kind: 'background' };

export type GraphViewEventName = 'select' | 'expand' | 'background';

export interface GraphView {
  /** Replace everything shown. */
  setGraph(data: GraphData): void;
  /** Add nodes and edges (expand neighbours); existing ones keep their place. */
  mergeGraph(data: GraphData): void;
  setLayout(layout: LayoutName): void;
  setTheme(theme: Theme): void;
  /** Show or hide the entities of one type. */
  setTypeVisible(type: string, visible: boolean): void;
  setAllTypesVisible(visible: boolean): void;
  /** Entity types present (chunks not included), with their colour and count, for a legend. */
  types(): TypeInfo[];
  /** Show or hide the relationships of one type. */
  setRelationshipVisible(type: string, visible: boolean): void;
  setAllRelationshipsVisible(visible: boolean): void;
  /** Relationship types present (MENTIONS included when chunks are loaded), with their count. */
  relationshipTypes(): TypeInfo[];
  /** Show or hide the chunks and their MENTIONS edges. */
  setChunksVisible(visible: boolean): void;
  chunkCount(): number;
  /** Select these elements; with exactly one, a 'select' event fires as for a tap. */
  setSelection(ids: string[]): void;
  /** Center and zoom on these node ids. */
  focus(ids: string[]): void;
  fit(): void;
  /** Zoom around the centre of the view (factor 1.25 per step). */
  zoomIn(): void;
  zoomOut(): void;
  /** Call when a hidden tab becomes visible or the container is resized. */
  resize(): void;
  toPng(): Promise<Blob>;
  nodeCount(): number;
  edgeCount(): number;
  /** select: tap on a node or edge; expand: double-tap on a node; background: tap on empty space. */
  on(event: GraphViewEventName, fn: (e: GraphViewEvent) => void): () => void;
  destroy(): void;
}
