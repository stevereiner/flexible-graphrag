import { Component, Input, Output, EventEmitter, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { MatCheckboxChange } from '@angular/material/checkbox';
import { ApiService } from '../../services/api.service';
import { AsyncProcessingResponse, ProcessingStatusResponse, SyncCoverageItem, SyncCoverageRequest } from '../../models/api.models';

// Sources with no auto change sync: the "Enable auto change sync" checkbox is hidden for them
const NO_AUTO_SYNC_SOURCES = ['upload', 'cmis', 'web', 'wikipedia', 'youtube'];

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
export class ProcessingTabComponent implements OnInit, OnChanges {
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

  // Auto-sync coverage of the current rows, by row index (see refreshCoverage)
  coverage: SyncCoverageItem[] = [];
  private coverageKey = '';

  displayedColumns: string[] = ['select', 'name', 'size', 'progress', 'remove', 'status'];
  
  // State
  selectedItems = new Set<number>();
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

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    this.updateDisplayFiles();
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
    
    if (configurationChanged) {
      // Clear old processing messages when configuration changes
      this.successMessage = '';
      this.error = '';
      // ...and the previous run's progress, which otherwise stays on the rows and hides the
      // "already ingested" check; re-ask coverage even for an identical configuration, since
      // the last run may have just ingested it. Left alone while a run is in flight.
      if (!this.isProcessing) {
        this.processingProgress = 0;
        this.currentProcessingId = null;
        this.statusData = null;
        this.lastStatusData = null;
        this.coverageKey = '';
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
      // backend has not reported yet.
      // No `return` in this branch: autoSelectFiles() runs at the end of this method, and
      // skipping it leaves every row unchecked, which disables Start Processing.
      const nodeDetails = this.repositoryNodeDetails();
      const individualFiles = (this.isProcessing || this.currentProcessingId) ?
        (this.statusData?.individual_files || this.lastStatusData?.individual_files || []) : [];

      if (nodeDetails.length) {
        this.displayFiles = nodeDetails.map((node: any, index: number) => ({
          index,
          name: node.path || node.name || `Item ${index + 1}`,
          size: 0,
          type: node.isFolder ? 'repository' : 'repository-file'
        }));
      } else if (individualFiles.length > 0) {
        // No per-node detail (a path typed on the Sources tab): the backend's own file list is
        // the only breakdown available, so use it when there is one.
        this.displayFiles = individualFiles.map((file: any, index: number) => ({
          index,
          name: file.filename || `File ${index + 1}`,
          size: 0,
          type: 'repository-file'
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
    this.refreshCoverage();
  }

  /**
   * Ask the backend which rows an auto-sync datasource already covers, so they can start
   * unchecked instead of being ingested a second time under another config_id. One call for
   * the whole selection, re-made only when the selection changes -- updateDisplayFiles() also
   * runs on every status poll. Quietly does nothing against a backend without the endpoint.
   */
  private refreshCoverage(): void {
    const cfg = this.pathRepositoryConfig();
    if (!cfg || this.repositoryItemsHidden || this.isProcessing || this.currentProcessingId) {
      if (!cfg) { this.coverage = []; this.coverageKey = ''; }
      return;
    }
    const nodes = this.repositoryNodeDetails();
    const request: SyncCoverageRequest = {
      data_source: this.configuredDataSource as 'alfresco' | 'nuxeo',
      url: cfg.url,
      recursive: !!cfg.recursive,
      items: nodes.length
        ? nodes.map((n: any) => ({ path: n.path, id: n.id, is_folder: !!n.isFolder }))
        : [this.pathItem(cfg.path || this.configuredFolderPath || '/')],
    };
    const key = JSON.stringify(request);
    if (key === this.coverageKey) return;
    this.coverageKey = key;
    this.coverage = [];

    this.apiService.checkSyncCoverage(request).subscribe({
      next: (res) => {
        if (key !== this.coverageKey) return;  // the selection changed while this was in flight
        this.coverage = res.enabled ? res.items : [];
        this.autoSelectFiles();
      },
      error: (err: any) => console.warn('Sync coverage check unavailable:', err),
    });
  }

  /** A typed repository path can name a file as well as a folder; an extension means file. */
  private pathItem(path: string): { path: string; is_folder: boolean } {
    const last = (path || '').split('/').pop() || '';
    return { path, is_folder: !/\.[A-Za-z0-9]{1,8}$/.test(last) };
  }

  /** Coverage for a row, when an auto-sync datasource already covers any of it. */
  coverageFor(index: number): SyncCoverageItem | null {
    // Rows and coverage line up one-to-one, except after a path-only run, when the rows can
    // be the backend's per-file list instead of the one folder that was checked.
    if (this.coverage.length !== this.displayFiles.length) return null;
    const c = this.coverage[index];
    return c && c.status !== 'none' ? c : null;
  }

  coverageLabel(index: number): string {
    const c = this.coverageFor(index);
    // "synced" only when an auto change sync covers it; otherwise it was ingested once
    const synced = !!c?.datasources.some((m) => m.auto_sync && m.status === c.status);
    switch (c?.status) {
      case 'synced': return synced ? 'already synced' : 'already ingested';
      case 'partial': return synced ? 'synced, no subfolders' : 'ingested, no subfolders';
      case 'overlaps': return synced ? 'contains synced' : 'contains ingested';
      default: return '';
    }
  }

  coverageTooltip(index: number): string {
    const c = this.coverageFor(index);
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
      ? 'Left unchecked. Check it to ingest again: the earlier copy is replaced, not duplicated.'
      : 'Part of it is already in the stores; ingesting it again refreshes that part.');
    return lines.join('\n');
  }

  get coveredRowCount(): number {
    return this.displayFiles.filter((_, i) => this.coverageFor(i)?.status === 'synced').length;
  }

  private autoSelectFiles(): void {
    if (this.configuredDataSource === 'upload') {
      this.selectedItems = new Set(this.configuredFiles.map((_, index) => index));
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      // Auto-select all repository rows except those auto-sync already covers. Mid-run the
      // selection is left alone: this also runs on every status poll.
      if (this.isProcessing) return;
      this.selectedItems = new Set(
        this.displayFiles
          .map((_, index) => index)
          .filter((index) => this.coverageFor(index)?.status !== 'synced')
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
  }

  toggleSelection(index: number, event: MatCheckboxChange): void {
    if (event.checked) {
      this.selectedItems.add(index);
    } else {
      this.selectedItems.delete(index);
    }
  }

  removeFile(index: number): void {
    if (this.configuredDataSource === 'upload') {
      // For upload files, emit event to parent to handle removal
      console.log('🗑️ Upload file removal requested for index:', index);
      this.removeUploadFile.emit(index);
      
      // Clear selection for the removed item
      this.selectedItems.delete(index);
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      // For repository files, emit event to parent to handle removal
      console.log('🗑️ Repository file removal requested for index:', index);
      this.removeRepositoryFile.emit(index);
      
      // Clear selection
      this.selectedItems.clear();
    }
  }

  removeSelectedFiles(): void {
    console.log('Remove selected files:', Array.from(this.selectedItems));
    
    if (this.configuredDataSource === 'upload') {
      // For upload files, emit removal events for each selected file (in reverse order)
      const indicesToRemove = Array.from(this.selectedItems).sort((a, b) => b - a);
      indicesToRemove.forEach(index => {
        console.log('🗑️ Upload bulk removal for index:', index);
        this.removeUploadFile.emit(index);
      });
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      // For repository files, emit event to parent to handle removal
      console.log('🗑️ Repository bulk removal requested');
      this.removeRepositoryFile.emit(0); // Emit with index 0 to hide all repository items
    }
    
    // Clear selection
    this.selectedItems.clear();
  }

  /**
   * The nodeDetails whose rows are checked. Rows used to be decoration only -- every node was
   * sent whatever was ticked -- so unchecking an already-synced row would not have kept it out.
   */
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
      
      // Add skip_graph flag to processing data
      if (this.skipGraph) {
        processingData.skip_graph = true;
        console.log('✓ skip_graph flag set to true - Knowledge graph extraction will be skipped');
      }
      
      // Add enable_sync flag to processing data
      // Only for a source that shows the checkbox: the value survives switching sources, so
      // a sync left ticked on Alfresco would otherwise make a later upload a live sync too.
      if (this.enableSync && !NO_AUTO_SYNC_SOURCES.includes(this.configuredDataSource)) {
        processingData.enable_sync = true;
        console.log('✓ enable_sync flag set to true - Incremental updates will be enabled');
      }
      
      this.apiService.ingestDocuments(processingData).subscribe({
        next: (response: AsyncProcessingResponse) => {
          console.log('Processing started:', response);
          
          if (response.processing_id) {
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
    
    // Poll every 2 seconds
    const pollInterval = setInterval(() => {
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