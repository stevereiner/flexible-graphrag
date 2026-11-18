import { Component, EventEmitter, OnDestroy, OnInit, Output, inject } from '@angular/core';
import { Subscription } from 'rxjs';
import { SourceBrowserService } from '../../browser/remote-browse.provider';
import { localBrowseProvider } from '../../browser/local-browse.provider';
import { DesktopLocalService, LocalFilesConfig, LocalItem } from '../../desktop/desktop-local.service';

/**
 * Local files and folders (desktop app only): picked with the file browser, ingested by path as
 * the filesystem source (folders with everything below them), and kept in sync when Auto Sync is
 * on. The picked paths are added to the backend's allowed ingest folders (DesktopLocalService).
 */
@Component({
  selector: 'app-local-folder-form',
  template: `
    <app-base-source-form
      title="Local Files and Folders"
      description="Files and folders on this computer. A folder includes everything below it.">
      <div class="local-actions">
        <button mat-stroked-button type="button" class="browse-button" (click)="browse()">
          <mat-icon>folder_open</mat-icon> Browse…
        </button>
        <button mat-button type="button" class="local-clear" *ngIf="items.length" (click)="setItems([])">Clear</button>
      </div>

      <p class="local-empty" *ngIf="!items.length">Nothing picked yet.</p>      <ul class="local-list" *ngIf="items.length">
        <li *ngFor="let item of items" class="local-item">
          <mat-icon class="local-icon">{{ item.isDirectory ? 'folder' : 'description' }}</mat-icon>
          <span class="local-path" [title]="item.path">{{ item.path }}</span>
          <button mat-icon-button type="button" class="local-remove" title="Leave out"
                  [attr.aria-label]="'Leave out ' + item.path" (click)="remove(item)">
            <mat-icon>delete</mat-icon>
          </button>
        </li>
      </ul>

      <div class="local-notice" *ngIf="notice" [class.local-warning]="noticeWarning" role="status">
        <span>{{ notice }}</span>
        <button mat-icon-button type="button" aria-label="Close" (click)="notice = ''"><mat-icon>close</mat-icon></button>
      </div>
    </app-base-source-form>
  `,
  styles: [`
    .local-actions { display: flex; gap: 8px; margin-bottom: 8px; }
    .browse-button { height: 40px; }
    .local-empty { font-size: 14px; opacity: 0.7; }
    .local-list { list-style: none; padding: 0; margin: 0 0 8px; }
    .local-item { display: flex; align-items: center; gap: 8px; padding: 2px 0; color: inherit; }
    .local-icon { opacity: 0.8; flex: none; }
    .local-path { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .local-remove { flex: none; color: inherit; }
    .local-notice {
      display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 8px;
      padding: 4px 4px 4px 12px; border-radius: 4px; background: rgba(33, 150, 243, 0.12); color: inherit;
    }
    .local-notice.local-warning { background: rgba(255, 152, 0, 0.16); }
  `],
  standalone: false
})
export class LocalFolderFormComponent implements OnInit, OnDestroy {
  @Output() configurationChange = new EventEmitter<LocalFilesConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  private readonly browser = inject(SourceBrowserService);
  private readonly local = inject(DesktopLocalService);
  private sub?: Subscription;

  items: LocalItem[] = [];
  notice = '';
  noticeWarning = false;

  ngOnInit(): void {
    // the picks live in DesktopLocalService: a row removed on the Processing tab leaves here too
    this.sub = this.local.itemChanges.subscribe((items) => {
      this.items = items;
      this.validationChange.emit(items.length > 0);
      this.configurationChange.emit(DesktopLocalService.configOf(items));
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }

  setItems(items: LocalItem[]): void {
    this.local.setItems(items);
  }

  remove(item: LocalItem): void {
    this.setItems(this.items.filter((i) => i.path !== item.path));
  }

  async browse(): Promise<void> {
    const picked = await this.browser.pick({
      provider: localBrowseProvider, title: 'Add files and folders from this computer',
    });
    // picks add up (several folders) until an ingest starts (DesktopLocalService then empties the list)
    const add = picked
      .map((p) => ({ path: p.path || p.id, isDirectory: p.isDirectory }))
      .filter((p) => !this.items.some((i) => i.path === p.path));
    if (!add.length) return;
    this.setItems([...this.items, ...add]);
    const result = await this.local.addLocalRoots(add.map((a) => a.path));
    this.notice = result.message || '';
    this.noticeWarning = !result.ok;
  }
}
