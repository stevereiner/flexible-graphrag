export interface IngestRequest {
  data_source: string;
  paths?: string[];
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
  web_config?: {
    url: string;
  };
  wikipedia_config?: {
    query: string;
    language?: string;
    max_docs?: number;
  };
  youtube_config?: {
    url: string;
    chunk_size_seconds?: number;
  };
  s3_config?: any;
  gcs_config?: any;
  azure_blob_config?: any;
  onedrive_config?: any;
  sharepoint_config?: any;
  box_config?: any;
  google_drive_config?: any;
}

export interface QueryRequest {
  query: string;
  query_type?: string;
  top_k?: number;
}

/** A document a search result or an answer came from (backend doc_refs.py). */
export interface SourceDocument {
  doc_id: string;
  name: string;
  path: string;
  source_type: string;  // 'alfresco' | 'nuxeo' | '' (other sources)
  node_id: string;      // repository node id (Alfresco / Nuxeo)
  parent_id?: string;   // an Alfresco document's folder id ('' when unknown)
  open_url: string;     // link to the document (Alfresco Share, Nuxeo Web UI); '' when none
}

export interface ApiResponse {
  success?: boolean;  // Used by search endpoint
  status?: string;    // Used by ingest endpoint
  message?: string;
  error?: string;
  answer?: string;
  sources?: SourceDocument[];  // the documents an answer came from
  results?: any[];
}

// New async processing response
export interface AsyncProcessingResponse {
  processing_id: string;
  status: 'started' | 'processing' | 'completed' | 'failed';
  message: string;
  progress?: number;
  estimated_time?: string;
  started_at?: string;
  updated_at?: string;
  error?: string;
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
  current_file?: string;
  current_phase?: string;
  files_completed?: number;
  total_files?: number;
  estimated_time_remaining?: string;
}

export interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  queryType?: 'search' | 'qa';
  results?: any[];
  sources?: SourceDocument[];
  isLoading?: boolean;
}

export interface FileDisplayInfo {
  name: string;
  size: number;
  type: 'file' | 'path' | 'repository' | 'repository-file' | 'web-source' | 'wikipedia-source' | 'youtube-source' | 'cloud-source';
}
