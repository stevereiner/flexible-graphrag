export interface ProcessFolderRequest {
  folder_path: string;
}

export interface IngestRequest {
  paths?: string[];
  data_source?: string;
  skip_graph?: boolean;  // Per-ingest flag to skip knowledge graph step (doesn't persist)
  enable_sync?: boolean; // Enable incremental sync monitoring for this datasource
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

// POST /api/sync/coverage: which auto-sync datasources already cover a repository selection
export interface SyncCoverageRequest {
  data_source: 'alfresco' | 'nuxeo';
  url?: string;
  recursive: boolean;
  items: Array<{ path: string; id?: string; is_folder: boolean }>;
}

export interface SyncCoverageMatch {
  config_id: string;
  source_name: string;
  root: string;
  recursive: boolean;
  skip_graph: boolean;
  relation: 'same' | 'inside' | 'contains' | 'indexed';
  status: 'synced' | 'partial' | 'overlaps';
  auto_sync: boolean;  // false: ingested without auto change sync
}

export interface SyncCoverageItem {
  id?: string;
  path: string;
  is_folder: boolean;
  // synced: an auto-sync datasource already covers it. partial: same folder, synced without
  // subfolders. overlaps: a folder that contains something already synced.
  status: 'synced' | 'partial' | 'overlaps' | 'none';
  datasources: SyncCoverageMatch[];
  indexed: { vector: boolean; search: boolean; graph: boolean } | null;
}

export interface SyncCoverageResponse {
  enabled: boolean;  // false when incremental sync is off on the backend
  items: SyncCoverageItem[];
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
