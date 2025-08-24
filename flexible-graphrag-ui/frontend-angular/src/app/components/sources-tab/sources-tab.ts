import { Component, EventEmitter, Output } from '@angular/core';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-sources-tab',
  templateUrl: './sources-tab.html',
  styleUrls: ['./sources-tab.scss'],
  standalone: false
})
export class SourcesTabComponent {
  @Output() configureProcessing = new EventEmitter<void>();
  @Output() sourcesConfigured = new EventEmitter<{ dataSource: string; files: File[]; folderPath?: string }>();

  // State
  dataSource = 'upload';
  folderPath = '/Shared/GraphRAG';
  selectedFiles: File[] = [];
  isDragOver = false;
  isUploading = false;
  uploadProgress = 0;

  // CMIS state
  cmisUrl = `${environment.cmisBaseUrl || 'http://localhost:8080'}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  cmisUsername = 'admin';
  cmisPassword = 'admin';

  // Alfresco state
  alfrescoUrl = `${environment.alfrescoBaseUrl || 'http://localhost:8080'}/alfresco`;
  alfrescoUsername = 'admin';
  alfrescoPassword = 'admin';

  // Computed properties
  get cmisPlaceholder(): string {
    const baseUrl = environment.cmisBaseUrl || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  }

  get alfrescoPlaceholder(): string {
    const baseUrl = environment.alfrescoBaseUrl || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco`;
  }

  get dropZoneStyle(): any {
    return {
      border: this.isDragOver ? '2px solid #ffffff' : '2px dashed #ffffff',
      backgroundColor: this.isDragOver ? '#000000' : '#1976d2', // Black on hover, blue default like React
      transition: 'all 0.2s ease-in-out',
      cursor: 'pointer',
      padding: '24px',
      textAlign: 'center',
      borderRadius: '4px'
    };
  }

  // Methods
  onDataSourceChange(): void {
    // Clear state when data source changes
    this.selectedFiles = [];
    this.isDragOver = false;
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

  onFileSelect(event: Event): void {
    const target = event.target as HTMLInputElement;
    const files = target.files;
    if (files) {
      this.selectedFiles = Array.from(files);
    }
  }

  onFileDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragOver = false;
    
    const files = event.dataTransfer?.files;
    if (files) {
      this.selectedFiles = Array.from(files);
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  }

  onDragEnter(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragOver = true;
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const x = event.clientX;
    const y = event.clientY;
    
    if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
      this.isDragOver = false;
    }
  }

  removeFile(index: number): void {
    this.selectedFiles = this.selectedFiles.filter((_, i) => i !== index);
  }

  isFormValid(): boolean {
    switch (this.dataSource) {
      case 'upload':
        return this.selectedFiles.length > 0;
      case 'cmis':
        return this.folderPath.trim() !== '' && 
               this.cmisUrl.trim() !== '' && 
               this.cmisUsername.trim() !== '' && 
               this.cmisPassword.trim() !== '';
      case 'alfresco':
        return this.folderPath.trim() !== '' && 
               this.alfrescoUrl.trim() !== '' && 
               this.alfrescoUsername.trim() !== '' && 
               this.alfrescoPassword.trim() !== '';
      default:
        return false;
    }
  }

  onConfigureProcessing(): void {
    this.sourcesConfigured.emit({
      dataSource: this.dataSource,
      files: this.selectedFiles,
      folderPath: this.folderPath
    });
    this.configureProcessing.emit();
  }
}