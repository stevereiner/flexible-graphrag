import { Component, Input, Output, EventEmitter, OnInit, OnChanges, SimpleChanges } from '@angular/core';
import { MatCheckboxChange } from '@angular/material/checkbox';
import { ApiService } from '../../services/api.service';
import { AsyncProcessingResponse, ProcessingStatusResponse } from '../../models/api.models';

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
                                 changes['configuredWebConfig'] ||
                                 changes['configuredWikipediaConfig'] ||
                                 changes['configuredYoutubeConfig'] ||
                                 changes['configuredCloudConfig'] ||
                                 changes['configuredEnterpriseConfig'];
    
    if (configurationChanged) {
      // Clear old processing messages when configuration changes
      this.successMessage = '';
      this.error = '';
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
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco') {
      // If repository items are explicitly hidden, show nothing
      if (this.repositoryItemsHidden) {
        this.displayFiles = [];
        return;
      }
      
      // Only use individual files from status data if we're currently processing
      // or if the processing was for the current repository configuration
      const individualFiles = (this.isProcessing || this.currentProcessingId) ? 
        (this.statusData?.individual_files || this.lastStatusData?.individual_files || []) : [];
      if (individualFiles.length > 0) {
        this.displayFiles = individualFiles.map((file: any, index: number) => {
          // Show full path instead of extracting just filename
          const displayName = file.filename || `File ${index + 1}`;
          
          return {
            index,
            name: displayName, // Use full path as display name
            size: 0, // Repository files don't have size info
            type: 'repository-file'
          };
        });
      } else {
        // Default to repository path when no individual files yet - show full path
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
  }

  private autoSelectFiles(): void {
    if (this.configuredDataSource === 'upload') {
      this.selectedItems = new Set(this.configuredFiles.map((_, index) => index));
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco') {
      // Auto-select all repository files (whether individual files or repository path)
      this.selectedItems = new Set(this.displayFiles.map((_, index) => index));
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
      return progressData.progress || 0;
    }
    
    // Fallback to overall progress for repository files when no individual data
    if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco') {
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
      const phase = progressData.phase || 'ready';
      const phaseNames: { [key: string]: string } = {
        'ready': 'Ready',
        'waiting': 'Waiting',
        'docling': 'Converting',
        'chunking': 'Chunking',
        'kg_extraction': 'Extracting Graph',
        'indexing': 'Indexing',
        'completed': 'Completed',
        'error': 'Error'
      };
      return phaseNames[phase] || phase;
    }
    
    // Fallback for repository files
    if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco') {
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
      return progressData.status || 'ready';
    }
    
    // Fallback for repository files
    if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco') {
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
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco') {
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
    } else if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco') {
      // For repository files, emit event to parent to handle removal
      console.log('🗑️ Repository bulk removal requested');
      this.removeRepositoryFile.emit(0); // Emit with index 0 to hide all repository items
    }
    
    // Clear selection
    this.selectedItems.clear();
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
        const uploadedPaths = await this.uploadFiles();
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
        processingData.paths = [this.configuredFolderPath || '/Sites/swsdp/documentLibrary']; // Use configured path
        processingData.alfresco_config = {
          url: 'http://localhost:8080',
          username: 'admin',
          password: 'admin',
          path: this.configuredFolderPath || '/Sites/swsdp/documentLibrary'
        };
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
      if (this.enableSync) {
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

  private uploadFiles(): Promise<string[]> {
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
            // Fallback: use original file names
            uploadedPaths = this.configuredFiles.map(f => f.name);
          }
          
          resolve(uploadedPaths);
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