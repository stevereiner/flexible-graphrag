import { Component, Input } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';
import { SourceDocument } from '../../models/api.models';

/**
 * The documents a search result or an answer came from, each one a link when it can be opened:
 * the host's own viewer first (`openDocument`, e.g. ACA for Alfresco nodes), otherwise the
 * backend's `open_url` (Alfresco Share, Nuxeo Web UI) in a new tab, otherwise plain text.
 */
@Component({
  selector: 'app-source-docs',
  template: `
    <span class="source-docs" *ngIf="docs?.length">
      <span *ngIf="label" class="source-docs-label">{{ label }}</span>
      <ng-container *ngFor="let doc of docs; let last = last">
        <a *ngIf="canOpen(doc); else plain" href="" class="source-doc-link" (click)="open($event, doc)"
           [title]="doc.path || doc.name">{{ doc.name }}</a>
        <ng-template #plain><span class="source-doc" [title]="doc.path || doc.name">{{ doc.name }}</span></ng-template>
        <span *ngIf="!last">, </span>
      </ng-container>
    </span>
  `,
  styles: [`
    .source-docs-label { font-weight: 600; margin-right: 4px; }
    .source-doc-link { color: #1976d2; text-decoration: none; cursor: pointer; }
    .source-doc-link:hover { text-decoration: underline; }
    :host-context(.dark-theme) .source-doc-link { color: #90caf9; }
  `],
  standalone: false
})
export class SourceDocsComponent {
  @Input() docs: SourceDocument[] | null | undefined = [];
  /** Text before the list, e.g. "Sources:". */
  @Input() label = '';

  constructor(private fgConfig: FlexibleGraphragConfigService) {}

  canOpen(doc: SourceDocument): boolean {
    return this.fgConfig.canOpenDocument(doc) || !!doc.open_url;
  }

  open(event: Event, doc: SourceDocument): void {
    event.preventDefault();
    if (this.fgConfig.openDocument(doc)) return;
    if (doc.open_url) window.open(doc.open_url, '_blank', 'noopener');
  }
}
