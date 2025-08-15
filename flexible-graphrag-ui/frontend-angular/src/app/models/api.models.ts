export interface ProcessFolderRequest {
  folder_path: string;
}

export interface IngestRequest {
  paths?: string[];
  data_source?: string;
  cmis_config?: {
    url: string;
    username: string;
    password: string;
    folder_path: string;
  };
  alfresco_config?: {
    url: string;
    username: string;
    password: string;
    path: string;
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
}

export interface ProcessFolderResponse extends ApiResponse {}

export interface QueryResponse extends ApiResponse {}

export interface SearchResponse extends ApiResponse {
  results: SearchResult[];
}
