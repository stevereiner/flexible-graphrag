import { Component, Input, Output, EventEmitter, OnInit, OnChanges, OnDestroy, SimpleChanges } from '@angular/core';
import { MatCheckboxChange } from '@angular/material/checkbox';
import { ApiService } from '../../services/api.service';
import { FlexibleGraphragConfigService } from '../../config.service';
import { ProcessingSessionService } from '../../services/processing-session.service';
import {
  AsyncProcessingResponse, ConfiguredStores, ProcessingStatusResponse,
  IngestStatusItem, IngestStatusRequest, ItemAction, ItemActionKind, ProcessingJob,
} from '../../models/api.models';

// Sources with no auto change sync: the "Enable auto change sync" checkbox is hidden for them
const NO_AUTO_SYNC_SOURCES = ['upload', 'cmis', 'web', 'wikipedia', 'youtube'];

// What a row is in, or should end up in: Search+Vector, and Graphs (property graph + RDF).
interface RowStores {
  sv: boolean;
  graphs: boolean;
  sync: boolean;  // Auto Sync: kept up to date with repository changes
}

type ColumnKind = 'sv' | 'graphs' | 'sync';

const TERMINAL_JOB = ['completed', 'failed', 'cancelled'];
// Job list refresh: often while a job runs, seldom when idle (still picks up auto sync runs)
const JOBS_BUSY_MS = 3000;
const JOBS_IDLE_MS = 15000;

// A file the server refused to store (unsupported extension, bad name, too large)
interface SkippedFile {
  filename: string;
  reason: string;
}

interface FileItem {
  index: number;
  name: string;
  size: number;
  type: string;
}

@Component({
  selector: 'app-processing-tab',
  templateUrl: './processing-tab.html',
  styleUrls: ['./processing-tab.scss'],
  standalone: false
})
export class ProcessingTabComponent implements OnInit, OnChanges, OnDestroy {
  @Input() hasConfiguredSources = false;
  @Input() configuredDataSource = '';
  @Input() configuredFiles: File[] = [];
  @Input() configuredFolderPath = '';
  @Input() repositoryItemsHidden = false;
  @Input() configuredCmisConfig: any = null;
  @Input() configuredAlfrescoConfig: any = null;
  @Input() configuredNuxeoConfig: any = null;
  @Input() configuredWebConfig: any = null;
  @Input() configuredWikipediaConfig: any = null;
  @Input() configuredYoutubeConfig: any = null;
  @Input() configuredCloudConfig: any = null;
  @Input() configuredEnterpriseConfig: any = null;
  @Input() configurationTimestamp = 0;
  @Output() goToSources = new EventEmitter<void>();
  @Output() removeRepositoryFile = new EventEmitter<number>();
  @Output() removeUploadFile = new EventEmitter<number>();

  // Table configuration
  /** nodeDetails from whichever repository source is configured, or [] if none carries any. */
  private repositoryNodeDetails(): any[] {
    const cfg = this.configuredAlfrescoConfig || this.configuredNuxeoConfig || this.configuredCmisConfig;
    return Array.isArray(cfg?.nodeDetails) ? cfg.nodeDetails : [];
  }

  /** The Alfresco or Nuxeo config in play, or null for any other source. */
  private pathRepositoryConfig(): any {
    if (this.configuredDataSource === 'alfresco') return this.configuredAlfrescoConfig;
    if (this.configuredDataSource === 'nuxeo') return this.configuredNuxeoConfig;
    return null;
  }

  // Ingest status of the current rows, by row index (see refreshIngestStatus)
  ingestStatus: IngestStatusItem[] = [];
  private ingestStatusKey = '';
  private ingestStatusRequest: IngestStatusRequest | null = null;  // the request behind `ingestStatus`
  // Which stores are configured; any can be "none" in .env (from the ingest-status response)
  stores: Partial<ConfiguredStores> = {};

  // What each row should end up in, by row name, once the user changed it (see wantFor)
  private wantSearch = new Map<string, boolean>();
  private wantGraphs = new Map<string, boolean>();
  private wantSync = new Map<string, boolean>();

  // Run in the background: START returns at once and the job is followed on the Jobs sub-tab
  runInBackground = false;
  subTabIndex = 0;  // 0 Processing, 1 Jobs
  jobs: ProcessingJob[] = [];
  private watchedJobs = new Set<string>();  // background jobs started here, until they finish
  private jobsTimer: any = null;
  private jobsDelay = 0;
  private pollTimer: any = null;

  /** Search+Vector / Graphs columns: once the ingest-status check answered with `stores`. */
  get displayedColumns(): string[] {
    if (!this.columnsMode) return ['select', 'name', 'size', 'progress', 'remove', 'status'];
    // Auto Sync only for repository sources (uploads are not kept in sync)
    return this.configuredDataSource === 'upload'
      ? ['select', 'name', 'size', 'progress', 'searchVector', 'graphs', 'remove', 'status']
      : ['select', 'name', 'size', 'progress', 'searchVector', 'graphs', 'autoSync', 'remove', 'status'];
  }
  
  // State
  selectedItems = new Set<number>();
  // Rows the user checked or unchecked themselves, by row name. autoSelectFiles() runs on every
  // input change and status poll; without this it put every row back to its default, so a
  // checked "already ingested" row lost its check, and removing one row cleared them all.
  private userChecks = new Map<string, boolean>();
  // Set by removeFile(): the host answers a removed row with a new config, which is not a new
  // selection, so it must not reset the run state or the user's checks.
  private removingRow = false;
  // Between the end of a run and the fresh ingest status: check nothing automatically, so a
  // second START cannot act on what the rows were before the run
  private awaitingStatus = false;
  displayFiles: FileItem[] = [];
  isProcessing = false;
  processingProgress = 0;
  processingStatus = '';
  currentProcessingId: string | null = null;
  statusData: ProcessingStatusResponse | null = null;
  lastStatusData: ProcessingStatusResponse | null = null;
  successMessage = '';
  error = '';
  skipGraph = false;  // Per-ingest flag to skip knowledge graph extraction
  enableSync = false; // Enable incremental sync monitoring for this datasource

  // Expose Math to template
  Math = Math;

  constructor(private apiService: ApiService, public config: FlexibleGraphragConfigService,
              private session: ProcessingSessionService) {}

