import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { IngestSignalService } from '../../services/ingest-signal.service';
import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, inject } from '@angular/core';
import { UiDefaultsService } from '../../services/ui-defaults.service';
import { SourceBrowserService } from '../../browser/remote-browse.provider';
import { BrowseItem } from '../../browser/browse.models';

type BoxAuthMode = 'developer_token' | 'ccg_user' | 'ccg_enterprise' | 'ccg_both';

export interface BoxSourceConfig {
  client_id?: string;
  client_secret?: string;
  developer_token?: string;
  user_id?: string;
  enterprise_id?: string;
  folder_id?: string;
  /** Files picked in the browser: the ingest then reads these instead of a folder. */
  box_file_ids?: string[];
  recursive?: boolean;  // Deep: include subfolders, in the ingest and its auto sync
}

@Component({
  selector: 'app-box-source-form',
  template: `
    <app-base-source-form 
      title="Box Storage" 
      description="Connect to Box with developer token or persistent app credentials">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Authentication Type</mat-label>
        <mat-select [(ngModel)]="authMode" (ngModelChange)="onAuthModeChange()">
          <mat-option value="ccg_user">App Access (User)</mat-option>
          <mat-option value="ccg_enterprise">App Access (Enterprise)</mat-option>
          <mat-option value="ccg_both">App Access (User + Enterprise)</mat-option>
          <mat-option value="developer_token">Developer Token (expires after 1 hour)</mat-option>
        </mat-select>
      </mat-form-field>

      <div *ngIf="authMode === 'developer_token'">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Developer Token</mat-label>
          <input required matInput
                 type="password"
                 [(ngModel)]="developerToken"
                 (ngModelChange)="onDeveloperTokenChange()" autocomplete="new-password" />
          <mat-hint>Temporary token for testing (expires after 1 hour)</mat-hint>
        </mat-form-field>
      </div>

      <div *ngIf="authMode !== 'developer_token'">
        <div class="d-flex gap-2 mb-3">
          <mat-form-field appearance="outline" class="flex-1">
            <mat-label>App Client ID</mat-label>
            <input required matInput
                   [(ngModel)]="clientId"
                   (ngModelChange)="onClientIdChange()" />
          </mat-form-field>

          <mat-form-field appearance="outline" class="flex-1">
            <mat-label>App Client Secret</mat-label>
            <input required matInput
                   type="password"
                   [(ngModel)]="clientSecret"
                   (ngModelChange)="onClientSecretChange()" autocomplete="new-password" />
          </mat-form-field>
        </div>

        <mat-form-field *ngIf="authMode === 'ccg_user' || authMode === 'ccg_both'" 
                        appearance="outline" class="full-width">
          <mat-label>Box User ID</mat-label>
          <input required matInput
                 [(ngModel)]="userId"
                 (ngModelChange)="onUserIdChange()"
                 placeholder="12345678" />
          <mat-hint>Access files for a specific Box user</mat-hint>
        </mat-form-field>

        <mat-form-field *ngIf="authMode === 'ccg_enterprise' || authMode === 'ccg_both'" 
                        appearance="outline" class="full-width">
          <mat-label>Box Enterprise ID</mat-label>
          <input required matInput
                 [(ngModel)]="enterpriseId"
                 (ngModelChange)="onEnterpriseIdChange()"
                 placeholder="987654321" />
          <mat-hint>Access files across your entire Box organization</mat-hint>
        </mat-form-field>
      </div>

      <div class="path-row">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Folder ID (Optional)</mat-label>
          <input matInput
                 [(ngModel)]="folderId"
                 (ngModelChange)="onFolderIdTyped()"
                 [disabled]="files.length > 0"
                 placeholder="e.g., 123456789" />
          <mat-hint>{{ folderLabel ? 'Folder: ' + folderLabel : 'Leave empty for the root folder (All Files, ID 0)' }}</mat-hint>
        </mat-form-field>
        <button mat-stroked-button type="button" class="browse-button" [disabled]="!isValid()"
                [title]="isValid() ? 'Pick a folder or files in Box' : 'Fill in the credentials first'"
                (click)="browse()">
          <mat-icon>folder_open</mat-icon> Browse…
        </button>
        <mat-checkbox class="deep" [checked]="recursive" (change)="ownDeep = $event.checked; onFolderIdChange()"
                    title="Include subfolders, at every depth, in the ingest and its auto sync">Deep</mat-checkbox>
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
    </app-base-source-form>
  `,
  styles: [`
    .full-width {
      width: 100%;
      margin-bottom: 16px;
    }
    .d-flex {
      display: flex;
    }
    .gap-2 {
      gap: 16px;
    }
    .mb-3 {
      margin-bottom: 24px;
    }
    .flex-1 {
      flex: 1;
    }
    .path-row { display: flex; align-items: flex-start; gap: 8px; }
    .path-row .full-width { flex: 1; }
    .path-row .deep { margin-top: 12px; white-space: nowrap; }
    .browse-button { height: 56px; white-space: nowrap; flex: none; }
    .picked { margin-bottom: 16px; }
    .picked-caption { font-size: 12px; opacity: 0.8; margin-bottom: 4px; }
  `],
  standalone: false
})
export class BoxSourceFormComponent implements OnInit, OnDestroy {
  // an ingest started: the picked files empty (the run's rows stay in Processing)
  private readonly ingestStarted = inject(IngestSignalService).started
    .pipe(takeUntilDestroyed()).subscribe(() => this.clearFiles());
  @Input() clientId: string = '';
  @Input() clientSecret: string = '';
  @Input() developerToken: string = '';
  @Input() userId: string = '';
  @Input() enterpriseId: string = '';
  
