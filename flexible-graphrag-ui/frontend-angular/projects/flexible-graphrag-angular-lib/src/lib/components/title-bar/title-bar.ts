import { Component, Input, inject } from '@angular/core';
import { FlexibleGraphragThemeService } from '../../services/theme.service';

/**
 * An app's title bar: icon and title, anything projected after the title (a how-to line), the host
 * repository's user (app-host-identity), the sign-in pill for the other sources (app-source-sign-in,
 * which shows nothing without search sign-in) and the Dark / Light switch
 * (FlexibleGraphragThemeService). Used by the standalone Angular app and KG Spaces for Nuxeo; a host
 * with its own header and theme (ACA) uses app-host-identity and app-source-sign-in directly.
 */
@Component({
  selector: 'app-title-bar',
  template: `
    <mat-toolbar class="fg-title-bar" [class.dark-toolbar]="theme.dark" [class.light-toolbar]="!theme.dark">
      <mat-icon *ngIf="icon" class="fg-title-icon">{{ icon }}</mat-icon>
      <span class="fg-title">{{ title }}</span>
      <ng-content></ng-content>
      <span class="fg-spacer"></span>
      <app-host-identity *ngIf="hostUser" [source]="hostSource" [user]="hostUser" [url]="hostUrl"></app-host-identity>
      <app-source-sign-in *ngIf="signIn"></app-source-sign-in>
      <div *ngIf="themeSwitch" class="theme-switcher" (click)="theme.toggle()" role="switch"
           [attr.aria-checked]="!theme.dark" aria-label="Light mode" title="Dark / Light">
        <div class="toggle-track" [class.checked]="!theme.dark">
          <div class="toggle-thumb" [class.checked]="!theme.dark"></div>
        </div>
        <mat-icon class="theme-icon">{{ theme.dark ? 'dark_mode' : 'light_mode' }}</mat-icon>
        <span class="theme-text">{{ theme.dark ? 'Dark' : 'Light' }}</span>
      </div>
    </mat-toolbar>
  `,
  styles: [`
    :host { display: block; }
    .fg-title-bar { color: #ffffff; }
    .fg-title-bar.dark-toolbar { background-color: #424242; }
    .fg-title-bar.light-toolbar { background-color: #1976d2; }
    .fg-title-icon { margin-right: 8px; }
    .fg-title { white-space: nowrap; }
    .fg-spacer { flex: 1 1 auto; }
    .theme-switcher { display: flex; align-items: center; gap: 12px; cursor: pointer; user-select: none; }
    .theme-text { margin-right: 8px; font-size: 14px; }
    .toggle-track { width: 36px; height: 20px; border-radius: 10px; position: relative;
      background-color: #616161; transition: background-color 0.3s ease; }
    .toggle-track.checked { background-color: #0d47a1; }
    .toggle-thumb { width: 16px; height: 16px; border-radius: 50%; position: absolute; top: 2px; left: 2px;
      background-color: #ffffff; transition: transform 0.3s ease; }
    .toggle-thumb.checked { transform: translateX(16px); }
  `],
  standalone: false
})
export class TitleBarComponent {
  readonly theme = inject(FlexibleGraphragThemeService);

  @Input() title = 'Flexible GraphRAG';
  /** A Material icon name before the title (KG Spaces: hub). */
  @Input() icon: string | null = null;
  /** The host repository (app-host-identity); nothing shown without hostUser. */
  @Input() hostSource = 'alfresco';
  @Input() hostUser: string | null = null;
  @Input() hostUrl: string | null = null;
  /** The sign-in pill for the other sources. */
  @Input() signIn = true;
  /** The Dark / Light switch. */
  @Input() themeSwitch = true;
}