  ngOnInit(): void {
    this.restoreSession();
    this.updateDisplayFiles();
  }

  ngOnDestroy(): void {
    clearInterval(this.pollTimer);
    clearTimeout(this.jobsTimer);
    this.saveSession();
  }

  /** Names the selection, so saved state is only given back to the same one. */
  private selectionKey(): string {
    return JSON.stringify([this.configuredDataSource, this.configuredFolderPath,
      this.repositoryNodeDetails().map((n: any) => n.id || n.path)]);
  }

  private saveSession(): void {
    this.session.tab = {
      key: this.selectionKey(),
      isProcessing: this.isProcessing, currentProcessingId: this.currentProcessingId,
      processingProgress: this.processingProgress, processingStatus: this.processingStatus,
      statusData: this.statusData, lastStatusData: this.lastStatusData,
      successMessage: this.successMessage, error: this.error,
      skipGraph: this.skipGraph, enableSync: this.enableSync, runInBackground: this.runInBackground,
      subTabIndex: this.subTabIndex, watchedJobs: [...this.watchedJobs],
      userChecks: [...this.userChecks], wantSearch: [...this.wantSearch], wantGraphs: [...this.wantGraphs],
      wantSync: [...this.wantSync],
    };
  }

  private restoreSession(): void {
    const t = this.session.tab;
    if (!t || t.key !== this.selectionKey()) return;
    Object.assign(this, {
      isProcessing: t['isProcessing'], currentProcessingId: t['currentProcessingId'],
      processingProgress: t['processingProgress'], processingStatus: t['processingStatus'],
      statusData: t['statusData'], lastStatusData: t['lastStatusData'],
      successMessage: t['successMessage'], error: t['error'],
      skipGraph: t['skipGraph'], enableSync: t['enableSync'], runInBackground: t['runInBackground'],
    });
    this.watchedJobs = new Set(t['watchedJobs']);
    this.userChecks = new Map(t['userChecks']);
    this.wantSearch = new Map(t['wantSearch']);
    this.wantGraphs = new Map(t['wantGraphs']);
    this.wantSync = new Map(t['wantSync'] || []);
    if (this.isProcessing && this.currentProcessingId) {
      this.startStatusPolling();  // the run went on while the tab was gone
    }
    this.ensureJobsPolling();
  }

  ngOnChanges(changes: SimpleChanges): void {
    // Clear old processing messages when configuration changes (not just any input change)
    const configurationChanged = changes['configuredDataSource'] || 
                                 changes['configuredFiles'] || 
                                 changes['configurationTimestamp'] ||
                                 changes['configuredFolderPath'] ||
                                 changes['configuredCmisConfig'] ||
                                 changes['configuredAlfrescoConfig'] ||
                                 changes['configuredNuxeoConfig'] ||
                                 changes['configuredWebConfig'] ||
                                 changes['configuredWikipediaConfig'] ||
                                 changes['configuredYoutubeConfig'] ||
                                 changes['configuredCloudConfig'] ||
                                 changes['configuredEnterpriseConfig'];
    
    const rowRemoved = this.removingRow;
    this.removingRow = false;
    if (configurationChanged && !rowRemoved) {
      // Clear old processing messages when configuration changes
      this.successMessage = '';
      this.error = '';
      // ...and the previous run's progress, which otherwise stays on the rows and hides the
      // "already ingested" check; re-ask ingest status even for an identical configuration, since
      // the last run may have just ingested it. Left alone while a run is in flight.
      if (!this.isProcessing) {
        this.processingProgress = 0;
        this.currentProcessingId = null;
        this.statusData = null;
        this.lastStatusData = null;
        this.ingestStatusKey = '';
        this.userChecks.clear();  // a new selection starts from the defaults
        this.wantSearch.clear();
        this.wantGraphs.clear();
        this.wantSync.clear();
        this.subTabIndex = 0;  // a new selection (e.g. Add to KG Spaces) opens on Processing
      }
    }
    
    this.updateDisplayFiles();
  }

  private updateDisplayFiles(): void {
    if (!this.hasConfiguredSources) {
      this.displayFiles = [];
      return;
    }
    
    if (this.configuredDataSource === 'upload') {
      this.displayFiles = this.configuredFiles.map((file, index) => ({
        index,
        name: file.name,
        size: file.size,
        type: 'file',
      }));
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      // If repository items are explicitly hidden, show nothing
      if (this.repositoryItemsHidden) {
        this.displayFiles = [];
        return;
      }
      
      // The selection decides the rows, and keeps them for the whole run.
      //
      // individual_files from the status endpoint used to REPLACE this list, so mid-ingest the
      // table collapsed to whatever the backend happened to be reporting -- one file, losing
      // its path -- and never recovered, because lastStatusData still answers after the run
      // finishes. Progress is decorated onto these rows instead: getFileProgress() matches by
      // full path, basename or substring, and falls back to the overall figure for a node the
      // backend has not reported yet. A typed path gets one row too, with the overall figure:
      // swapping it for the per-file list left a folder row showing one of its files after a
      // run, out of line with the ingest status.
      // No `return` in this branch: autoSelectFiles() runs at the end of this method, and
      // skipping it leaves every row unchecked, which disables Start Processing.
      const nodeDetails = this.repositoryNodeDetails();
      if (nodeDetails.length) {
        this.displayFiles = nodeDetails.map((node: any, index: number) => ({
          index,
          name: node.path || node.name || `Item ${index + 1}`,
          size: 0,
          type: node.isFolder ? 'repository' : 'repository-file'
        }));
      } else {
        this.displayFiles = [{
          index: 0,
          name: this.configuredFolderPath || 'Repository Path',
          size: 0,
          type: 'repository',
        }];
      }
    } else if (['web', 'wikipedia', 'youtube', 's3', 'gcs', 'azure_blob', 'onedrive', 'sharepoint', 'box', 'google_drive'].includes(this.configuredDataSource)) {
      // Handle web, cloud, and enterprise sources
      const getDisplayName = (): string => {
        switch (this.configuredDataSource) {
          case 'web':
            return this.configuredWebConfig?.url || 'Web Page';
          case 'wikipedia':
            return this.configuredWikipediaConfig?.query || 'Wikipedia Article';
          case 'youtube':
            return this.configuredYoutubeConfig?.url || 'YouTube Video';
          case 's3': {
            const bucket = this.configuredCloudConfig?.bucket_name || this.configuredCloudConfig?.bucket || 'Bucket';
            const prefix = this.configuredCloudConfig?.prefix || '';
            return prefix ? `s3://${bucket}/${prefix}` : `s3://${bucket}`;
          }
          case 'gcs':
            return `GCS: ${this.configuredCloudConfig?.bucket_name || 'Bucket'}`;
          case 'azure_blob':
            return `Azure: ${this.configuredCloudConfig?.account_name || 'Storage'}`;
          case 'onedrive':
            return `OneDrive: ${this.configuredCloudConfig?.user_principal_name || 'Drive'}`;
          case 'sharepoint':
            return `SharePoint: ${this.configuredEnterpriseConfig?.site_name || 'Site'}`;
          case 'box':
            return `Box: ${this.configuredEnterpriseConfig?.folder_id || 'Folder'}`;
          case 'google_drive':
            return `Google Drive: ${this.configuredCloudConfig?.folder_name || 'Drive'}`;
          default:
            return 'Source';
        }
      };

      const displayName = getDisplayName();
      
      // Check for individual files from status data (like CMIS/Alfresco)
      const individualFiles = (this.isProcessing || this.currentProcessingId) ? 
        (this.statusData?.individual_files || this.lastStatusData?.individual_files || []) : [];
      
      // If we have individual_files data, show it (this shows the single source entry with progress)
      if (individualFiles.length > 0) {
        this.displayFiles = individualFiles.map((file: any, index: number) => {
          // Use the filename from status (should be the bucket/source path)
          const fileName = file.filename || displayName;
          
          return {
            index,
            name: fileName,
            size: 0,
            type: 'source'
          };
        });
      } else {
        // Default to source path when no individual files yet
        this.displayFiles = [{
          index: 0,
          name: displayName,
          size: 0,
          type: 'source',
        }];
      }
    }
    
    // Auto-select files after updating display
    this.autoSelectFiles();
    this.refreshIngestStatus();
  }