  @Output() clientIdChange = new EventEmitter<string>();
  @Output() clientSecretChange = new EventEmitter<string>();
  @Output() developerTokenChange = new EventEmitter<string>();
  @Output() userIdChange = new EventEmitter<string>();
  @Output() enterpriseIdChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<BoxSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  folderId: string = '';
  // the browsed folder's name path, shown under its id (cleared when the id is typed)
  folderLabel: string = '';
  // files picked in the browser (box_file_ids: the ingest then reads these instead of a folder)
  files: BrowseItem[] = [];
  private readonly browser = inject(SourceBrowserService);
  private readonly provider = this.browser.provider('box', 'Box', () => this.config());
  authMode: BoxAuthMode = 'ccg_user';
  // Deep: include subfolders (recursive). Unset: the backend's DEFAULT_RECURSIVE, else on (Box's own default)
  private readonly uiDefaults = inject(UiDefaultsService);
  ownDeep: boolean | undefined = undefined;
  get recursive(): boolean { return this.ownDeep ?? this.uiDefaults.defaults.recursive ?? true; }

  ngOnInit() {
    this.updateValidationAndConfig();
    this.uiDefaults.load().then(() => this.updateValidationAndConfig());  // the Deep default may have changed
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  isValid(): boolean {
    switch (this.authMode) {
      case 'developer_token':
        return this.developerToken.trim() !== '';
      case 'ccg_user':
        return this.clientId.trim() !== '' && this.clientSecret.trim() !== '' && this.userId.trim() !== '';
      case 'ccg_enterprise':
        return this.clientId.trim() !== '' && this.clientSecret.trim() !== '' && this.enterpriseId.trim() !== '';
      case 'ccg_both':
        return this.clientId.trim() !== '' && this.clientSecret.trim() !== '' &&
          this.userId.trim() !== '' && this.enterpriseId.trim() !== '';
      default:
        return false;
    }
  }

  private config(): BoxSourceConfig {
    return {
      client_id: this.authMode !== 'developer_token' ? this.clientId : undefined,
      client_secret: this.authMode !== 'developer_token' ? this.clientSecret : undefined,
      developer_token: this.authMode === 'developer_token' ? this.developerToken : undefined,
      user_id: (this.authMode === 'ccg_user' || this.authMode === 'ccg_both') ? this.userId : undefined,
      enterprise_id: (this.authMode === 'ccg_enterprise' || this.authMode === 'ccg_both') ? this.enterpriseId : undefined,
      folder_id: this.folderId || undefined,
      box_file_ids: this.files.length ? this.files.map((f) => f.id) : undefined,
      recursive: this.recursive,
    };
  }

  private updateValidationAndConfig() {
    this.validationChange.emit(this.isValid());
    this.configurationChange.emit(this.config());
  }

  /** One folder (folder_id, its name path shown under the id), or files (box_file_ids). */
  async browse(): Promise<void> {
    const items = await this.browser.pick({ provider: this.provider, title: 'Pick a folder or files: Box', mixed: false });
    if (!items.length) return;
    if (items[0].isDirectory) {
      this.folderId = items[0].id;
      this.folderLabel = items[0].path || items[0].name;
      this.files = [];
    } else {
      this.files = items;
      this.folderId = '';
      this.folderLabel = '';
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

  /** A typed id replaces a browsed folder (its label) and picked files. */
  onFolderIdTyped(): void {
    this.folderLabel = '';
    if (this.folderId) this.files = [];
    this.updateValidationAndConfig();
  }

  onAuthModeChange(): void {
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

  onDeveloperTokenChange(): void {
    this.developerTokenChange.emit(this.developerToken);
    this.updateValidationAndConfig();
  }

  onUserIdChange(): void {
    this.userIdChange.emit(this.userId);
    this.updateValidationAndConfig();
  }

  onEnterpriseIdChange(): void {
    this.enterpriseIdChange.emit(this.enterpriseId);
    this.updateValidationAndConfig();
  }

  onFolderIdChange(): void {
    this.updateValidationAndConfig();
  }
}
