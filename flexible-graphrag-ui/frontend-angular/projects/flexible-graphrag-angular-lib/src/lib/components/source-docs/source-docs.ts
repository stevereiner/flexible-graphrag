import { Component, Input, inject } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';
import { SourceDocument } from '../../models/api.models';
import { desktopInvoke, isDesktopApp, isDesktopRemoteBackend, isLocalPath } from '../../desktop/desktop-bridge';
import { DesktopLocalService } from '../../desktop/desktop-local.service';

/**
 * The documents a search result or an answer came from, each one a link when it can be opened:
 * the host's own viewer first (`openDocument`, e.g. ACA for Alfresco nodes), otherwise the
 * backend's `open_url` (Alfresco Share, Nuxeo Web UI) in a new tab, otherwise plain text. In the
 * desktop app a local file opens with its default app, and its folder icon shows it in its folder
 * (desktop/src-tauri/src/open_file.rs, which opens only files inside the folders added in the app
 * or the backend's own allowed folders, DesktopLocalService.openRoots).
 */
@Component({
  selector: 'app-source-docs',
  template: `
    <span class="source-docs" *ngIf="docs?.length">
      <span *ngIf="label" class="source-docs-label">{{ label }}</span>
      <ng-container *ngFor="let doc of docs; let last = last">
        <a *ngIf="canOpen(doc); else localOrPlain" href="" class="source-doc-link" (click)="open($event, doc)"
           [title]="doc.path || doc.name">{{ doc.name }}</a>
        <ng-template #localOrPlain>
          <ng-container *ngIf="isLocal(doc); else plain">
            <a href="" class="source-doc-link" (click)="openLocal($event, doc.path!, false)"
               [title]="'Open ' + doc.path">{{ doc.name }}</a>
            <button type="button" class="source-doc-reveal" title="Show in folder"
                    [attr.aria-label]="'Show ' + doc.name + ' in its folder'"
                    (click)="openLocal($event, doc.path!, true)">
              <mat-icon>folder_open</mat-icon>
            </button>
          </ng-container>
        </ng-template>
        <ng-template #plain><span class="source-doc" [title]="doc.path || doc.name">{{ doc.name }}</span></ng-template>
        <span *ngIf="!last">, </span>
      </ng-container>
      <span *ngIf="localError" class="source-docs-error">{{ localError }}</span>
    </span>
  `,
  styles: [`
    .source-docs-label { font-weight: 600; margin-right: 4px; }
    .source-doc-link { color: #1976d2; text-decoration: none; cursor: pointer; }
    .source-doc-link:hover { text-decoration: underline; }
    :host-context(.dark-theme) .source-doc-link { color: #90caf9; }
    .source-doc-reveal {
      border: none; background: none; padding: 0 2px; margin-left: 2px; cursor: pointer; color: inherit;
      vertical-align: middle; line-height: 1;
    }
    .source-doc-reveal mat-icon { font-size: 14px; width: 14px; height: 14px; }
    .source-docs-error { display: block; color: #f44336; font-size: 0.8em; }
  `],
  standalone: false
})
export class SourceDocsComponent {
  @Input() docs: SourceDocument[] | null | undefined = [];
  /** Text before the list, e.g. "Sources:". */
  @Input() label = '';

  private readonly desktop = isDesktopApp();
  private readonly local = inject(DesktopLocalService);
  localError = '';

  constructor(private fgConfig: FlexibleGraphragConfigService) {}

  canOpen(doc: SourceDocument): boolean {
    return this.fgConfig.canOpenDocument(doc) || !!doc.open_url;
  }

  /** A local file the desktop app can open (desktop app only): on this computer, so not a remote
   *  backend's document, nor with the app's backend on another machine. */
  isLocal(doc: SourceDocument): boolean {
    return this.desktop && !doc.backend && !isDesktopRemoteBackend() && isLocalPath(doc.path);
  }

  open(event: Event, doc: SourceDocument): void {
    event.preventDefault();
    if (this.fgConfig.openDocument(doc)) return;
    if (doc.open_url) window.open(doc.open_url, '_blank', 'noopener');
  }

  openLocal(event: Event, path: string, reveal: boolean): void {
    event.preventDefault();
    this.localError = '';
    this.local.openRoots()
      .then((roots) => desktopInvoke<void>('open_local_file', { path, roots, reveal }))
      .catch((e) => (this.localError = String(e)));
  }
}