  /**
   * Ask the backend which rows an auto-sync datasource already covers, so they can start
   * unchecked instead of being ingested a second time under another config_id. One call for
   * the whole selection, re-made only when the selection changes -- updateDisplayFiles() also
   * runs on every status poll. Quietly does nothing against a backend without the endpoint.
   */
  private refreshIngestStatus(): void {
    if (this.configuredDataSource === 'upload') {
      // Uploaded files: rows by file name (the backend finds them under its upload directory)
      if (this.isProcessing) return;
      if (!this.displayFiles.length) { this.ingestStatus = []; this.ingestStatusKey = ''; return; }
      this.requestIngestStatus({
        data_source: 'upload',
        recursive: false,
        items: this.displayFiles.map((f: any) => ({ path: f.name, is_folder: false })),
      });
      return;
    }
    const cfg = this.pathRepositoryConfig();
    if (!cfg || this.repositoryItemsHidden || this.isProcessing) {
      if (!cfg) { this.ingestStatus = []; this.ingestStatusKey = ''; }
      return;
    }
    const nodes = this.repositoryNodeDetails();
    const request: IngestStatusRequest = {
      data_source: this.configuredDataSource as 'alfresco' | 'nuxeo',
      url: cfg.url,
      recursive: !!cfg.recursive,
      items: nodes.length
        ? nodes.map((n: any) => ({ path: n.path, id: n.id, is_folder: !!n.isFolder }))
        : [this.pathItem(cfg.path || this.configuredFolderPath || '/')],
    };
    this.requestIngestStatus(request);
  }

  private requestIngestStatus(request: IngestStatusRequest): void {
    const key = JSON.stringify(request);
    if (key === this.ingestStatusKey) return;
    this.ingestStatusKey = key;
    this.ingestStatusRequest = request;
    this.ingestStatus = [];

    this.apiService.checkIngestStatus(request).subscribe({
      next: (res) => {
        if (key !== this.ingestStatusKey) return;  // the selection changed while this was in flight
        this.ingestStatus = res.enabled ? res.items : [];
        this.stores = res.stores || {};
        this.autoSelectFiles();
      },
      error: (err: any) => console.warn('Ingest status check unavailable:', err),
    });
  }

  /** A typed repository path can name a file as well as a folder; an extension means file. */
  private pathItem(path: string): { path: string; is_folder: boolean } {
    const last = (path || '').split('/').pop() || '';
    return { path, is_folder: !/\.[A-Za-z0-9]{1,8}$/.test(last) };
  }

  /** Ingest status of a row, when an auto-sync datasource already covers any of it. */
  ingestStatusFor(index: number): IngestStatusItem | null {
    // Rows and ingest status line up one-to-one, except after a path-only run, when the rows can
    // be the backend's per-file list instead of the one folder that was checked.
    if (this.ingestStatus.length !== this.displayFiles.length) return null;
    const c = this.ingestStatus[index];
    return c && c.status !== 'none' ? c : null;
  }

  ingestStatusLabel(index: number): string {
    const c = this.ingestStatusFor(index);
    // "synced" only when an auto change sync covers it; otherwise it was ingested once
    const synced = !!c?.datasources.some((m) => m.auto_sync && m.status === c.status);
    switch (c?.status) {
      case 'synced': return synced ? 'already synced' : 'already ingested';
      case 'partial': return synced ? 'synced, no subfolders' : 'ingested, no subfolders';
      case 'overlaps': return synced ? 'contains synced' : 'contains ingested';
      case 'removed': return 'removed';
      default: return '';
    }
  }

