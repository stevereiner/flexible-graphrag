import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { IngestSignalService } from '../../services/ingest-signal.service';
import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, inject } from '@angular/core';
import { SourceBrowserService } from '../../browser/remote-browse.provider';
import { BrowseItem } from '../../browser/browse.models';

export interface OneDriveSourceConfig {
  user_principal_name: string;
  client_id: string;
  client_secret: string;
  tenant_id: string;
  folder_path?: string;
  folder_id?: string;
  /** Files picked in the browser: the ingest then reads these instead of a folder. */
  file_ids?: string[];
}

@Component({
  selector: 'app-onedrive-source-form',
  template: `
    <app-base-source-form
      title="Microsoft OneDrive"
      description="Connect to OneDrive using Azure app registration credentials">

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>User Principal Name</mat-label>
          <input matInput
                 [(ngModel)]="userPrincipalName"
                 (ngModelChange)="onUserPrincipalNameChange()"
                 placeholder="user@domain.com"
                 required />
          <mat-hint>User principal name (email)</mat-hint>
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Client ID</mat-label>
          <input matInput
                 [(ngModel)]="clientId"
                 (ngModelChange)="onClientIdChange()"
                 placeholder="12345678-1234-1234-1234-123456789012"
                 required />
        </mat-form-field>
      </div>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Client Secret</mat-label>
          <input matInput
                 type="password"
                 [(ngModel)]="clientSecret"
                 (ngModelChange)="onClientSecretChange()"
                 required autocomplete="new-password" />
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Tenant ID</mat-label>
          <input matInput
                 [(ngModel)]="tenantId"
                 (ngModelChange)="onTenantIdChange()"
                 placeholder="common or tenant-id"
                 required />
        </mat-form-field>
      </div>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Folder Path (Optional)</mat-label>
          <input matInput
                 [(ngModel)]="folderPath"
                 (ngModelChange)="onFolderPathChange()"
                 [disabled]="files.length > 0"
                 placeholder="Documents/Reports" />
          <mat-hint>Optional: a folder in the user's drive (empty: the whole drive)</mat-hint>
        </mat-form-field>
        <button mat-stroked-button type="button" class="browse-button" [disabled]="!isValid()"
                [title]="isValid() ? 'Pick a folder or files in OneDrive' : 'Fill in the user and the app credentials first'"
                (click)="browse()">
          <mat-icon>folder_open</mat-icon> Browse…
        </button>
      </div>

      <div class="picked" *ngIf="files.length">
        <div class="picked-caption">
          {{ files.length === 1 ? '1 file picked' : files.length + ' files picked' }}: the ingest reads these instead of a folder
        </div>
        <mat-chip-set>
          <mat-chip *ngFor="let f of files" (removed)="removeFile(f)" [title]="f.path || f.name">
            {{ f.path || f.name }}
            <button matChipRemove type="button" [attr.aria-label]="'Remove ' + f.name"><mat-icon>cancel</mat-icon></button>
          </mat-chip>
        </mat-chip-set>
        <button mat-button type="button" (click)="clearFiles()">Clear</button>
      </div>

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

    .browse-button {
      height: 56px;
      white-space: nowrap;
      flex: none;
    }

    .picked {
      margin-bottom: 16px;
    }

    .picked-caption {
      font-size: 12px;
      opacity: 0.8;
      margin-bottom: 4px;
    }
  `],
  standalone: false
})
export class OneDriveSourceFormComponent implements OnInit, OnDestroy {
  // an ingest started: the picked files empty (the run's rows stay in Processing)
  private readonly ingestStarted = inject(IngestSignalService).started
    .pipe(takeUntilDestroyed()).subscribe(() => this.clearFiles());
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
  /** Files picked in the browser (file_ids). */
  files: BrowseItem[] = [];

  private readonly browser = inject(SourceBrowserService);
  private readonly provider = this.browser.provider('onedrive', 'OneDrive', () => this.config());

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  isValid(): boolean {
    return this.userPrincipalName.trim() !== '' && this.clientId.trim() !== '' &&
      this.clientSecret.trim() !== '' && this.tenantId.trim() !== '';
  }

  /** One folder (folder_path), or files (file_ids): the browser keeps the two apart. */
  async browse(): Promise<void> {
    const items = await this.browser.pick({
      provider: this.provider, title: `Pick a folder or files: ${this.userPrincipalName || 'OneDrive'}`, mixed: false,
    });
    if (!items.length) return;
    if (items[0].isDirectory) {
      this.folderPath = items[0].path || '';
      this.files = [];
    } else {
      this.files = items;
      this.folderPath = '';
    }
    this.updateValidationAndConfig();
  }

  removeFile(file: BrowseItem): void {
    this.files = this.files.filter((f) => f !== file);
    this.updateValidationAndConfig();
  }

  clearFiles(): void {
    this.files = [];
    this.updateValidationAndConfig();
  }

  private config(): OneDriveSourceConfig {
    return {
      user_principal_name: this.userPrincipalName,
      client_id: this.clientId,
      client_secret: this.clientSecret,
      tenant_id: this.tenantId,
      folder_path: this.folderPath || undefined,
      folder_id: this.folderId || undefined,
      file_ids: this.files.length ? this.files.map((f) => f.id) : undefined
    };
  }

  private updateValidationAndConfig() {
    this.validationChange.emit(this.isValid());
    this.configurationChange.emit(this.config());
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
    if (this.folderPath) this.files = [];
    this.updateValidationAndConfig();
  }

  onFolderIdChange(): void {
    this.updateValidationAndConfig();
  }
}
