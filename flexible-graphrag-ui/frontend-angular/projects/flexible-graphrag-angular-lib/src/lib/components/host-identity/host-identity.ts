import { Component, Input } from '@angular/core';
import { SOURCE_COLORS, labelOf } from '../../services/source-auth.service';

/**
 * Who the user is in the host's own repository -- "Alfresco · admin" in KG Spaces for ACA, "Nuxeo ·
 * Administrator" in KG Spaces for Nuxeo -- for a title bar. Read-only: the host's session is the
 * sign-in there, so there is no sign-out or server switch (the sign-in pill leaves that server out).
 * Renders nothing without a user.
 */
@Component({
  selector: 'app-host-identity',
  template: `
    <span *ngIf="user" class="host-identity" [class.light]="light" [title]="tooltip">
      <span class="dot" [style.background]="color"></span>
      <mat-icon>account_circle</mat-icon>
      <span class="host-label">{{ label }} · {{ user }}</span>
    </span>
  `,
  styles: [`
    :host { display: inline-flex; align-items: center; margin-right: 12px; }
    .host-identity { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 12px;
      border-radius: 18px; background: rgba(255, 255, 255, 0.1); color: inherit; font-size: 14px; white-space: nowrap; }
    .host-identity.light { background: rgba(0, 0, 0, 0.06); }
    .host-identity mat-icon { font-size: 20px; width: 20px; height: 20px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
    .host-label { max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
  `],
  standalone: false
})
export class HostIdentityComponent {
  /** The host repository's source type: alfresco | nuxeo | cmis | ... */
  @Input() source = 'alfresco';
  /** The signed-in user there; nothing is shown without one. */
  @Input() user: string | null = null;
  /** The repository's server, for the tooltip. */
  @Input() url: string | null = null;
  /** For a light background (ACA's page) instead of a coloured toolbar. */
  @Input() light = false;

  get label(): string {
    return labelOf(this.source);
  }

  get color(): string {
    return SOURCE_COLORS[this.source] || '#66bb6a';
  }

  get tooltip(): string {
    return `Signed in to ${this.label}${this.url ? ' (' + this.url + ')' : ''} as ${this.user}`;
  }
}
