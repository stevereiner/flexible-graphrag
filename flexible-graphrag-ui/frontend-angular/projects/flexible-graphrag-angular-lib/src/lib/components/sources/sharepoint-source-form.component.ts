import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, inject } from '@angular/core';
import { SourceBrowserService } from '../../browser/remote-browse.provider';

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
          <mat-label>Client ID</mat-label>
          <input matInput
                 [(ngModel)]="clientId"
                 (ngModelChange)="onClientIdChange()"
                 placeholder="12345678-1234-1234-1234-123456789012"
                 required
                 autocomplete="off" />
          <mat-hint>Azure app registration client ID</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Tenant ID</mat-label>
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
        <mat-label>Client Secret</mat-label>
        <input matInput
               type="password"
               [(ngModel)]="clientSecret"
               (ngModelChange)="onClientSecretChange()"
               required
               autocomplete="new-password" />
        <mat-hint>Azure app registration client secret</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Site Name</mat-label>
        <input matInput
               [(ngModel)]="siteName"
               (ngModelChange)="onSiteNameChange()"
               placeholder="mysite"
               required />
        <mat-hint>SharePoint site name (required)</mat-hint>
      </mat-form-field>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Folder Path (Optional)</mat-label>
          <input matInput
                 [(ngModel)]="folderPath"
                 (ngModelChange)="onFolderPathChange()"
                 placeholder="Reports/2024" />
          <mat-hint>Optional: a folder in the site's document library (empty: the whole library)</mat-hint>
        </mat-form-field>
        <button mat-stroked-button type="button" class="browse-button" [disabled]="!isValid()"
                [title]="isValid() ? 'Pick a folder in the site\\'s document library' : 'Fill in the site and the app credentials first'"
                (click)="browse()">
          <mat-icon>folder_open</mat-icon> Browse…
        </button>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Folder ID (Optional)</mat-label>
          <input matInput
                 [(ngModel)]="folderId"
                 (ngModelChange)="onFolderIdChange()"
                 placeholder="01BYE5RZ6QN6OWWLQZC5FK2GWWDURNZHIL" />
          <mat-hint>Optional: specific folder ID (replaces document library)</mat-hint>
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

    .browse-button {
      height: 56px;
      white-space: nowrap;
      flex: none;
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

  private readonly browser = inject(SourceBrowserService);
  // the id of the folder last browsed to: a typed path replaces it (its id would win, SharePointReader)
  private browsedId = '';
  private readonly provider = this.browser.provider('sharepoint', 'SharePoint document library', () => this.config());

  isValid(): boolean {
    return this.clientId.trim() !== '' && this.clientSecret.trim() !== '' &&
      this.tenantId.trim() !== '' && this.siteName.trim() !== '';
  }

  /** Browse the site's document library with the credentials above (POST /api/browse). */
  async browse(): Promise<void> {
    const [folder] = await this.browser.pick({
      provider: this.provider, title: `Pick a folder: ${this.siteName || 'SharePoint'}`, files: false, multiple: false,
    });
    if (!folder) return;
    this.folderPath = folder.path || '';
    this.folderId = folder.id;
    this.browsedId = folder.id;
    this.updateValidationAndConfig();
  }

  private config(): SharePointSourceConfig {
    return {
      client_id: this.clientId,
      client_secret: this.clientSecret,
      tenant_id: this.tenantId,
      site_name: this.siteName,
      site_id: this.siteId || undefined,
      folder_path: this.folderPath || undefined,
      folder_id: this.folderId || undefined
    };
  }

  private updateValidationAndConfig() {
    this.validationChange.emit(this.isValid());
    this.configurationChange.emit(this.config());
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
    if (this.browsedId && this.folderId === this.browsedId) {
      this.folderId = '';
      this.browsedId = '';
    }
    this.updateValidationAndConfig();
  }

  onFolderIdChange(): void {
    this.updateValidationAndConfig();
  }

  onSiteIdChange(): void {
    this.updateValidationAndConfig();
  }
}
