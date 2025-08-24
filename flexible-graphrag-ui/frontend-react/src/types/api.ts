export interface IngestRequest {
  data_source: string;
  paths?: string[];
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
  query_type?: string;
  top_k?: number;
}

export interface ApiResponse {
  success?: boolean;  // Used by search endpoint
  status?: string;    // Used by ingest endpoint
  message?: string;
  error?: string;
  answer?: string;
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
  isLoading?: boolean;
}

export interface FileDisplayInfo {
  name: string;
  size: number;
  type: 'file' | 'path' | 'repository' | 'repository-file';
}
