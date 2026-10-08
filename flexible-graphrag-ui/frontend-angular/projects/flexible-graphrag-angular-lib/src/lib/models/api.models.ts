export interface ProcessFolderRequest {
  folder_path: string;
}

// Ask about one repository document or folder only (POST /api/search `scope`)
export interface AskScope {
  data_source: 'alfresco' | 'nuxeo';
  url?: string;
  node_id?: string;
  path?: string;     // a folder covers everything below it
  is_folder: boolean;
  name?: string;     // shown as "Asking about: <name>"
}

export type ItemActionKind = 'ingest' | 'ingest_no_graph' | 'remove_graph' | 'remove_all' | 'keep';

export interface ItemAction {
  path: string;
  id?: string;
  is_folder: boolean;
  action: ItemActionKind;
  // Auto Sync column: false stops this row's sync, true resumes it; omitted = no change
  auto_sync?: boolean;
}

// GET /api/processing-status: processing jobs, oldest first
export interface ProcessingJob {
  processing_id: string;
  kind: 'ingest' | 'sync';
  status: 'started' | 'processing' | 'completed' | 'failed' | 'cancelled';
  message?: string;
  progress: number;
  data_source?: string;
  label?: string;
  sync_action?: 'add' | 'update' | 'delete';  // auto sync runs
  owner?: string;
  started_at?: string;
  updated_at?: string;
}

export interface IngestRequest {
  paths?: string[];
  data_source?: string;
  skip_graph?: boolean;  // Per-ingest flag to skip knowledge graph step (doesn't persist)
  enable_sync?: boolean; // Enable incremental sync monitoring for this datasource
  // Per-row actions (Alfresco/Nuxeo): what each checked row should end up as. The backend runs
  // removals, then an ingest pass with graphs and one without, as ONE job.
  item_actions?: ItemAction[];
  owner?: string;  // who started it, for the jobs list
  cmis_config?: {
    url: string;
    username: string;
    password: string;
    folder_path: string;
  };
  alfresco_config?: {
    url: string;
    auth_method?: string;
    username?: string;
    password?: string;
    oauth2?: {
      client_id?: string;
      client_secret?: string;
      token_endpoint?: string;
      scope?: string;
      access_token?: string;
      refresh_token?: string;
    };
    path: string;
  };
  nuxeo_config?: {
    url: string;
    auth_method?: string;
    username?: string;
    password?: string;
    token?: string;
    oauth2?: {
      client_id?: string;
      client_secret?: string;
      access_token?: string;
      refresh_token?: string;
      token_endpoint?: string;
    };
    path?: string;
  };
}

export interface QueryRequest {
  query: string;
  top_k?: number;
}

export interface SearchResult {
  rank: number;
  content: string;
  score: number;
  source: string;
  file_type: string;
  file_name: string;
  metadata?: {
    source?: string;
  };
}

export interface ApiResponse<T = any> {
  status: string;
  message?: string;
  answer?: string;
  results?: SearchResult[];
  system_status?: any;
  success?: boolean;  // For legacy compatibility
  error?: string;
}

// New async processing response
export interface AsyncProcessingResponse {
  processing_id: string;
  status: 'started' | 'processing' | 'completed' | 'failed' | 'cancelled';
  message: string;
  progress?: number;
  estimated_time?: string;
  started_at?: string;
  updated_at?: string;
  error?: string;
}

// POST /api/sync/ingest-status: which auto-sync datasources already cover a repository selection
export interface IngestStatusRequest {
  // upload: items are uploaded file names; filesystem: backend paths
  data_source: 'alfresco' | 'nuxeo' | 'upload' | 'filesystem';
  url?: string;
  recursive: boolean;
  items: Array<{ path: string; id?: string; is_folder: boolean }>;
}

export interface IngestStatusMatch {
  config_id: string;
  source_name: string;
  root: string;
  recursive: boolean;
  skip_graph: boolean;
  relation: 'same' | 'inside' | 'contains' | 'indexed';
  status: 'synced' | 'partial' | 'overlaps';
  auto_sync: boolean;  // false: ingested without auto change sync
}

export interface IngestStatusItem {
  id?: string;
  path: string;
  is_folder: boolean;
  // synced: an auto-sync datasource already covers it. partial: same folder, synced without
  // subfolders. overlaps: a folder that contains something already synced. removed: a file an
  // auto sync holds, taken out of every store (the sync now leaves it out until it is ingested again).
  status: 'synced' | 'partial' | 'overlaps' | 'removed' | 'none';
  datasources: IngestStatusMatch[];
  indexed: { vector: boolean; search: boolean; graph: boolean } | null;
  auto_sync?: boolean;  // followed by an auto sync now (per document: document_state.auto_sync)
}

// Which delete targets have a store behind them; any store can be "none" in .env.
// graph = the property graph and/or the RDF store.
export interface ConfiguredStores {
  vector: boolean;
  search: boolean;
  graph: boolean;
}

export interface IngestStatusResponse {
  enabled: boolean;  // false when incremental sync is off on the backend
  stores?: ConfiguredStores;  // absent from a 0.8.2 backend
  items: IngestStatusItem[];
}

export type RemoveTarget = 'vector' | 'search' | 'graph';

// POST /api/sync/remove: take a repository selection back out of some or all stores
export interface SyncRemoveRequest extends IngestStatusRequest {
  targets: RemoveTarget[];
}

export interface SyncRemoveResponse {
  status: string;
  targets: RemoveTarget[];
  documents: number;            // documents deleted from at least one store
  forgotten: number;            // ingest-only document_state rows dropped
  datasources_dropped: number;  // ingest-only datasources left with nothing
  items: Array<{ id?: string; path: string; documents: number; kept_out_of_auto_sync: number }>;
}

// Processing status check response
export interface ProcessingStatusResponse {
  processing_id: string;
  status: 'started' | 'processing' | 'completed' | 'failed' | 'cancelled';
  message: string;
  progress: number;
  started_at: string;
  updated_at: string;
  error?: string;
  // Additional fields for dynamic progress tracking
  current_file?: string;
  current_phase?: string;
  files_completed?: number;
  total_files?: number;
  file_progress?: string;
  estimated_time_remaining?: string;
  // Individual file progress tracking
  individual_files?: Array<{
    filename: string;
    status: string;
    progress: number;
    phase: string;
    message?: string;
    error?: string;
    started_at?: string;
    completed_at?: string;
  }>;
}

export interface ProcessFolderResponse extends ApiResponse {}

export interface QueryResponse extends ApiResponse {}

export interface SearchResponse extends ApiResponse {
  results: SearchResult[];
}
