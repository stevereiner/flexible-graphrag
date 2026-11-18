import { ChangeDetectorRef, Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTableModule } from '@angular/material/table';
import { BrowseItem, SourceBrowserData, browseStartTrail, saveBrowseTrail } from './browse.models';

const MAX_PAGES = 50;

/**
 * A read-only picker over any BrowseProvider (Material + CDK only, no ADF, so it also works inside
 * KG Spaces' ACA app with its own ADF). One folder level at a time: a breadcrumb back up, folders
 * first, a folder opens when its name is clicked, checkboxes select. Closes with the picked items
 * (undefined when cancelled). The rules and messages follow the React SourceBrowser.
 */
@Component({
  selector: 'fg-source-browser-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatCheckboxModule, MatIconModule,
    MatProgressBarModule, MatTableModule],
  template: `
    <h2 mat-dialog-title>{{ data.title || ('Browse ' + data.provider.label) }}</h2>
    <mat-dialog-content class="fg-browser">
      <div class="fg-browser-error" *ngIf="error" role="alert">
        <mat-icon>warning</mat-icon><span>{{ error }}</span>
      </div>

      <div class="fg-browser-bar">
        <nav class="fg-crumbs" aria-label="Folder">
          <button mat-button type="button" class="fg-crumb" (click)="goTo(0)" [disabled]="!trail.length">
            <mat-icon>home</mat-icon>{{ data.provider.label }}
          </button>
          <ng-container *ngFor="let f of trail; let i = index; let last = last">
            <span class="fg-crumb-sep">/</span>
            <button mat-button type="button" class="fg-crumb" (click)="goTo(i + 1)" [disabled]="last">{{ f.name }}</button>
          </ng-container>
        </nav>
        <button mat-icon-button type="button" (click)="refresh()" [disabled]="loading" title="Refresh">
          <mat-icon>refresh</mat-icon>
        </button>
      </div>
      <mat-progress-bar *ngIf="loading" mode="indeterminate"></mat-progress-bar>

      <div class="fg-browser-table">
        <table mat-table [dataSource]="items">
          <ng-container matColumnDef="select">
            <th mat-header-cell *matHeaderCellDef class="fg-col-select">
              <mat-checkbox *ngIf="data.multiple !== false" [checked]="allSelected()"
                            [indeterminate]="selected.size > 0 && !allSelected()"
                            (change)="toggleAll($event.checked)" [disabled]="!items.length"></mat-checkbox>
            </th>
            <td mat-cell *matCellDef="let item" class="fg-col-select">
              <mat-checkbox [checked]="selected.has(item)" (change)="toggle(item, $event.checked)"></mat-checkbox>
            </td>
          </ng-container>
          <ng-container matColumnDef="name">
            <th mat-header-cell *matHeaderCellDef>Name</th>
            <td mat-cell *matCellDef="let item">
              <span class="fg-name">
                <mat-icon class="fg-icon">{{ item.isDirectory ? 'folder' : 'description' }}</mat-icon>
                <a *ngIf="item.isDirectory; else plain" href="" (click)="$event.preventDefault(); open(item)"
                   [title]="'Open ' + item.name">{{ item.name }}</a>
                <ng-template #plain><span [title]="item.path || item.name">{{ item.name }}</span></ng-template>
              </span>
            </td>
          </ng-container>
          <ng-container matColumnDef="size">
            <th mat-header-cell *matHeaderCellDef class="fg-col-size">Size</th>
            <td mat-cell *matCellDef="let item" class="fg-col-size">{{ item.isDirectory ? '' : formatSize(item.size) }}</td>
          </ng-container>
          <ng-container matColumnDef="modified">
            <th mat-header-cell *matHeaderCellDef class="fg-col-modified">Modified</th>
            <td mat-cell *matCellDef="let item" class="fg-col-modified">{{ formatDate(item.modified) }}</td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="columns; sticky: true"></tr>
          <tr mat-row *matRowDef="let item; columns: columns" [class.fg-row-selected]="selected.has(item)"
              (click)="rowClick(item, $event)" (dblclick)="rowDoubleClick(item)"></tr>
        </table>
        <div class="fg-empty" *ngIf="!loading && !items.length && !error">This folder is empty.</div>
      </div>

      <div class="fg-caption">{{ caption() }}</div>
      <div class="fg-problem" *ngIf="selectionProblem()">{{ selectionProblem() }}</div>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" (click)="cancel()">Cancel</button>
      <button mat-button type="button" [disabled]="!currentFolder()" (click)="pick([currentFolder()!])">
        {{ replaces() ? 'Use this folder' : 'Add this folder' }}
      </button>
      <button mat-flat-button color="primary" type="button"
              [disabled]="!selected.size || !!selectionProblem()" (click)="pick(selectedItems())">
        {{ (replaces() ? 'Use' : 'Add') + ' selected' + (data.multiple !== false && selected.size ? ' (' + selected.size + ')' : '') }}
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .fg-browser { min-height: 50vh; display: flex; flex-direction: column; }
    .fg-browser-error {
      display: flex; align-items: center; gap: 8px; padding: 8px 12px; margin-bottom: 8px; border-radius: 4px;
      background: rgba(255, 152, 0, 0.12); color: inherit;
    }
    .fg-browser-bar { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .fg-crumbs { display: flex; align-items: center; flex-wrap: wrap; min-width: 0; }
    .fg-crumb { min-width: 0; padding: 0 6px; }
    .fg-crumb mat-icon { margin-right: 4px; }
    .fg-crumb-sep { opacity: 0.6; }
    .fg-browser-table { flex: 1; overflow: auto; max-height: 55vh; }
    table { width: 100%; }
    .fg-col-select { width: 48px; }
    .fg-col-size { width: 96px; white-space: nowrap; text-align: right; }
    .fg-col-modified { width: 180px; white-space: nowrap; }
    .fg-name { display: inline-flex; align-items: center; gap: 6px; }
    .fg-icon { opacity: 0.7; }
    .fg-name a { color: inherit; text-decoration: none; font-weight: 500; }
    .fg-name a:hover { text-decoration: underline; }
    .fg-row-selected { background: rgba(25, 118, 210, 0.08); }
    .mat-mdc-row { cursor: pointer; user-select: none; }
    .fg-empty { padding: 24px; text-align: center; opacity: 0.7; }
    .fg-caption { margin-top: 8px; font-size: 12px; opacity: 0.7; }
    .fg-problem { font-size: 12px; color: #ed6c02; }
  `],
})
export class SourceBrowserDialogComponent implements OnInit {
  readonly data = inject<SourceBrowserData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<SourceBrowserDialogComponent, BrowseItem[]>);
  private readonly cdr = inject(ChangeDetectorRef);

  readonly columns = ['select', 'name', 'size', 'modified'];
  /** The folders opened from the root down to the one shown. */
  trail: BrowseItem[] = [];
  items: BrowseItem[] = [];
  selected = new Set<BrowseItem>();
  loading = false;
  error = '';
  private readonly cache = new Map<string, BrowseItem[]>();
  private loadSeq = 0;

  ngOnInit(): void {
    this.restore();
  }

  /** Open at the folder last open in this source's browser when its root is still among the roots
   *  and it still lists, else at the roots. */
  private async restore(): Promise<void> {
    const seq = ++this.loadSeq;
    this.loading = true;
    this.cdr.markForCheck();
    try {
      const [listedRoots, saved] = await Promise.all([this.data.provider.roots(), browseStartTrail(this.data.provider)]);
      const roots = this.sorted(listedRoots);
      if (seq !== this.loadSeq) return;
      this.cache.set('', roots);
      const root = saved.length ? roots.find((r) => r.id === saved[0].id) : undefined;
      if (root) {
        const folders = [root, ...saved.slice(1)];
        const last = folders[folders.length - 1];
        try {
          const items = this.sorted(await this.listAll(last, seq));
          if (seq !== this.loadSeq) return;
          this.cache.set(`id:${last.id}`, items);
          this.trail = folders;
          this.items = items;
          return;
        } catch { /* gone or unreadable now: the roots */ }
      }
      if (seq === this.loadSeq) this.items = roots;
    } catch (e: any) {
      if (seq === this.loadSeq) this.error = `Could not list ${this.data.provider.label}: ${e?.message || e}`;
    } finally {
      if (seq === this.loadSeq) {
        this.loading = false;
        this.cdr.markForCheck();
      }
    }
  }

  /** All of one folder's children, page by page (stops early when another folder was opened). */
  private async listAll(folder: BrowseItem, seq: number): Promise<BrowseItem[]> {
    const items: BrowseItem[] = [];
    let token: string | null | undefined = null;
    for (let page = 0; page < MAX_PAGES; page++) {
      const listing = await this.data.provider.list(folder, token);
      items.push(...listing.items);
      token = listing.nextPageToken;
      if (!token || seq !== this.loadSeq) break;
    }
    return items;
  }

  private sorted(items: BrowseItem[]): BrowseItem[] {
    return [...items].sort((a, b) =>
      Number(b.isDirectory) - Number(a.isDirectory) || a.name.toLowerCase().localeCompare(b.name.toLowerCase()));
  }

  currentFolder(): BrowseItem | null {
    return this.trail.length ? this.trail[this.trail.length - 1] : null;
  }

  open(folder: BrowseItem): void {
    this.trail = [...this.trail, folder];
    this.load();
  }

  /** Back up to the n-th breadcrumb (0 = the root). */
  goTo(n: number): void {
    this.trail = this.trail.slice(0, n);
    this.load();
  }

  refresh(): void {
    this.load(true);
  }

  private async load(refresh = false): Promise<void> {
    const folder = this.currentFolder();
    const key = folder ? `id:${folder.id}` : '';
    const seq = ++this.loadSeq;
    this.selected = new Set();
    this.error = '';
    saveBrowseTrail(this.data.provider.key, this.trail);
    const cached = refresh ? undefined : this.cache.get(key);
    if (cached) {
      this.items = cached;
      this.cdr.markForCheck();
      return;
    }
    this.items = [];
    this.loading = true;
    this.cdr.markForCheck();
    try {
      const listed = folder ? await this.listAll(folder, seq) : await this.data.provider.roots();
      if (seq !== this.loadSeq) return;  // another folder was opened meanwhile
      const items = this.sorted(listed);
      this.cache.set(key, items);
      this.items = items;
    } catch (e: any) {
      if (seq !== this.loadSeq) return;
      const where = folder ? (folder.path || folder.name) : this.data.provider.label;
      this.error = `Could not list ${where}: ${e?.message || e}`;
    } finally {
      if (seq === this.loadSeq) {
        this.loading = false;
        this.cdr.markForCheck();
      }
    }
  }

  toggle(item: BrowseItem, checked: boolean): void {
    const next = this.data.multiple === false ? new Set<BrowseItem>() : new Set(this.selected);
    if (checked) next.add(item); else next.delete(item);
    this.selected = next;
  }

  /** A click on a row (not its checkbox or folder link) selects it or clears it, as in a file manager. */
  rowClick(item: BrowseItem, event: MouseEvent): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest('mat-checkbox, a, button')) return;
    this.toggle(item, !this.selected.has(item));
  }

  /** Double-click: a folder opens; a file stays selected (its two clicks would otherwise cancel out). */
  rowDoubleClick(item: BrowseItem): void {
    window.getSelection()?.removeAllRanges();
    if (item.isDirectory) {
      this.open(item);
    } else {
      this.toggle(item, true);
    }
  }

  toggleAll(checked: boolean): void {
    this.selected = checked ? new Set(this.items) : new Set();
  }

  allSelected(): boolean {
    return this.items.length > 0 && this.selected.size === this.items.length;
  }

  selectedItems(): BrowseItem[] {
    return this.items.filter((i) => this.selected.has(i));
  }

  /** The pick replaces what the form had (one folder / one list), rather than adding to it. */
  replaces(): boolean {
    return this.data.multiple === false || this.data.mixed === false;
  }

  /** Why the selection can't be used (the source's config can't hold it), '' when it can. */
  selectionProblem(): string {
    const allowFiles = this.data.files !== false;
    const multiple = this.data.multiple !== false;
    const mixed = this.data.mixed !== false;
    const sel = this.selectedItems();
    const folders = sel.filter((s) => s.isDirectory).length;
    if (!allowFiles && sel.some((s) => !s.isDirectory)) return 'Pick a folder: this source takes a folder, not files.';
    if (!multiple && sel.length > 1) {
      return allowFiles ? 'Pick one folder or file: this source takes a single path.'
        : 'Pick one folder: this source takes a single folder.';
    }
    if (!mixed && folders > 0 && sel.length > 1) {
      return 'Pick one folder, or files only: this source takes a folder or a list of files.';
    }
    return '';
  }

  caption(): string {
    const allowFiles = this.data.files !== false;
    const multiple = this.data.multiple !== false;
    const mixed = this.data.mixed !== false;
    if (!multiple && allowFiles) return 'Click a folder\'s name to open it. Select one folder or file, or use the folder you are in.';
    if (!mixed && allowFiles) return 'Click a folder\'s name to open it. Select one folder or several files, or use the folder you are in.';
    if (multiple || allowFiles) return 'Click a folder\'s name to open it. Select files and folders, or add the folder you are in.';
    return 'Click a folder\'s name to open it. Select a folder, or use the folder you are in.';
  }

  pick(items: BrowseItem[]): void {
    this.ref.close(items);
  }

  cancel(): void {
    this.ref.close(undefined);
  }

  formatSize(size?: number): string {
    if (size === undefined || size === null) return '';
    if (size < 1024) return `${size} B`;
    const units = ['KB', 'MB', 'GB', 'TB'];
    let v = size / 1024;
    let u = 0;
    while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
    return `${v < 10 ? v.toFixed(1) : Math.round(v)} ${units[u]}`;
  }

  formatDate(iso?: string): string {
    if (!iso) return '';
    const d = new Date(iso);
    return isNaN(d.getTime()) ? iso : d.toLocaleString();
  }
}
