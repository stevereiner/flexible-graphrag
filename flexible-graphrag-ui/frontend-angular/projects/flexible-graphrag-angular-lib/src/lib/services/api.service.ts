import { Injectable, inject } from '@angular/core';
import { FlexibleGraphragConfigService } from '../config.service';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, catchError, throwError } from 'rxjs';
import { ProcessFolderRequest, QueryRequest, ApiResponse, IngestRequest, AsyncProcessingResponse, ProcessingStatusResponse, IngestStatusRequest, IngestStatusResponse, SyncRemoveRequest, SyncRemoveResponse, ProcessingJob } from '../models/api.models';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private apiUrl = this.fgConfig.apiUrl;

  constructor(private http: HttpClient) {}

  ingestDocuments(request: IngestRequest): Observable<AsyncProcessingResponse> {
    return this.http.post<AsyncProcessingResponse>(
      `${this.apiUrl}/ingest`,
      request
    ).pipe(
      catchError(this.handleError)
    );
  }

  getProcessingStatus(processingId: string): Observable<ProcessingStatusResponse> {
    return this.http.get<ProcessingStatusResponse>(
      `${this.apiUrl}/processing-status/${processingId}`
    ).pipe(
      catchError(this.handleError)
    );
  }

  removeFromStores(request: SyncRemoveRequest): Observable<SyncRemoveResponse> {
    return this.http.post<SyncRemoveResponse>(
      `${this.apiUrl}/sync/remove`,
      request
    ).pipe(
      catchError(this.handleError)
    );
  }

  listJobs(owner?: string): Observable<{ jobs: ProcessingJob[] }> {
    const q = owner ? `?owner=${encodeURIComponent(owner)}` : '';
    return this.http.get<{ jobs: ProcessingJob[] }>(`${this.apiUrl}/processing-status${q}`).pipe(
      catchError(this.handleError)
    );
  }

  /** Forget finished jobs (the backend keeps ones that finished in the last two minutes). */
  clearJobs(): Observable<{ cleared: number; kept: number }> {
    return this.http.delete<{ cleared: number; kept: number }>(`${this.apiUrl}/processing-status`).pipe(
      catchError(this.handleError)
    );
  }

  checkIngestStatus(request: IngestStatusRequest): Observable<IngestStatusResponse> {
    return this.http.post<IngestStatusResponse>(
      `${this.apiUrl}/sync/ingest-status`,
      request
    ).pipe(
      catchError(this.handleError)
    );
  }

  cancelProcessing(processingId: string): Observable<any> {
    return this.http.post<any>(
      `${this.apiUrl}/cancel-processing/${processingId}`,
      {}
    ).pipe(
      catchError(this.handleError)
    );
  }

  processFolder(request: ProcessFolderRequest): Observable<ApiResponse> {
    return this.http.post<ApiResponse>(
      `${this.apiUrl}/process-folder`,
      request
    ).pipe(
      catchError(this.handleError)
    );
  }

  search(request: QueryRequest): Observable<ApiResponse> {
    return this.http.post<ApiResponse>(
      `${this.apiUrl}/search`,
      request
    ).pipe(
      catchError(this.handleError)
    );
  }

  query(request: QueryRequest): Observable<ApiResponse> {
    return this.http.post<ApiResponse>(
      `${this.apiUrl}/query`,
      request
    ).pipe(
      catchError(this.handleError)
    );
  }

  getStatus(): Observable<ApiResponse> {
    return this.http.get<ApiResponse>(
      `${this.apiUrl}/status`
    ).pipe(
      catchError(this.handleError)
    );
  }

  uploadFiles(formData: FormData): Observable<any> {
    return this.http.post<any>(
      `${this.apiUrl}/upload`,
      formData
    ).pipe(
      catchError(this.handleError)
    );
  }

  private handleError(error: HttpErrorResponse) {
    let errorMessage = 'An error occurred';
    if (error.error instanceof ErrorEvent) {
      // Client-side error
      errorMessage = `Error: ${error.error.message}`;
    } else {
      // Server-side error
      errorMessage = error.error?.detail || error.message || 'Server error';
    }
    console.error('API Error:', error);
    return throwError(() => new Error(errorMessage));
  }
}
