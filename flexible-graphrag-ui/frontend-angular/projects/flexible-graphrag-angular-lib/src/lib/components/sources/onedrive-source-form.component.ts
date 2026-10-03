import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface OneDriveSourceConfig {
  user_principal_name: string;
  client_id: string;
  client_secret: string;
  tenant_id: string;
  folder_path?: string;
  folder_id?: string;
}

@Component({
  selector: 'app-onedrive-source-form',
  template: `
    <app-base-source-form 
      title="Microsoft OneDrive" 
      description="Connect to OneDrive using Azure app registration credentials">
      
      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>User Principal Name *</mat-label>
          <input matInput
                 [(ngModel)]="userPrincipalName"
                 (ngModelChange)="onUserPrincipalNameChange()"
                 placeholder="user@domain.com"
                 required />
          <mat-hint>User principal name (email)</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Client ID *</mat-label>
          <input matInput
                 [(ngModel)]="clientId"
                 (ngModelChange)="onClientIdChange()"
                 placeholder="12345678-1234-1234-1234-123456789012"
                 required />
        </mat-form-field>
      </div>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Client Secret *</mat-label>
          <input matInput
                 type="password"
                 [(ngModel)]="clientSecret"
                 (ngModelChange)="onClientSecretChange()"
                 required />
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Tenant ID *</mat-label>
          <input matInput
                 [(ngModel)]="tenantId"
                 (ngModelChange)="onTenantIdChange()"
                 placeholder="common or tenant-id"
                 required />
        </mat-form-field>
      </div>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Folder Path (Optional)</mat-label>
        <input matInput
               [(ngModel)]="folderPath"
               (ngModelChange)="onFolderPathChange()"
               placeholder="/Documents/Reports" />
        <mat-hint>Optional: specific folder path in OneDrive</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Folder ID (Optional)</mat-label>
        <input matInput
               [(ngModel)]="folderId"
               (ngModelChange)="onFolderIdChange()"
               placeholder="01BYE5RZ6QN6OWWLQZC5FK2GWWDURNZHIL" />
        <mat-hint>Optional: specific OneDrive folder ID</mat-hint>
      </mat-form-field>
    </app-base-source-form>
  `,
  styles: [`
    .full-width {
      width: 100%;
      margin-bottom: 16px;
    }
    
    .form-row {
      display: flex;
      gap: 16px;
      margin-bottom: 16px;
    }
    
    .half-width {
      flex: 1;
    }
  `],
  standalone: false
})
export class OneDriveSourceFormComponent implements OnInit, OnDestroy {
  @Input() userPrincipalName: string = '';
  @Input() clientId: string = '';
  @Input() clientSecret: string = '';
  @Input() tenantId: string = '';
  
  @Output() userPrincipalNameChange = new EventEmitter<string>();
  @Output() clientIdChange = new EventEmitter<string>();
  @Output() clientSecretChange = new EventEmitter<string>();
  @Output() tenantIdChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<OneDriveSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  folderPath: string = '';
  folderId: string = '';

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.userPrincipalName.trim() !== '' && 
                   this.clientId.trim() !== '' && 
                   this.clientSecret.trim() !== '' && 
                   this.tenantId.trim() !== '';
    
    const config: OneDriveSourceConfig = {
      user_principal_name: this.userPrincipalName,
      client_id: this.clientId,
      client_secret: this.clientSecret,
      tenant_id: this.tenantId,
      folder_path: this.folderPath || undefined,
      folder_id: this.folderId || undefined
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onUserPrincipalNameChange(): void {
    this.userPrincipalNameChange.emit(this.userPrincipalName);
    this.updateValidationAndConfig();
  }

  onClientIdChange(): void {
    this.clientIdChange.emit(this.clientId);
    this.updateValidationAndConfig();
  }

  onClientSecretChange(): void {
    this.clientSecretChange.emit(this.clientSecret);
    this.updateValidationAndConfig();
  }

  onTenantIdChange(): void {
    this.tenantIdChange.emit(this.tenantId);
    this.updateValidationAndConfig();
  }

  onFolderPathChange(): void {
    this.updateValidationAndConfig();
  }

  onFolderIdChange(): void {
    this.updateValidationAndConfig();
  }
}