  ingestStatusTooltip(index: number): string {
    const c = this.ingestStatusFor(index);
    if (!c) return '';
    const lines = c.datasources.map((m) => {
      const how = m.auto_sync ? 'synced by' : 'ingested (no auto sync) by';
      const what = m.relation === 'indexed' ? 'indexed by'
        : m.relation === 'contains' ? `contains ${m.root}, ${how}`
        : `${m.root}${m.recursive ? ' (with subfolders)' : ''}, ${how}`;
      return `${what} ${m.source_name || m.config_id}${m.skip_graph ? ' [no graph]' : ''}`;
    });
    if (c.indexed) {
      const where = (['vector', 'search', 'graph'] as const).filter((t) => c.indexed![t]);
      lines.push(`in: ${where.join(', ') || 'none'}`);
    }
    lines.push(c.status === 'synced'
      ? 'Left unchecked. Check it, set Search+Vector / Graphs, and click START PROCESSING to update it.'
      : c.status === 'removed'
        ? 'Removed from the stores and kept out of its auto sync, even when it changes. Ingest it to put it back.'
        : 'Part of it is already in the stores; ingesting it again refreshes that part.');
    return lines.join('\n');
  }

  // ── Search+Vector / Graphs columns ──────────────────────────────────────────────────
  /** Offered once the ingest-status check answered with `stores` (a 0.8.2 backend has none). */
  get columnsMode(): boolean {
    return this.ingestStatus.length > 0 && this.ingestStatusRequest !== null && Object.keys(this.stores).length > 0;
  }

  /** Kept for hosts/templates that still ask; same as columnsMode. */
  get canRemove(): boolean {
    return this.columnsMode;
  }

  get canSearchVector(): boolean {
    return !!(this.stores.vector || this.stores.search);
  }

  get canGraphs(): boolean {
    return !!this.stores.graph;
  }

  inStores(index: number): boolean {
    const status = this.ingestStatusFor(index)?.status;
    return status === 'synced' || status === 'partial' || status === 'overlaps';
  }

  /** What a row is in now, from the ingest status. */
  currentFor(index: number): RowStores {
    const c = this.ingestStatusFor(index);
    const sync = !!c?.auto_sync;
    if (!c || !this.inStores(index)) return { sv: false, graphs: false, sync };
    if (c.indexed) {
      return { sv: !!(c.indexed.vector || c.indexed.search), graphs: !!c.indexed.graph, sync };
    }
    // No per-document answer: the datasources holding it say whether they build graphs
    return { sv: true, graphs: c.datasources.some((m) => !m.skip_graph), sync };
  }

  /** Whether an auto sync already covers the row (so Auto Sync on resumes, not starts, it). */
  private coveredBySync(index: number): boolean {
    return !!this.ingestStatusFor(index)?.datasources.some((m) => m.auto_sync);
  }

  /** What a row should end up in: the user's choice, else what it is in now, else everything. */
  wantFor(index: number): RowStores {
    const name = this.displayFiles[index]?.name;
    const cur = this.currentFor(index);
    const fresh = !this.inStores(index);
    const sv = this.wantSearch.get(name) ?? (fresh ? this.canSearchVector : cur.sv);
    const graphs = this.wantGraphs.get(name) ?? (fresh ? this.canGraphs : cur.graphs);
    const sync = this.wantSync.get(name) ?? cur.sync;
    // Graphs and Auto Sync both need Search+Vector: a sync with nothing indexed would only
    // put the document back on its next change
    return { sv, graphs: sv && graphs, sync: sv && sync };
  }

  /** Changing a row's Search+Vector / Graphs / Auto Sync checks the row: START PROCESSING applies it. */
  setWant(index: number, kind: ColumnKind, value: boolean): void {
    const name = this.displayFiles[index]?.name;
    if (!name) return;
    if (kind === 'sv') {
      this.wantSearch.set(name, value);
      if (!value) {  // no graphs and no sync without search + vector
        this.wantGraphs.set(name, false);
        this.wantSync.set(name, false);
      }
    } else if (kind === 'graphs') {
      this.wantGraphs.set(name, value);
      if (value) this.wantSearch.set(name, true);
    } else {
      this.wantSync.set(name, value);
      if (value) this.wantSearch.set(name, true);
    }
    this.selectedItems.add(index);
    this.userChecks.set(name, true);
  }

  /** Set a column for every row (its header checkbox). */
  setWantAll(kind: ColumnKind, value: boolean): void {
    this.displayFiles.forEach((_, i) => this.setWant(i, kind, value));
  }

  allWant(kind: ColumnKind): boolean {
    return this.displayFiles.length > 0 && this.displayFiles.every((_, i) => this.wantFor(i)[kind]);
  }

  someWant(kind: ColumnKind): boolean {
    const n = this.displayFiles.filter((_, i) => this.wantFor(i)[kind]).length;
    return n > 0 && n < this.displayFiles.length;
  }

  /** What START PROCESSING does with a checked row, or null when there is nothing to do. */
  actionFor(index: number): ItemActionKind | null {
    const cur = this.currentFor(index);
    const want = this.wantFor(index);
    if (!want.sv) return cur.sv || cur.graphs ? 'remove_all' : null;
    if (want.graphs) return 'ingest';
    return cur.sv && cur.graphs ? 'remove_graph' : 'ingest_no_graph';
  }

  /** The Status column in columns mode: which stores the row is in now. */
  storesLabel(index: number): string {
    const c = this.ingestStatusFor(index);
    if (c?.status === 'removed') return 'removed';
    const cur = this.currentFor(index);
    if (!cur.sv && !cur.graphs) return 'not ingested';
    return (cur.graphs ? 'search+vector, graphs' : 'search+vector') + (cur.sync ? ' (synced)' : '');
  }

  /** A sync change for a checked row: false stops it, true resumes it, null = none. */
  private syncChange(index: number): boolean | null {
    const want = this.wantFor(index).sync;
    return want !== this.currentFor(index).sync ? want : null;
  }

  /** Auto Sync turned on for a row no sync covers: the backend starts a sync for it. */
  private needsNewSync(index: number): boolean {
    return this.syncChange(index) === true && !this.coveredBySync(index);
  }

  /**
   * What START PROCESSING sends for the checked rows: per row a store action and/or an Auto
   * Sync change. A row no sync covers yet, with Auto Sync checked, is ingested with
   * auto_sync: true: the backend makes this run\'s datasource an auto sync watching it.
   */
  private itemActions(): ItemAction[] {
    const base = this.ingestStatusRequest;
    const rows: ItemAction[] = [];
    for (const i of [...this.selectedItems].sort((a, b) => a - b)) {
      const item = base?.items[i];
      if (!item) continue;
      const ref = { path: item.path, id: item.id, is_folder: item.is_folder };
      if (this.needsNewSync(i)) {
        rows.push({ ...ref, action: this.actionFor(i) ?? (this.wantFor(i).graphs ? 'ingest' : 'ingest_no_graph'), auto_sync: true });
        continue;
      }
      const action = this.actionFor(i);
      const sync = this.syncChange(i);
      if (!action && sync === null) continue;
      rows.push({ ...ref, action: action ?? 'keep', ...(sync === null ? {} : { auto_sync: sync }) });
    }
    return rows;
  }

