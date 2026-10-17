import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface GoogleDriveSourceConfig {
  credentials: string;
  folder_id?: string;
}

@Component({
  selector: 'app-google-drive-source-form',
  template: `
    <app-base-source-form 
      title="Google Drive" 
      description="Connect to Google Drive using service account credentials">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Folder ID (Optional)</mat-label>
        <input matInput [(ngModel)]="folderId" (ngModelChange)="updateValidationAndConfig()"
               placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" autocomplete="off" />
        <mat-hint>Optional: Google Drive folder ID to process specific folder. Leave empty to process all accessible files.</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Service Account Credentials (JSON)</mat-label>
        <textarea matInput
                  [(ngModel)]="credentials"
                  (ngModelChange)="onCredentialsChange()"
                  placeholder='{"type": "service_account", "project_id": "...", ...}'
                  rows="4"
                  required></textarea>
        <mat-hint>JSON service account key (required)</mat-hint>
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
export class GoogleDriveSourceFormComponent implements OnInit, OnDestroy {
  @Input() credentials: string = '';
  folderId: string = '';
  
  @Output() credentialsChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<GoogleDriveSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  updateValidationAndConfig() {
    const isValid = this.credentials.trim() !== '';
    
    const config: GoogleDriveSourceConfig = {
      credentials: this.credentials,
      folder_id: this.folderId.trim() || undefined
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onCredentialsChange(): void {
    this.credentialsChange.emit(this.credentials);
    this.updateValidationAndConfig();
  }
}
