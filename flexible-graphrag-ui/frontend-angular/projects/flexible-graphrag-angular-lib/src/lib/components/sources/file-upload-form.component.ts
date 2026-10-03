import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface FileUploadConfig {
  files: File[];
}

@Component({
  selector: 'app-file-upload-form',
  template: `
    <app-base-source-form 
      title="File Upload" 
      description="Upload documents directly from your computer">
      
      <div class="drop-zone" 
           [ngStyle]="dropZoneStyle"
           (drop)="onFileDrop($event)"
           (dragover)="onDragOver($event)"
           (dragenter)="onDragEnter($event)"
           (dragleave)="onDragLeave($event)"
           (click)="fileInput.click()">
        <h3 style="color: #ffffff; margin-bottom: 8px;">
          Drop files here or click to select
        </h3>
        <p style="color: #ffffff; margin: 0;">
          Supports: PDF, DOCX, XLSX, PPTX, TXT, MD, HTML, CSV, PNG, JPG
        </p>
        <input #fileInput
               type="file"
               multiple
               accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.html,.csv,.png,.jpg,.jpeg"
               (change)="onFileSelect($event)"
               style="display: none" />
      </div>

      <div *ngIf="selectedFiles.length > 0" class="selected-files">
        <h4>Selected Files ({{ selectedFiles.length }}):</h4>
        <mat-card *ngFor="let file of selectedFiles; let i = index" class="file-card">
          <mat-card-content class="file-content">
            <div class="file-info">
              <div class="file-name">{{ file.name }}</div>
              <div class="file-size">{{ formatFileSize(file.size) }}</div>
            </div>
            <button mat-button color="warn" (click)="removeFile(i)">
              Remove
            </button>
          </mat-card-content>
        </mat-card>
      </div>
    </app-base-source-form>
  `,
  styles: [`
    .drop-zone {
      padding: 24px;
      text-align: center;
      cursor: pointer;
      border-radius: 4px;
      margin-bottom: 16px;
      transition: all 0.2s ease-in-out;
    }
    
    .selected-files {
      margin-top: 16px;
    }
    
    .file-card {
      margin-bottom: 8px;
    }
    
    .file-content {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px !important;
    }
    
    .file-info {
      flex: 1;
    }
    
    .file-name {
      font-weight: 500;
    }
    
    .file-size {
      font-size: 12px;
      color: var(--mat-sys-on-surface-variant);
    }
    
    /* Fallback for older Material versions */
    :host-context(.mat-app-background) .file-size {
      color: rgba(0, 0, 0, 0.6);
    }
    
    /* Dark theme support */
    :host-context(.dark-theme) .file-size,
    :host-context([data-theme="dark"]) .file-size {
      color: rgba(255, 255, 255, 0.7);
    }
  `],
  standalone: false
})
export class FileUploadFormComponent implements OnInit, OnDestroy {
  @Input() selectedFiles: File[] = [];
  @Output() selectedFilesChange = new EventEmitter<File[]>();
  @Output() configurationChange = new EventEmitter<FileUploadConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  isDragOver = false;

  get dropZoneStyle() {
    return {
      border: this.isDragOver ? '2px solid #ffffff' : '2px dashed #ffffff',
      backgroundColor: this.isDragOver ? '#000000' : '#1976d2',
      transition: 'all 0.2s ease-in-out'
    };
  }

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.selectedFiles.length > 0;
    const config: FileUploadConfig = {
      files: this.selectedFiles
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
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
      requestAnimationFrame(() => {
        const fileArray = Array.from(files);
        this.selectedFiles = fileArray;
        this.selectedFilesChange.emit(this.selectedFiles);
        this.updateValidationAndConfig();
        target.value = '';
      });
    }
  }

  onFileDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragOver = false;
    
    const files = event.dataTransfer?.files;
    if (files) {
      requestAnimationFrame(() => {
        const fileArray = Array.from(files);
        this.selectedFiles = fileArray;
        this.selectedFilesChange.emit(this.selectedFiles);
        this.updateValidationAndConfig();
      });
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
    this.selectedFilesChange.emit(this.selectedFiles);
    this.updateValidationAndConfig();
  }
}