  // ── Jobs sub-tab ────────────────────────────────────────────────────────────────────
  onSubTabChange(index: number): void {
    this.subTabIndex = index;
    if (index === 1) this.loadJobs();
    this.ensureJobsPolling();
  }

  /**
   * Refresh the job list while it is shown or a background job started here is still going:
   * every 3 s while a job runs, every 15 s when none does.
   */
  private ensureJobsPolling(): void {
    const wanted = this.subTabIndex === 1 || this.watchedJobs.size > 0;
    const delay = this.watchedJobs.size > 0 || this.jobs.some((j) => this.jobRunning(j)) ? JOBS_BUSY_MS : JOBS_IDLE_MS;
    if (this.jobsTimer && (!wanted || delay < this.jobsDelay)) {  // stop, or a job just started
      clearTimeout(this.jobsTimer);
      this.jobsTimer = null;
    }
    if (wanted && !this.jobsTimer) {
      this.jobsDelay = delay;
      this.jobsTimer = setTimeout(() => {
        this.jobsTimer = null;
        this.loadJobs();
      }, delay);
    }
  }

  loadJobs(): void {
    this.apiService.listJobs().subscribe({
      next: (res) => {
        this.jobs = res.jobs || [];
        for (const job of this.jobs) {
          if (this.watchedJobs.has(job.processing_id) && TERMINAL_JOB.includes(job.status)) {
            this.watchedJobs.delete(job.processing_id);
            this.showFinishedJob(job);
          }
        }
        this.ensureJobsPolling();
      },
      error: (err: any) => {
        console.warn('Job list unavailable:', err);
        this.ensureJobsPolling();
      },
    });
  }

  /**
   * A background job started here has finished: show its outcome on the Processing sub-tab
   * like a foreground run -- per-file status and its message -- unless a foreground run is
   * going on, then ask the ingest status again once its document_state rows are written.
   */
  private showFinishedJob(job: ProcessingJob): void {
    if (!this.isProcessing) {
      this.apiService.getProcessingStatus(job.processing_id).subscribe({
        next: (status) => {
          if (this.isProcessing) return;
          this.statusData = null;
          this.lastStatusData = status;
          this.processingProgress = status.status === 'completed' ? 100 : status.progress || 0;
          if (status.status === 'completed') {
            this.successMessage = status.message || 'Background job finished.';
          } else {
            this.error = `Background job ${status.status}: ${status.error || status.message || ''}`;
          }
          this.updateDisplayFiles();
        },
        error: () => undefined,
      });
    }
    if (!this.isProcessing) this.afterRun();
  }

  /**
   * A run is over. The rows' choices go back to their defaults -- rows in the stores unchecked,
   * columns showing what each row is in now -- so a second START does not repeat the run (a
   * row whose graphs were removed would otherwise be re-ingested as search + vector). The
   * ingest status is asked again once the run's document_state rows are written.
   */
  private afterRun(): void {
    this.userChecks.clear();
    this.wantSearch.clear();
    this.wantGraphs.clear();
    this.selectedItems = new Set();
    this.awaitingStatus = true;
    setTimeout(() => {
      this.awaitingStatus = false;
      this.ingestStatusKey = '';
      this.refreshIngestStatus();
      this.autoSelectFiles();
    }, 4000);
  }

  clearJobs(): void {
    this.apiService.clearJobs().subscribe({
      next: () => this.loadJobs(),
      error: (err: any) => (this.error = `Clear failed: ${err?.error?.detail || err?.message || err}`),
    });
  }

  get finishedJobCount(): number {
    return this.jobs.filter((j) => !this.jobRunning(j)).length;
  }

  cancelJob(job: ProcessingJob): void {
    this.apiService.cancelProcessing(job.processing_id).subscribe({
      next: () => this.loadJobs(),
      error: (err: any) => (this.error = `Cancel failed: ${err?.error?.detail || err?.message || err}`),
    });
  }

  jobRunning(job: ProcessingJob): boolean {
    return !TERMINAL_JOB.includes(job.status);
  }

  get runningJobCount(): number {
    return this.jobs.filter((j) => this.jobRunning(j)).length;
  }

  get ingestedRowCount(): number {
    return this.displayFiles.filter((_, i) => this.ingestStatusFor(i)?.status === 'synced').length;
  }

  private autoSelectFiles(): void {
    if (this.configuredDataSource === 'upload') {
      this.selectedItems = new Set(this.configuredFiles.map((_, index) => index));
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      // Auto-select all repository rows except those auto-sync already covers. Mid-run the
      // selection is left alone: this also runs on every status poll.
      if (this.isProcessing || this.awaitingStatus) return;
      this.selectedItems = new Set(
        this.displayFiles
          .map((_, index) => index)
          .filter((index) => this.userChecks.get(this.displayFiles[index].name)
            ?? this.ingestStatusFor(index)?.status !== 'synced')
      );
    } else if (['web', 'wikipedia', 'youtube', 's3', 'gcs', 'azure_blob', 'onedrive', 'sharepoint', 'box', 'google_drive'].includes(this.configuredDataSource)) {
      // Auto-select the single source item
      this.selectedItems = new Set(this.displayFiles.map((_, index) => index));
    }
  }

  formatFileSize(bytes: number): string {
    if (bytes < 1024) {
      return bytes === 0 ? "0 B" : "1 KB";
    } else if (bytes < 1024 * 1024) {
      return `${Math.ceil(bytes / 1024)} KB`;
    } else {
      return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }
  }

  /**
   * True once a run has finished successfully. The status poll stops at that point, so
   * lastStatusData keeps whatever mid-flight sample arrived last -- a row could sit at
   * "40% - Loading" next to a green "Successfully ingested" banner. A per-file record is
   * still preferred when it reports a terminal state, so a file that errored keeps saying so.
   */
  private get runFinishedOk(): boolean {
    return !this.isProcessing && this.processingProgress === 100 && !this.error;
  }

