import { Component, EventEmitter, Input, OnDestroy, OnInit, Output, inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { Subscription } from 'rxjs';
import { FlexibleGraphragConfigService } from '../../config.service';
import {
  AuthProvider, AuthRequirements, AvailableSource, SOURCE_COLORS, SignInReason, SourceAuthService, SourceKind, SourceSession,
  credentialLabels, ingestCredential, isKeySource, isPopupSource, labelOf, providerCaption, providerTitle, providerTooltip, sameServer, serverKey, signInFor, sourceKey,
} from '../../services/source-auth.service';

const providerKey = (p: AuthProvider) => `${p.source}|${serverKey(p.source, p.url)}`;

/**
 * Header control for the repository sign-ins (planning/SOURCE-AUTH-LOGIN.md): ONE pill
 * ("Sign-ins 1/3", or "Nuxeo: Administrator" with a single server) whose menu lists every server
 * whose documents are in the stores -- signed in (its colour, the user, Sign out) or offline
 * (Sign in). Renders nothing without search sign-in (FlexibleGraphragConfigService.searchSignIn).
 * The server a host's own ticket covers (ACA's Alfresco in KG Spaces) is not listed: the host
 * already identifies the user there.
 */
@Component({
  selector: 'app-source-sign-in',
  template: `
    <ng-container *ngIf="fgConfig.searchSignIn && rows.length">
      <button *ngIf="!compact" mat-button class="sign-in-pill" [class.light]="light" [class.connected]="signedInCount > 0" [class.missing]="missingCount > 0"
              [matMenuTriggerFor]="signInMenu" [title]="pillTitle">
        <mat-icon>account_circle</mat-icon>
        <span class="pill-label">{{ pillLabel }}</span>
        <mat-icon iconPositionEnd>arrow_drop_down</mat-icon>
      </button>
      <!-- compact: an icon with a signed-in count, for a narrow toolbar (ACA's) -->
      <button *ngIf="compact" mat-icon-button class="sign-in-icon" [class.missing]="missingCount > 0"
              [matMenuTriggerFor]="signInMenu" [title]="pillTitle" aria-label="Repository sign-ins">
        <mat-icon>account_circle</mat-icon>
        <span class="count" [class.all]="signedInCount === rows.length">{{ signedInCount }}/{{ rows.length }}</span>
      </button>
      <mat-menu #signInMenu="matMenu" xPosition="before" class="fg-sign-in-menu">
        <div class="menu-title">REPOSITORY SIGN-INS</div>
        <div *ngFor="let r of rows" class="menu-row" (click)="$event.stopPropagation()">
          <span class="dot" [style.background]="r.session ? (colors[r.provider.source] || '#66bb6a') : '#9e9e9e'"></span>
          <div class="menu-text">
            <div><strong>{{ providerTitle(r.provider) }}</strong>
              <span *ngIf="r.session"> {{ r.session.user_id }}</span><em *ngIf="!r.session" class="offline"> offline</em></div>
            <div class="menu-url" [title]="providerTooltip(r.provider)">{{ providerCaption(r.provider) }}</div>
          </div>
          <button *ngIf="r.session" mat-button (click)="auth.signOut(r.session)">Sign out</button>
          <button *ngIf="!r.session" mat-stroked-button (click)="auth.promptSignIn(r.provider)">Sign in</button>
        </div>
      </mat-menu>
    </ng-container>
  `,
  styles: [`
    :host { display: inline-flex; align-items: center; margin-right: 12px; }
    .sign-in-pill {
      color: inherit !important; border-radius: 16px; padding: 0 8px 0 10px; height: 32px;
      background: rgba(255, 255, 255, 0.1); --mat-button-text-label-text-color: currentColor;
    }
    .sign-in-pill.connected { background: rgba(255, 255, 255, 0.22); }
    .sign-in-pill.missing { outline: 1px dashed rgba(255, 255, 255, 0.6); }
    /* light: on a light background (KG Spaces' tab bar in ACA) instead of a dark app header */
    .sign-in-pill.light { background: rgba(0, 0, 0, 0.04); border: 1px solid rgba(0, 0, 0, 0.18); height: 36px; }
    .sign-in-pill.light.connected { background: rgba(33, 150, 243, 0.08); border-color: rgba(33, 150, 243, 0.45); }
    .sign-in-pill.light.missing { outline: none; border-style: dashed; }
    .sign-in-pill mat-icon { margin: 0 4px; }
    .sign-in-pill .pill-label { display: inline-block; max-width: 180px; overflow: hidden; text-overflow: ellipsis;
      white-space: nowrap; vertical-align: middle; }
    .sign-in-icon { position: relative; color: inherit !important; }
    .sign-in-icon.missing mat-icon { opacity: 0.7; }
    .sign-in-icon .count {
      position: absolute; right: -2px; bottom: 2px; font-size: 10px; line-height: 14px; padding: 0 3px;
      border-radius: 7px; background: #9e9e9e; color: #fff;
    }
    .sign-in-icon .count.all { background: #43a047; }
    ::ng-deep .fg-sign-in-menu { max-width: 460px !important; }
    ::ng-deep .fg-sign-in-menu .menu-title { padding: 4px 16px 8px; font-size: 11px; letter-spacing: 1px; opacity: 0.7; }
    ::ng-deep .fg-sign-in-menu .menu-row { display: flex; align-items: center; gap: 12px; padding: 6px 16px; min-width: 340px; }
    ::ng-deep .fg-sign-in-menu .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
    /* the menu theme's own text colour, not the host page's (a dark page's white text on this
       light panel was invisible) */
    ::ng-deep .fg-sign-in-menu .menu-text { flex: 1; min-width: 0; font-size: 14px;
      color: var(--mat-menu-item-label-text-color, rgba(0, 0, 0, 0.87)); }
    ::ng-deep .fg-sign-in-menu .menu-title { color: var(--mat-menu-item-label-text-color, rgba(0, 0, 0, 0.87)); }
    ::ng-deep .fg-sign-in-menu .menu-url { font-size: 12px; opacity: 0.7; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 280px; }
    ::ng-deep .fg-sign-in-menu .offline { opacity: 0.7; }
  `],
  standalone: false
})
export class SourceSignInComponent implements OnInit, OnDestroy {
  readonly auth = inject(SourceAuthService);
  readonly fgConfig = inject(FlexibleGraphragConfigService);
  readonly labelOf = labelOf;
  readonly colors = SOURCE_COLORS;
  readonly providerTitle = providerTitle;
  readonly providerCaption = providerCaption;
  readonly providerTooltip = providerTooltip;
  /** Icon + signed-in count instead of the labelled pill (e.g. in ACA's toolbar); the menu is the same. */
  @Input() compact = false;
  /** Styled for a light background (e.g. KG Spaces' tab bar in ACA) rather than a dark header. */
  @Input() light = false;
  rows: { provider: AuthProvider; session: SourceSession | null }[] = [];
  missingCount = 0;
  private sub?: Subscription;

  get signedInCount(): number { return this.rows.filter((r) => r.session).length; }
  /** Short: the name before the @ (full names and servers are in the tooltip and the menu). */
  get pillLabel(): string {
    if (this.rows.length === 1) {
      const r = this.rows[0];
      return `${providerTitle(r.provider)}: ${r.session ? r.session.user_id.split('@')[0] : 'offline'}`;
    }
    return `Sign-ins ${this.signedInCount}/${this.rows.length}`;
  }
  get pillTitle(): string {
    return this.rows.map((r) => `${providerTitle(r.provider)}: ${r.session ? r.session.user_id : 'offline'}`).join('\n');
  }

  ngOnInit(): void {
    this.sub = this.auth.sessions$.subscribe(async () => {
      this.rows = await this.auth.signInRows();
      this.missingCount = (await this.auth.missingProviders()).length;
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}

/** The sign-in dialog. Closes with true when signed in, false for "Continue without" / dismiss. */
@Component({
  selector: 'app-source-sign-in-dialog',
  template: `
    <h2 mat-dialog-title>Sign in to {{ label }}</h2>
    <mat-dialog-content>
      <p *ngIf="reason === 'ingest'">
        Sign in to add documents from {{ label }}. The same sign-in is used for search and AI chat.
      </p>
      <p *ngIf="reason !== 'ingest'">
        {{ docs ? docs + ' document(s) from ' + label + ' are in the stores. ' : 'The stores may hold ' + label + ' documents. ' }}
        Sign in to search and ask about the ones you may read.
      </p>
      <!-- dynamic: the hint takes two lines in the dialog, and a fixed one-line subscript ran it into the field below -->
      <mat-form-field *ngIf="reason === 'ask' && servers.length > 1; else oneServer" appearance="outline" class="full-width"
                      subscriptSizing="dynamic">
        <mat-label>Server</mat-label>
        <mat-select [(ngModel)]="selectedKey">
          <mat-option *ngFor="let p of servers" [value]="key(p)">
            {{ labelOf(p.source) }}: {{ p.url }}{{ p.documents != null ? ' (' + p.documents + ' document' + (p.documents === 1 ? '' : 's') + ')' : '' }}
          </mat-option>
        </mat-select>
        <mat-hint>Sign in to each server you want answers from; the others' documents are left out</mat-hint>
      </mat-form-field>
      <ng-template #oneServer>
        <ng-container *ngIf="current as c"><div *ngIf="c.url && !isKey" class="url">{{ c.url }}</div></ng-container>
      </ng-template>
      <div *ngIf="error" class="error">{{ error }}</div>
      <p *ngIf="isPopup">
        Signs in at {{ label }} in a new window (allow pop-ups for this site).
        <ng-container *ngIf="current?.source === 'microsoft'">One sign-in covers SharePoint and OneDrive.</ng-container>
        <ng-container *ngIf="current?.source === 'google'">One sign-in covers Google Drive and Cloud Storage.</ng-container>
      </p>
      <ng-container *ngIf="!isPopup">
        <p *ngIf="isKey">Your AWS access key is used once to start a session (12 hours by default); only that session is kept, in this browser tab.</p>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>{{ fieldLabels[0] }}</mat-label>
          <input matInput [(ngModel)]="username" autocomplete="off" cdkFocusInitial />
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>{{ fieldLabels[1] }}</mat-label>
          <input matInput type="password" [(ngModel)]="password" autocomplete="new-password"
                 (keydown.enter)="username.trim() && password && signIn()" />
        </mat-form-field>
      </ng-container>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button [disabled]="busy" (click)="continueWithout()">{{ reason === 'ingest' ? 'Cancel' : 'Continue without' }}</button>
      <button *ngIf="isPopup" mat-flat-button color="primary" [disabled]="busy" (click)="signInPopup()">
        {{ busy ? 'Waiting for ' + label + '…' : 'Sign in with ' + label }}
      </button>
      <button *ngIf="!isPopup" mat-flat-button color="primary" [disabled]="busy || !username.trim() || !password || !current" (click)="signIn()">
        Sign in
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    /* block + a gap: in a host with denser form fields (ACA) a field's floating label otherwise
       overlaps the field above it */
    .full-width { width: 100%; display: block; margin-top: 8px; }
    .url { font-size: 0.85rem; opacity: 0.8; margin-bottom: 12px; word-break: break-all; }
    .error { color: #f44336; margin-bottom: 12px; }
  `],
  standalone: false
})
export class SourceSignInDialogComponent {
  private readonly auth = inject(SourceAuthService);
  private readonly ref = inject(MatDialogRef<SourceSignInDialogComponent, boolean>);
  private readonly data = inject<{ provider: AuthProvider | null; reason?: SignInReason }>(MAT_DIALOG_DATA);
  readonly provider: AuthProvider | null = this.data?.provider ?? null;
  readonly reason: SignInReason = this.data?.reason ?? 'ask';
  readonly labelOf = labelOf;
  readonly key = providerKey;
  // servers with documents in the stores and no sign-in yet -- the dialog lets the user pick one
  missing: AuthProvider[] = this.provider ? [this.provider] : [];
  selectedKey = this.provider ? providerKey(this.provider) : '';

  constructor() {
    if (this.reason === 'ask') {
      this.auth.missingProviders(true).then((list) => {
        if (list.length) this.missing = list;
        if (!this.missing.some((p) => providerKey(p) === this.selectedKey) && this.missing.length) {
          this.selectedKey = providerKey(this.missing[0]);
        }
      });
    }
  }
  username = '';
  password = '';
  error = '';
  busy = false;

  get current(): AuthProvider | null {
    return this.missing.find((p) => providerKey(p) === this.selectedKey) || this.provider;
  }
  /** One source per dialog (Alfresco, then Nuxeo, ...): its servers in the picker. */
  get servers(): AuthProvider[] { return this.missing.filter((p) => p.source === this.current?.source); }
  get label(): string { return labelOf(this.current?.source || 'alfresco'); }
  get docs(): number | null | undefined { return this.current?.documents; }
  get isPopup(): boolean { return isPopupSource(this.current?.source); }
  get isKey(): boolean { return isKeySource(this.current?.source); }
  get fieldLabels(): [string, string] { return credentialLabels(this.current?.source); }

  /** Microsoft 365 / Box: auth.signInPopup opens the popup synchronously, so call it first in the click. */
  async signInPopup(): Promise<void> {
    const signingIn = this.auth.signInPopup(this.current!.source as SourceKind);
    this.busy = true;
    this.error = '';
    try {
      await signingIn;
      this.ref.close(true);
    } catch (err: any) {
      this.error = err?.error?.detail || err?.message || 'Sign-in failed';
    } finally {
      this.busy = false;
    }
  }

  async signIn(): Promise<void> {
    const p = this.current;
    if (!p) return;
    this.busy = true;
    this.error = '';
    try {
      await this.auth.signIn(p.source as SourceKind, this.username.trim(), this.password, p.url || undefined);
      this.ref.close(true);
    } catch (err: any) {
      this.error = err?.error?.detail || 'Sign-in failed';
    } finally {
      this.busy = false;
    }
  }

  continueWithout(): void {
    if (this.reason === 'ask') this.auth.continueWithout();  // only questions remember "without"
    this.ref.close(false);
  }
}

/**
 * A data-source form's sign-in row: "Signed in to X as Y (used for this ingest)" with Sign out /
 * Use other credentials, or a "Sign in to X" button -- the same sign-in the header and search /
 * chat use. Hidden when the host already covers the server (KG Spaces' own Alfresco).
 */
@Component({
  selector: 'app-source-sign-in-section',
  template: `
    <div class="sign-in-row" *ngIf="auth.active && !hostCovered">
      <ng-container *ngIf="session as s; else notSignedIn">
        <span>Signed in to {{ label }} as <strong>{{ s.user_id }}</strong>{{ useOther ? '' : ' (used for this ingest)' }}</span>
        <button mat-button type="button" (click)="auth.signOut(s)">Sign out</button>
        <mat-checkbox [ngModel]="useOther" (ngModelChange)="useOtherChange.emit($event)">
          {{ source === 'alfresco' ? 'Use other credentials (e.g. for Auto Sync)' : 'Use other credentials' }}
        </mat-checkbox>
      </ng-container>
      <ng-template #notSignedIn>
        <button mat-stroked-button type="button" [disabled]="!url.trim()" (click)="signIn()">Sign in to {{ label }}</button>
        <span class="hint">or enter credentials below</span>
      </ng-template>
    </div>
  `,
  styles: [`
    .sign-in-row { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
    .sign-in-row .hint { opacity: 0.7; }
  `],
  standalone: false
})
export class SourceSignInSectionComponent {
  readonly auth = inject(SourceAuthService);
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  @Input() source: SourceKind = 'alfresco';
  @Input() url = '';
  @Input() useOther = false;
  @Output() useOtherChange = new EventEmitter<boolean>();

  get label(): string { return labelOf(this.source); }
  get hostCovered(): boolean { return this.fgConfig.hostCovers(this.source, this.url); }
  get session(): SourceSession | null {
    return this.auth.sessions.find((s) => s.source === this.source && sameServer(this.source, s.url, this.url)) || null;
  }

  signIn(): void {
    this.auth.promptSignIn({ source: this.source, url: this.url, methods: ['basic'], documents: null }, 'ingest');
  }
}

/**
 * The sign-in state behind a data-source form: whether an ingest from `source` at `url` uses the
 * sign-in (signed in there, the library's sign-in active, "Use other credentials" not ticked),
 * and the config fields that make it do so. `onChange` runs when the user signs in or out.
 */
export class FormSignIn {
  useOther = false;
  private sub?: Subscription;

  constructor(private readonly auth: SourceAuthService, private readonly fgConfig: FlexibleGraphragConfigService,
              private readonly source: SourceKind) {}

  start(onChange: () => void): void {
    this.sub = this.auth.sessions$.subscribe(() => onChange());
    this.auth.validateSessions(true);  // a kept ticket / token may be dead by now
  }

  stop(): void { this.sub?.unsubscribe(); }

  using(url: string): boolean {
    return this.auth.active && !this.useOther && !this.fgConfig.hostCovers(this.source, url)
      && this.auth.sessions.some((s) => s.source === this.source && sameServer(this.source, s.url, url));
  }

  credential(url: string): Record<string, string> | null {
    return this.using(url) ? ingestCredential(this.source, url) : null;
  }
}

/**
 * Which sources a search / AI chat question covers (like Angel's content-lake UI): "All sources"
 * plus one chip per source with documents in the stores. Several can be picked. A repository
 * (Alfresco, Nuxeo, CMIS) needs a sign-in to that server first: its chip is greyed and clicking it
 * opens the sign-in. Shared by Search and AI Chat; sent as the question's `sources`
 * (FlexibleGraphragConfigService.questionBody). Hidden with fewer than two sources. In KG Spaces
 * ACA's own Alfresco is covered by ACA's ticket; other repositories stay greyed (no search sign-in
 * there yet).
 */
@Component({
  selector: 'app-source-picker',
  template: `
    <div class="source-picker" *ngIf="fgConfig.sourcePicker && sources.length > 1">
      <span class="label">Sources:</span>
      <button type="button" class="pick" [class.on]="!picked.size" (click)="pickAll()">All sources</button>
      <button type="button" *ngFor="let s of sources" class="pick" [class.on]="picked.has(key(s))"
              [class.locked]="locked(s)"
              [style.border-color]="colors[s.source] || null"
              [style.background]="picked.has(key(s)) ? (colors[s.source] || null) : null"
              [title]="tooltip(s)"
              (click)="onPick(s)">{{ chipLabel(s) }}</button>
    </div>
  `,
  styles: [`
    .source-picker { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
    .label { font-size: 14px; opacity: 0.7; margin-right: 4px; }
    .pick {
      border: 1px solid rgba(127, 127, 127, 0.6); border-radius: 16px; padding: 3px 12px; font-size: 13px;
      background: transparent; color: inherit; cursor: pointer;
    }
    .pick.on { background: #1976d2; border-color: #1976d2; color: #fff; }
    .pick.locked { opacity: 0.5; }
  `],
  standalone: false
})
export class SourcePickerComponent implements OnInit, OnDestroy {
  readonly auth = inject(SourceAuthService);
  readonly fgConfig = inject(FlexibleGraphragConfigService);
  readonly colors = SOURCE_COLORS;
  readonly key = sourceKey;
  sources: AvailableSource[] = [];
  picked = new Set<string>();
  private req: AuthRequirements = { required: false, providers: [] };
  private subs: Subscription[] = [];

  ngOnInit(): void {
    this.subs.push(this.auth.picked$.subscribe((list) => { this.picked = new Set(list.map(sourceKey)); }));
    this.subs.push(this.auth.sessions$.subscribe(() => this.refresh()));
    // a run added or removed documents: a new source's pill shows without leaving the page
    this.subs.push(this.auth.storesChanged$.subscribe(() => this.refresh(true)));
    this.refresh(true);
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  private async refresh(force = false): Promise<void> {
    const [list, req] = await Promise.all([this.auth.availableSources(force), this.auth.requirements(force)]);
    this.sources = list;
    this.req = req;
    // drop picks that are gone from the stores or now need a sign-in (e.g. after signing out)
    const usable = new Set(list.filter((s) => !this.locked(s)).map(sourceKey));
    const current = this.auth.picked$.value;
    const kept = current.filter((p) => usable.has(sourceKey(p)));
    if (kept.length !== current.length) this.auth.setPicked(kept);
  }

  locked(s: AvailableSource): boolean { return this.auth.sourceNeedsSignIn(s, this.req); }

  tooltip(s: AvailableSource): string {
    if (this.locked(s)) {
      const label = labelOf(signInFor(s).source);
      return this.fgConfig.searchSignIn
        ? `Sign in to ${label} first`
        : `Needs a ${label} sign-in, not available here yet`;
    }
    return `${s.label} only (${s.documents} document${s.documents === 1 ? '' : 's'})${s.url ? ' — ' + s.url : ''}`;
  }

  chipLabel(s: AvailableSource): string {
    const several = this.sources.filter((x) => x.source === s.source).length > 1;
    return several && s.url ? `${s.label} (${s.url.replace(/^https?:\/\//, '')})` : s.label;
  }

  pickAll(): void { this.auth.setPicked([]); }

  onPick(s: AvailableSource): void {
    if (this.locked(s)) {
      if (!this.fgConfig.searchSignIn) return;  // KG Spaces: no search sign-in (yet)
      this.auth.promptSignIn({ ...signInFor(s), methods: ['basic'], documents: s.documents });
      return;
    }
    const k = sourceKey(s);
    const current = this.auth.picked$.value;
    this.auth.setPicked(current.some((p) => sourceKey(p) === k)
      ? current.filter((p) => sourceKey(p) !== k)
      : [...current, s.url ? { source: s.source, url: s.url } : { source: s.source }]);
  }
}
