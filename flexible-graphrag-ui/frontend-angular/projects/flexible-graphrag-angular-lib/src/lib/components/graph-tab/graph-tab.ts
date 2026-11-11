import { AfterViewInit, ChangeDetectorRef, Component, ElementRef, Input, NgZone, OnChanges, OnDestroy,
         SimpleChanges, ViewChild, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import type { GraphData, GraphView, GraphViewEvent, LayoutName, TypeInfo } from '@flexible-graphrag/graph-view';
import { FlexibleGraphragConfigService } from '../../config.service';
import { AskScope, GraphScope } from '../../models/api.models';
import { SourceAuthService } from '../../services/source-auth.service';

type Selected = Extract<GraphViewEvent, { kind: 'node' } | { kind: 'edge' }> | null;

/**
 * The Graph tab: the property graph (entities, relationships, chunks) extracted from a set of
 * documents. The standalone app sets `graph` from other tabs' "View graph"; KG Spaces sets
 * `scope` to the selected document or folder (the same scope AI Chat takes).
 *
 * Cytoscape is loaded by dynamic import the first time the tab is created, and runs outside
 * Angular's zone (its pointer events would otherwise trigger change detection constantly).
 */
@Component({
  selector: 'app-graph-tab',
  templateUrl: './graph-tab.html',
  styleUrls: ['./graph-tab.scss'],
  standalone: false
})
export class GraphTabComponent implements AfterViewInit, OnChanges, OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private readonly sourceAuth = inject(SourceAuthService);
  private readonly zone = inject(NgZone);
  private readonly cdr = inject(ChangeDetectorRef);

  /** Which documents: a ingest job, doc ids, or a KG Spaces scope. */
  @Input() graph: GraphScope | null = null;
  /** Shown as "Graph for: <label>". */
  @Input() label = '';
  /** A new value shows `graph` again (e.g. "View graph" on the same scope twice). */
  @Input() requestKey: number | string = 0;
  /** KG Spaces: the selected document or folder (used when `graph` is not set). */
  @Input() scope: AskScope | null = null;
  /** Dark graph colours; unset: follow the library theme's `dark-theme` class on <body>. */
  @Input() darkMode: boolean | null = null;

  @ViewChild('canvas', { static: true }) canvas!: ElementRef<HTMLDivElement>;

  view: GraphView | null = null;
  data: GraphData | null = null;
  loading = false;
  error = '';
  layout: LayoutName = 'force';
  selected: Selected = null;
  panelOpen = true;
  open = { details: true, nodes: true, rels: true };
  chunksVisible = true;
  types: TypeInfo[] = [];
  rels: TypeInfo[] = [];
  counts = { nodes: 0, edges: 0, chunks: 0 };

  private resizeObserver?: ResizeObserver;
  private themeObserver?: MutationObserver;
  private wasHidden = true;
  private destroyed = false;

  /** What is shown: `graph`, else the KG Spaces scope. */
  get body(): GraphScope | null {
    if (this.graph) return this.graph;
    return this.scope ? { scope: this.scope } : null;
  }

  get title(): string {
    if (this.graph) return this.label || 'selected documents';
    return this.scope ? (this.scope.name || this.scope.path || 'selected item') : '';
  }

  get empty(): boolean {
    return !this.loading && !this.error && !!this.body && !!this.data && this.data.nodes.length === 0;
  }

  ngAfterViewInit(): void {
    // Cytoscape measures its container when created, so wait until the canvas is in the page and
    // has a size (a mat-tab's content can be initialised before it is attached). Afterwards: when
    // a hidden tab gets its size back, re-measure and fit; on other size changes (side panel,
    // window) only re-measure, keeping the user's zoom.
    this.zone.runOutsideAngular(() => {
      this.resizeObserver = new ResizeObserver(([entry]) => {
        const hidden = entry.contentRect.width === 0 || entry.contentRect.height === 0;
        const v = this.view;
        if (!hidden && !v && !this.starting) this.zone.run(() => this.start());
        if (!hidden && v) {
          v.resize();
          if (this.wasHidden) v.fit();
        }
        this.wasHidden = hidden;
      });
      this.resizeObserver.observe(this.canvas.nativeElement);
    });
  }

  private starting = false;

  private async start(): Promise<void> {
    this.starting = true;
    try {
      await this.createView();
    } catch (err) {
      console.error('Graph view could not start', err);
      this.error = 'The graph view could not start: ' + this.errorText(err);
      return;
    } finally {
      this.starting = false;
    }
    if (this.body) this.load();
  }

  private async createView(): Promise<void> {
    const { createGraphView } = await import('@flexible-graphrag/graph-view');
    if (this.destroyed) return;
    this.zone.runOutsideAngular(() => {
      const v = createGraphView(this.canvas.nativeElement, { theme: this.isDark() ? 'dark' : 'light' });
      v.on('select', (e) => this.zone.run(() => { this.selected = e as Selected; }));
      v.on('background', () => this.zone.run(() => { this.selected = null; }));
      v.on('expand', (e) => this.zone.run(() => this.expand(e)));
      this.view = v;
      this.themeObserver = new MutationObserver(() => v.setTheme(this.isDark() ? 'dark' : 'light'));
      this.themeObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    });
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['darkMode'] && this.view) this.view.setTheme(this.isDark() ? 'dark' : 'light');
    const what = changes['graph'] || changes['requestKey'] || changes['scope'];
    if (what && !what.firstChange && this.view) this.load();
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    this.resizeObserver?.disconnect();
    this.themeObserver?.disconnect();
    this.view?.destroy();
    this.view = null;
  }

  private isDark(): boolean {
    return this.darkMode ?? document.body.classList.contains('dark-theme');
  }

  /** Re-read the view's counts and type lists (after a load, merge or toggle). */
  private refresh(): void {
    const v = this.view;
    this.types = v ? v.types() : [];
    this.rels = v ? v.relationshipTypes() : [];
    this.counts = { nodes: v ? v.nodeCount() : 0, edges: v ? v.edgeCount() : 0, chunks: v ? v.chunkCount() : 0 };
  }

  /** POST with the library's sign-ins (source_auth / host headers); sign in again once on a 401. */
  private async post(path: string, body: object): Promise<GraphData> {
    await this.sourceAuth.beforeQuestion();
    const send = () => firstValueFrom(this.http.post<GraphData>(`${this.fgConfig.apiUrl}/graph/${path}`,
      this.fgConfig.questionBody(body), { headers: this.fgConfig.questionHeaders() }));
    try {
      return await send();
    } catch (err: any) {
      if (err?.status === 401 && await this.sourceAuth.afterUnauthorized()) return send();
      throw err;
    }
  }

  private errorText(err: any): string {
    return err?.error?.detail || err?.message || String(err);
  }

  async load(): Promise<void> {
    const v = this.view;
    const body = this.body;
    if (!v || !body) return;
    this.loading = true;
    this.error = '';
    this.selected = null;
    try {
      const data = await this.post('subgraph', { ...body, include_chunks: true });
      this.data = data;
      this.zone.runOutsideAngular(() => {
        v.setGraph(data);
        v.setChunksVisible(this.chunksVisible);
      });
    } catch (err) {
      this.data = null;
      this.zone.runOutsideAngular(() => v.setGraph({ nodes: [], edges: [] }));
      this.error = this.errorText(err);
    } finally {
      this.loading = false;
      this.refresh();
    }
  }

  /** Double-click: the node's neighbours from the same documents. */
  private async expand(e: GraphViewEvent): Promise<void> {
    const v = this.view;
    const body = this.body;
    if (e.kind !== 'node' || !v || !body) return;
    try {
      const data = await this.post('neighbors', { ...body, node_id: e.id, include_chunks: true, limit: 100 });
      if (this.data) this.data = { ...this.data, documents: { ...this.data.documents, ...data.documents } };
      this.zone.runOutsideAngular(() => v.mergeGraph(data));
      this.refresh();
    } catch (err) {
      this.error = this.errorText(err);
    }
  }

  /** Run a view call outside the zone, then re-read the lists. */
  act(fn: (v: GraphView) => void): void {
    const v = this.view;
    if (!v) return;
    this.zone.runOutsideAngular(() => fn(v));
    this.refresh();
  }

  setLayout(layout: LayoutName): void {
    this.layout = layout;
    this.act((v) => v.setLayout(layout));
  }

  setAllTypes(on: boolean): void { this.act((v) => v.setAllTypesVisible(on)); }
  typeToggle(type: string, on: boolean): void { this.act((v) => v.setTypeVisible(type, on)); }
  setAllRels(on: boolean): void { this.act((v) => v.setAllRelationshipsVisible(on)); }
  relToggle(type: string, on: boolean): void { this.act((v) => v.setRelationshipVisible(type, on)); }

  toggleChunks(on: boolean): void {
    this.chunksVisible = on;
    this.act((v) => v.setChunksVisible(on));
  }

  togglePanel(): void {
    this.panelOpen = !this.panelOpen;  // the ResizeObserver re-measures the canvas
  }

  async savePng(): Promise<void> {
    if (!this.view) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await this.view.toPng());
    a.download = 'graph.png';
    a.click();
  }

  docNames(ids?: string[]): string {
    return (ids || []).map((id) => {
      const m: Record<string, unknown> = this.data?.documents?.[id] || {};
      return String(m['file_name'] || m['title'] || m['file_path'] || id);
    }).join(', ');
  }

  show(v: unknown): string {
    return typeof v === 'string' ? v : JSON.stringify(v);
  }

  endName(id: string): string {
    return id.startsWith('chunk:') ? 'Chunk' : id;
  }
}