  getFileProgressData(filename: string): any {
    const files = this.statusData?.individual_files || this.lastStatusData?.individual_files || [];
    
    // Try exact match first
    let match = files.find((file: any) => file.filename === filename);
    if (!match) {
      // Try matching just the basename if full path doesn't match
      match = files.find((file: any) => {
        const fileBasename = file.filename?.split(/[/\\]/).pop();
        return fileBasename === filename;
      });
    }
    if (!match) {
      // Try matching if our filename is contained in the stored filename
      match = files.find((file: any) => 
        file.filename?.includes(filename) || filename.includes(file.filename)
      );
    }
    
    return match;
  }

  getFileProgress(filename: string): number {
    // For repository path placeholder, use overall progress
    if (filename === 'Repository Path' || filename?.includes('Repository')) {
      return this.isProcessing ? this.processingProgress : 0;
    }
    
    // Try to get individual file data first, fall back to overall progress for repository files
    const progressData = this.getFileProgressData(filename);
    if (progressData) {
      if (this.runFinishedOk && progressData.status !== 'error') {
        return 100;
      }
      return progressData.progress || 0;
    }
    
    // Fallback to overall progress for repository files when no individual data
    if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      return this.processingProgress; // Always show progress, even when completed
    }
    
    return 0;
  }

  getFilePhase(filename: string): string {
    // For repository path placeholder, use overall status
    if (filename === 'Repository Path' || filename?.includes('Repository')) {
      if (this.isProcessing) return 'Processing';
      if (this.processingProgress === 100) return 'Completed';
      return 'Ready';
    }
    
    // Try to get individual file data first
    const progressData = this.getFileProgressData(filename);
    if (progressData) {
      if (this.runFinishedOk && progressData.status !== 'error') {
        return 'Completed';
      }
      const phase = progressData.phase || 'ready';
      const phaseNames: { [key: string]: string } = {
        'ready': 'Ready',
        'waiting': 'Waiting',
        'loading': 'Loading',
        'loaded': 'Loaded',
        'cocoindex': 'Processing',
        'downloading': 'Downloading',
        'downloaded': 'Downloaded',
        'parsing': 'Parsing',
        'parsed': 'Parsed',
        'chunked': 'Chunked',
        'embedded': 'Embedded',
        'docling': 'Converting',
        'chunking': 'Chunking',
        'kg_extracting': 'Extracting Graph',
        'kg_extracted': 'Graph Extracted',
        'vector_indexing': 'Vector Index',
        'graph_indexing': 'Property Graph',
        'kg_extraction': 'Extracting Graph',
        'search_indexing': 'Search Index',
        'rdf_indexing': 'RDF Graph',
        'indexing_complete': 'Complete',
        'indexing': 'Indexing',
        'completed': 'Completed',
        'error': 'Error'
      };
      return phaseNames[phase] || phase;
    }
    
    // Fallback for repository files
    if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      if (this.isProcessing) return 'Processing';
      if (this.processingProgress === 100) return 'Completed';
      return 'Ready';
    }
    
    return 'Ready';
  }

  getFileStatus(filename: string): string {
    // For repository path placeholder, use overall status
    if (filename === 'Repository Path' || filename?.includes('Repository')) {
      if (this.isProcessing) return 'processing';
      if (this.processingProgress === 100) return 'completed';
      return 'ready';
    }
    
    // Try to get individual file data first
    const progressData = this.getFileProgressData(filename);
    if (progressData) {
      if (this.runFinishedOk && progressData.status !== 'error') {
        return 'completed';
      }
      return progressData.status || 'ready';
    }
    
    // Fallback for repository files
    if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      if (this.isProcessing) return 'processing';
      if (this.processingProgress === 100) return 'completed';
      return 'ready';
    }
    
    return 'ready';
  }

  getStatusColor(status: string): string {
    switch (status) {
      case 'completed': return 'success'; // Green for completed
      case 'failed': return 'warn';
      case 'processing': return 'accent';
      default: return '';
    }
  }

  // Selection methods
  isAllSelected(): boolean {
    return this.displayFiles.length > 0 && this.selectedItems.size === this.displayFiles.length;
  }

  isIndeterminate(): boolean {
    return this.selectedItems.size > 0 && this.selectedItems.size < this.displayFiles.length;
  }

  isSelected(index: number): boolean {
    return this.selectedItems.has(index);
  }

  toggleAllSelection(event: MatCheckboxChange): void {
    if (event.checked) {
      this.selectedItems = new Set(this.displayFiles.map((_, index) => index));
    } else {
      this.selectedItems.clear();
    }
    this.displayFiles.forEach((f) => this.userChecks.set(f.name, event.checked));
  }

  toggleSelection(index: number, event: MatCheckboxChange): void {
    if (event.checked) {
      this.selectedItems.add(index);
    } else {
      this.selectedItems.delete(index);
    }
    const row = this.displayFiles[index];
    if (row) this.userChecks.set(row.name, event.checked);
  }

  removeFile(index: number): void {
    // The host answers with a new config (the row gone), and the checks are put back on the
    // remaining rows BY NAME (autoSelectFiles + userChecks) -- never shifted by position here:
    // a host that does not remove the row would then see the checks slide up one row.
    this.displayFiles.forEach((f, i) => this.userChecks.set(f.name, this.selectedItems.has(i)));
    this.removingRow = true;
    setTimeout(() => (this.removingRow = false));  // a host that sends no new config
    if (this.configuredDataSource === 'upload') {
      console.log('🗑️ Upload file removal requested for index:', index);
      this.removeUploadFile.emit(index);
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      console.log('🗑️ Repository file removal requested for index:', index);
      this.removeRepositoryFile.emit(index);
    }
  }


  private checkedNodeDetails(): any[] {
    return this.repositoryNodeDetails().filter((_: any, index: number) => this.selectedItems.has(index));
  }

  /** Narrow a repository config's nodeDetails / nodeIds to the checked rows. */
  private withCheckedNodes(cfg: any): any {
    if (!Array.isArray(cfg?.nodeDetails) || !cfg.nodeDetails.length) return cfg;
    const checked = this.checkedNodeDetails();
    const ids = new Set(checked.map((n: any) => n.id));
    return {
      ...cfg,
      nodeDetails: checked,
      ...(Array.isArray(cfg.nodeIds) ? { nodeIds: cfg.nodeIds.filter((id: string) => ids.has(id)) } : {}),
    };
  }

  canStartProcessing(): boolean {
    return this.hasConfiguredSources && this.selectedItems.size > 0 && !this.isProcessing;
  }

  getProcessingButtonText(): string {
    if (this.isProcessing) return 'PROCESSING...';
    if (!this.hasConfiguredSources) return 'CONFIGURE SOURCES FIRST';
    if (this.selectedItems.size === 0) return 'SELECT FILES TO PROCESS';
    return 'START PROCESSING';
  }

  async startProcessing(): Promise<void> {
    if (!this.canStartProcessing()) return;
    
    console.log('Start processing with selected items:', Array.from(this.selectedItems));
    
    this.isProcessing = true;
    this.processingProgress = 0;
    this.statusData = null;
    this.successMessage = ''; // Clear any previous success message
    this.error = ''; // Clear any previous error message
    
    try {
      // Prepare processing data
      const processingData: any = {};
      
      // Search+Vector / Graphs columns: each checked row says what it should end up as
      const planned = this.columnsMode ? this.itemActions() : null;
      const actions = planned;
      if (planned && planned.length === 0) {
        this.successMessage = 'Nothing to do: the checked rows already match their Search+Vector / Graphs settings.';
        this.isProcessing = false;
        return;
      }

      if (this.configuredDataSource === 'upload') {
        // For upload, upload files first then use filesystem processing
        const { paths: uploadedPaths, skipped } = await this.uploadFiles();

        // Nothing survived the upload (e.g. every file had an unsupported extension).
        // Stop here: posting paths: [] starts a job that can only fail, and its "failed"
        // status then overwrites the skip reasons the user actually needs to read.
        if (uploadedPaths.length === 0) {
          this.error = skipped.length > 0
            ? `No files could be uploaded:\n${this.formatSkipped(skipped)}`
            : 'No files could be uploaded';
          this.isProcessing = false;
          return;
        }

        if (skipped.length > 0) {
          this.error = `Some files were skipped:\n${this.formatSkipped(skipped)}`;
        }

        processingData.data_source = 'filesystem'; // Use filesystem processing for uploaded files
        processingData.paths = uploadedPaths;
      } else {
        processingData.data_source = this.configuredDataSource;
      }
      
      // Add configuration for other data sources
      if (this.configuredDataSource === 'filesystem') {
        // For direct filesystem access (not upload)
        processingData.paths = this.configuredFiles.map(f => f.name);
      } else if (this.configuredDataSource === 'cmis') {
        processingData.paths = [this.configuredFolderPath || '/Sites/swsdp/documentLibrary']; // Use configured path
        processingData.cmis_config = {
          url: 'http://localhost:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom',
          username: 'admin',
          password: 'admin',
          folder_path: this.configuredFolderPath || '/Sites/swsdp/documentLibrary'
        };
      } else if (this.configuredDataSource === 'alfresco') {
        const alfrescoPath = this.configuredAlfrescoConfig?.path
          || this.configuredFolderPath
          || '/Sites/swsdp/documentLibrary';
        // One path per selected node when the host supplied nodeDetails, so a multi-select
        // ingests exactly what was picked. The backend also routes per nodeDetails entry, so
        // these agree; a single collapsed path would silently widen a partial selection.
        const nodePaths = this.checkedNodeDetails()
          .map((n: any) => n.path)
          .filter((p: any): p is string => !!p);
        processingData.paths = nodePaths.length ? nodePaths : [alfrescoPath];
        // Send what the Sources tab actually configured. This used to be a hardcoded
        // url/username/password literal, so every edit made in the form -- credentials, auth
        // method, ticket -- was silently discarded and every ingest ran as admin/admin against
        // http://localhost:8080. The literals remain only as a fallback for when nothing has
        // been configured at all.
        processingData.alfresco_config = this.configuredAlfrescoConfig
          ? this.withCheckedNodes({ ...this.configuredAlfrescoConfig, path: alfrescoPath })
          : {
              url: 'http://localhost:8080',
              username: 'admin',
              password: 'admin',
              path: alfrescoPath
            };
      } else if (this.configuredDataSource === 'nuxeo') {
        processingData.nuxeo_config = this.configuredNuxeoConfig
          ? this.withCheckedNodes({ ...this.configuredNuxeoConfig })
          : this.configuredNuxeoConfig;
      } else if (this.configuredDataSource === 'web') {
        processingData.web_config = this.configuredWebConfig;
      } else if (this.configuredDataSource === 'wikipedia') {
        processingData.wikipedia_config = this.configuredWikipediaConfig;
      } else if (this.configuredDataSource === 'youtube') {
        processingData.youtube_config = this.configuredYoutubeConfig;
      } else if (this.configuredDataSource === 's3') {
        processingData.s3_config = this.configuredCloudConfig;
      } else if (this.configuredDataSource === 'gcs') {
        processingData.gcs_config = this.configuredCloudConfig;
      } else if (this.configuredDataSource === 'azure_blob') {
        processingData.azure_blob_config = this.configuredCloudConfig;
      } else if (this.configuredDataSource === 'onedrive') {
        processingData.onedrive_config = this.configuredEnterpriseConfig;
      } else if (this.configuredDataSource === 'sharepoint') {
        processingData.sharepoint_config = this.configuredEnterpriseConfig;
      } else if (this.configuredDataSource === 'box') {
        processingData.box_config = this.configuredEnterpriseConfig;
      } else if (this.configuredDataSource === 'google_drive') {
        processingData.google_drive_config = this.configuredEnterpriseConfig;
      }
      
      console.log('🔧 Angular startProcessing - configured data:', {
        dataSource: this.configuredDataSource,
        webConfig: this.configuredWebConfig,
        wikipediaConfig: this.configuredWikipediaConfig,
        youtubeConfig: this.configuredYoutubeConfig,
        cloudConfig: this.configuredCloudConfig,
        enterpriseConfig: this.configuredEnterpriseConfig,
        skipGraph: this.skipGraph
      });
      console.log('Starting processing with data:', processingData);
      
      if (planned) {
        processingData.item_actions = actions;
      } else if (this.skipGraph) {
        // Add skip_graph flag to processing data (no columns: one setting for the whole run)
        processingData.skip_graph = true;
        console.log('✓ skip_graph flag set to true - Knowledge graph extraction will be skipped');
      }
      
      // Add enable_sync flag to processing data
      // Only for a source that shows the checkbox: the value survives switching sources, so
      // a sync left ticked on Alfresco would otherwise make a later upload a live sync too.
      if (!planned && this.enableSync && !NO_AUTO_SYNC_SOURCES.includes(this.configuredDataSource)) {
        processingData.enable_sync = true;
        console.log('✓ enable_sync flag set to true - Incremental updates will be enabled');
      }
      

      this.apiService.ingestDocuments(processingData).subscribe({
        next: (response: AsyncProcessingResponse) => {
          console.log('Processing started:', response);
          
          if (response.processing_id && this.runInBackground) {
            // The job carries on in the backend; this tab is free to start another one
            this.isProcessing = false;
            this.watchedJobs.add(response.processing_id);
            this.successMessage = `Started in the background (job ${response.processing_id}). Follow it on the Jobs tab.`;
            this.ensureJobsPolling();
          } else if (response.processing_id) {
            this.currentProcessingId = response.processing_id;
            // Set success message with estimated time like Vue/React
            const estimatedTime = response.estimated_time || '30-60 seconds';
            this.successMessage = `Processing started: ${estimatedTime}`;
            this.startStatusPolling();
          }
        },
        error: (error: any) => {
          console.error('Error starting processing:', error);
          this.isProcessing = false;
        }
      });
      
    } catch (error) {
      console.error('Error in startProcessing:', error);
      this.isProcessing = false;
    }
  }

  private formatSkipped(skipped: SkippedFile[]): string {
    return skipped.map(file => `${file.filename}: ${file.reason}`).join('\n');
  }

  private uploadFiles(): Promise<{ paths: string[]; skipped: SkippedFile[] }> {
    console.log('Uploading files:', this.configuredFiles);
    
    const formData = new FormData();
    this.configuredFiles.forEach(file => {
      formData.append('files', file);
    });
    
    return new Promise((resolve, reject) => {
      this.apiService.uploadFiles(formData).subscribe({
        next: (response: any) => {
          console.log('Files uploaded:', response);
          
          // Extract uploaded file paths for processing (match Vue/React pattern)
          let uploadedPaths: string[] = [];
          const skipped: SkippedFile[] = response.skipped || [];
          
          if (response.success && response.files) {
            uploadedPaths = response.files.map((file: any) => file.path);
            
            // Update configured files with server response if needed
            this.configuredFiles = response.files.map((serverFile: any) => {
              const originalFile = this.configuredFiles.find(f => f.name === serverFile.filename);
              if (originalFile) {
                // Create a new File object with the server filename
                const newFile = new File([originalFile], serverFile.saved_as, { type: originalFile.type });
                return newFile;
              }
              return originalFile;
            }).filter(Boolean);
          } else {
            // No fallback to client-side file names: those are bare basenames that would
            // resolve against the backend's working directory, not the upload directory.
            // An empty list is correct here and the caller reports it.
            uploadedPaths = [];
          }
          
          resolve({ paths: uploadedPaths, skipped });
        },
        error: (error: any) => {
          console.error('Error uploading files:', error);
          reject(error);
        }
      });
    });
  }

  private startStatusPolling(): void {
    if (!this.currentProcessingId) return;
    
    console.log('Starting status polling for:', this.currentProcessingId);
    
    // Poll every 2 seconds (stopped in ngOnDestroy; restoreSession() picks the run up again)
    clearInterval(this.pollTimer);
    const pollInterval = this.pollTimer = setInterval(() => {
      if (!this.currentProcessingId) {
        clearInterval(pollInterval);
        return;
      }
      
      this.apiService.getProcessingStatus(this.currentProcessingId).subscribe({
        next: (status: ProcessingStatusResponse) => {
          console.log('Status update:', status);
          this.statusData = status;
          this.lastStatusData = status; // Preserve for after cancellation
          
          if (status.progress !== undefined) {
            this.processingProgress = status.progress;
          }
          
          // Update display files when status data changes (for repository individual files)
          this.updateDisplayFiles();
          
          // Check if processing is complete
          if (status.status === 'completed') {
            console.log('Processing completed successfully');
            this.isProcessing = false;
            this.currentProcessingId = null;
            this.successMessage = status.message || 'Successfully ingested document(s)!';
            clearInterval(pollInterval);
          } else if (status.status === 'failed') {
            console.log('Processing failed');
            this.isProcessing = false;
            this.currentProcessingId = null;
            this.error = status.error || 'Processing failed';
            clearInterval(pollInterval);
          } else if (status.status === 'cancelled') {
            console.log('Processing cancelled');
            this.isProcessing = false;
            this.currentProcessingId = null;
            this.successMessage = 'Processing cancelled successfully';
            clearInterval(pollInterval);
          }
          if (!this.isProcessing) {
            this.afterRun();
            this.updateDisplayFiles();
          }
        },
        error: (error: any) => {
          console.error('Error polling status:', error);
          clearInterval(pollInterval);
          this.isProcessing = false;
          this.currentProcessingId = null;
        }
      });
    }, 2000);
  }

  cancelProcessing(): void {
    if (!this.currentProcessingId) return;
    
    console.log('Cancel processing:', this.currentProcessingId);
    
    this.apiService.cancelProcessing(this.currentProcessingId).subscribe({
      next: (response: any) => {
        console.log('Processing cancelled:', response);
        this.isProcessing = false;
        this.currentProcessingId = null;
        this.processingProgress = 0;
        this.statusData = null;
        // Keep lastStatusData to preserve individual files after cancellation
        this.updateDisplayFiles(); // Update display to show preserved files
      },
      error: (error: any) => {
        console.error('Error cancelling processing:', error);
        // Still reset the UI state
        this.isProcessing = false;
        this.currentProcessingId = null;
      }
    });
  }
}