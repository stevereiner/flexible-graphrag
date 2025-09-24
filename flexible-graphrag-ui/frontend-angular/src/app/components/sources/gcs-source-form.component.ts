import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface GCSSourceConfig {
  bucket_name: string;
  project_id: string;
  credentials: string;
  prefix?: string;
  folder_name?: string;
}

@Component({
  selector: 'app-gcs-source-form',
  template: `
    <app-base-source-form 
      title="Google Cloud Storage" 
      description="Connect to Google Cloud Storage buckets">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Bucket Name *</mat-label>
        <input matInput
               [(ngModel)]="bucketName"
               (ngModelChange)="onBucketNameChange()"
               placeholder="my-gcs-bucket"
               required />
        <mat-hint>GCS bucket name (required)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Project ID *</mat-label>
        <input matInput
               [(ngModel)]="projectId"
               (ngModelChange)="onProjectIdChange()"
               placeholder="my-gcp-project"
               required />
        <mat-hint>Google Cloud project ID (required)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Service Account Credentials (JSON) *</mat-label>
        <textarea matInput
                  [(ngModel)]="credentials"
                  (ngModelChange)="onCredentialsChange()"
                  placeholder='{"type": "service_account", "project_id": "...", ...}'
                  rows="4"
                  required></textarea>
        <mat-hint>JSON service account key (required)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Prefix (Optional)</mat-label>
        <input matInput
               [(ngModel)]="prefix"
               (ngModelChange)="onPrefixChange()"
               placeholder="documents/reports/" />
        <mat-hint>Optional: folder path prefix within bucket</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Folder Name (Optional)</mat-label>
        <input matInput
               [(ngModel)]="folderName"
               (ngModelChange)="onFolderNameChange()"
               placeholder="my-folder" />
        <mat-hint>Optional: specific folder name</mat-hint>
      </mat-form-field>
    </app-base-source-form>
  `,
  styles: [`
    .full-width {
      width: 100%;
      margin-bottom: 16px;
    }
  `],
  standalone: false
})
export class GCSSourceFormComponent implements OnInit, OnDestroy {
  @Input() bucketName: string = '';
  @Input() projectId: string = '';
  @Input() credentials: string = '';
  
  @Output() bucketNameChange = new EventEmitter<string>();
  @Output() projectIdChange = new EventEmitter<string>();
  @Output() credentialsChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<GCSSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  prefix: string = '';
  folderName: string = '';

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.bucketName.trim() !== '' && 
                   this.projectId.trim() !== '' && 
                   this.credentials.trim() !== '';
    
    const config: GCSSourceConfig = {
      bucket_name: this.bucketName,
      project_id: this.projectId,
      credentials: this.credentials,
      prefix: this.prefix || undefined,
      folder_name: this.folderName || undefined
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onBucketNameChange(): void {
    this.bucketNameChange.emit(this.bucketName);
    this.updateValidationAndConfig();
  }

  onProjectIdChange(): void {
    this.projectIdChange.emit(this.projectId);
    this.updateValidationAndConfig();
  }

  onCredentialsChange(): void {
    this.credentialsChange.emit(this.credentials);
    this.updateValidationAndConfig();
  }

  onPrefixChange(): void {
    this.updateValidationAndConfig();
  }

  onFolderNameChange(): void {
    this.updateValidationAndConfig();
  }
}
