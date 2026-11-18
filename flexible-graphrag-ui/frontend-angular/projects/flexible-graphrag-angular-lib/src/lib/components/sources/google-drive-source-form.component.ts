import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { IngestSignalService } from '../../services/ingest-signal.service';
import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, inject } from '@angular/core';
import { SourceBrowserService } from '../../browser/remote-browse.provider';
import { BrowseItem } from '../../browser/browse.models';

export interface GoogleDriveSourceConfig {
  credentials: string;
  folder_id?: string;
  /** Files picked in the browser: the ingest reads these when there is no folder id. */
  file_ids?: string[];
}

@Component({
  selector: 'app-google-drive-source-form',
  template: `
    <app-base-source-form
      title="Google Drive"
      description="Connect to Google Drive using service account credentials">

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Folder ID</mat-label>
          <input matInput [(ngModel)]="folderId" (ngModelChange)="onFolderIdTyped()"
                 [disabled]="files.length > 0" [required]="files.length === 0"
                 placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" autocomplete="off" />
          <mat-hint>{{ folderLabel ? 'Folder: ' + folderLabel : 'A folder shared with the service account, or pick files with Browse…' }}</mat-hint>
        </mat-form-field>
        <button mat-stroked-button type="button" class="browse-button" [disabled]="!canBrowse()"
                [title]="canBrowse() ? 'Pick a folder or files in Google Drive' : 'Paste the service account credentials first'"
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
export class GoogleDriveSourceFormComponent implements OnInit, OnDestroy {
  // an ingest started: the picked files empty (the run's rows stay in Processing)
  private readonly ingestStarted = inject(IngestSignalService).started
    .pipe(takeUntilDestroyed()).subscribe(() => this.clearFiles());
  @Input() credentials: string = '';
  folderId: string = '';
  // the browsed folder's name path, shown under its id (cleared when the id is typed)
  folderLabel: string = '';
  // files picked in the browser (file_ids)
  files: BrowseItem[] = [];

  @Output() credentialsChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<GoogleDriveSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  private readonly browser = inject(SourceBrowserService);
  private readonly provider = this.browser.provider('google_drive', 'Google Drive', () => this.config());

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  /** Browse needs the credentials. */
  canBrowse(): boolean {
    return this.credentials.trim() !== '';
  }

  /** The ingest also needs a folder or files: the reader reads nothing else (a service account
   *  has no "whole drive"). */
  isValid(): boolean {
    return this.canBrowse() && (this.folderId.trim() !== '' || this.files.length > 0);
  }

  private config(): GoogleDriveSourceConfig {
    return {
      credentials: this.credentials,
      folder_id: this.folderId.trim() || undefined,
      file_ids: this.files.length ? this.files.map((f) => f.id) : undefined
    };
  }

  updateValidationAndConfig() {
    this.validationChange.emit(this.isValid());
    this.configurationChange.emit(this.config());
  }

  /** One folder (folder_id), or files (file_ids): kept apart, since a folder id wins in the ingest. */
  async browse(): Promise<void> {
    const items = await this.browser.pick({
      provider: this.provider, title: 'Pick a folder or files: Google Drive', mixed: false,
    });
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

  onFolderIdTyped(): void {
    this.folderLabel = '';
    if (this.folderId) this.files = [];
    this.updateValidationAndConfig();
  }

  onCredentialsChange(): void {
    this.credentialsChange.emit(this.credentials);
    this.updateValidationAndConfig();
  }
}
