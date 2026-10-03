import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface SharePointSourceConfig {
  client_id: string;
  client_secret: string;
  tenant_id: string;
  site_name: string;
  site_id?: string;
  folder_path?: string;
  folder_id?: string;
}

@Component({
  selector: 'app-sharepoint-source-form',
  template: `
    <app-base-source-form 
      title="Microsoft SharePoint" 
      description="Connect to SharePoint using Azure app registration credentials">
      
      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Client ID *</mat-label>
          <input matInput
                 [(ngModel)]="clientId"
                 (ngModelChange)="onClientIdChange()"
                 placeholder="12345678-1234-1234-1234-123456789012"
                 required
                 autocomplete="off" />
          <mat-hint>Azure app registration client ID</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Tenant ID *</mat-label>
          <input matInput
                 [(ngModel)]="tenantId"
                 (ngModelChange)="onTenantIdChange()"
                 placeholder="87654321-4321-4321-4321-210987654321"
                 required
                 autocomplete="off" />
          <mat-hint>Azure tenant ID</mat-hint>
        </mat-form-field>
      </div>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Client Secret *</mat-label>
        <input matInput
               type="password"
               [(ngModel)]="clientSecret"
               (ngModelChange)="onClientSecretChange()"
               required
               autocomplete="off" />
        <mat-hint>Azure app registration client secret</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Site Name *</mat-label>
        <input matInput
               [(ngModel)]="siteName"
               (ngModelChange)="onSiteNameChange()"
               placeholder="mysite"
               required />
        <mat-hint>SharePoint site name (required)</mat-hint>
      </mat-form-field>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Folder Path</mat-label>
          <input matInput
                 [(ngModel)]="folderPath"
                 (ngModelChange)="onFolderPathChange()"
                 placeholder="/Shared Documents/Reports" />
          <mat-hint>Optional: folder path within site</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Folder ID</mat-label>
          <input matInput
                 [(ngModel)]="folderId"
                 (ngModelChange)="onFolderIdChange()"
                 placeholder="01BYE5RZ6QN6OWWLQZC5FK2GWWDURNZHIL" />
          <mat-hint>Optional: SharePoint folder ID</mat-hint>
        </mat-form-field>
      </div>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Site ID (Optional)</mat-label>
        <input matInput
               [(ngModel)]="siteId"
               (ngModelChange)="onSiteIdChange()"
               placeholder="12345678-1234-1234-1234-123456789012" />
        <mat-hint>Optional: for Sites.Selected permission</mat-hint>
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
export class SharePointSourceFormComponent implements OnInit, OnDestroy {
  @Input() siteName: string = '';
  
  @Output() siteNameChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<SharePointSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  clientId: string = '';
  clientSecret: string = '';
  tenantId: string = '';
  folderPath: string = '';
  folderId: string = '';
  siteId: string = '';

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.clientId.trim() !== '' && 
                   this.clientSecret.trim() !== '' && 
                   this.tenantId.trim() !== '' && 
                   this.siteName.trim() !== '';
    
    const config: SharePointSourceConfig = {
      client_id: this.clientId,
      client_secret: this.clientSecret,
      tenant_id: this.tenantId,
      site_name: this.siteName,
      site_id: this.siteId || undefined,
      folder_path: this.folderPath || undefined,
      folder_id: this.folderId || undefined
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onClientIdChange(): void {
    this.updateValidationAndConfig();
  }

  onClientSecretChange(): void {
    this.updateValidationAndConfig();
  }

  onTenantIdChange(): void {
    this.updateValidationAndConfig();
  }

  onSiteNameChange(): void {
    this.siteNameChange.emit(this.siteName);
    this.updateValidationAndConfig();
  }

  onFolderPathChange(): void {
    this.updateValidationAndConfig();
  }

  onFolderIdChange(): void {
    this.updateValidationAndConfig();
  }

  onSiteIdChange(): void {
    this.updateValidationAndConfig();
  }
}
