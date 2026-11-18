import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { IngestSignalService } from '../../services/ingest-signal.service';
import { Component, Input, Output, EventEmitter, OnDestroy, OnInit, inject } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';
import { SourceAuthService } from '../../services/source-auth.service';
import { FormSignIn } from '../source-sign-in/source-sign-in';
import { UiDefaultsService } from '../../services/ui-defaults.service';
import { SourceBrowserService } from '../../browser/remote-browse.provider';
import { BrowsedNodeDetail, commonParentPath, toNodeDetails } from '../../browser/browse.models';

export interface AlfrescoOAuth2Config {
  client_id?: string;
  client_secret?: string;
  token_endpoint?: string;
  scope?: string;
  access_token?: string;
  refresh_token?: string;
}

export interface AlfrescoSourceConfig {
  url: string;
  auth_method: string;
  username?: string;
  password?: string;
  ticket?: string;
  oauth2?: AlfrescoOAuth2Config;
  path?: string;
  /** Documents / folders picked in the browser (as ACA's multi-select sends them): the ingest
   *  reads these instead of the path, which is then their common parent folder. */
  nodeDetails?: BrowsedNodeDetail[];
  recursive?: boolean;  // Deep: include subfolders, in the ingest and its auto sync
}

@Component({
  selector: 'app-alfresco-source-form',
  template: `
    <app-base-source-form
      title="Alfresco Repository"
      description="Connect to an Alfresco content management system">

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Alfresco Base URL</mat-label>
        <input matInput [(ngModel)]="url" (ngModelChange)="update()"
               [placeholder]="'e.g., ' + defaultUrl" required />
      </mat-form-field>

      <!-- The library's sign-in (not for KG Spaces' own server, which uses ACA's ticket) -->
      <app-source-sign-in-section source="alfresco" [url]="url"
          [useOther]="signin.useOther" (useOtherChange)="signin.useOther = $event; update()">
      </app-source-sign-in-section>

      <!-- In a host that signs the user in itself (KG Spaces in ACA), an ingest to that host's own
           Alfresco server uses the host's sign-in: the credential fields would be ignored -->
      <div class="sign-in-row" *ngIf="usingHostSignIn">
        <span>This ingest uses your Alfresco Content App sign-in &mdash; no username or password needed.</span>
      </div>
      <div class="sign-in-row" *ngIf="fgConfig.hostSuppliesAlfrescoTicket && !usingHostSignIn && !auth.active">
        <span class="hint">A different Alfresco server than the one you are signed in to: enter its credentials.</span>
      </div>

      <mat-form-field appearance="outline" class="full-width" *ngIf="!credentialsHidden">
        <mat-label>Authentication</mat-label>
        <mat-select [(ngModel)]="authMethod" (ngModelChange)="update()">
          <mat-option value="basic">Basic (username / password)</mat-option>
          <mat-option value="ticket">Ticket (login ticket)</mat-option>
          <mat-option value="oauth2">OAuth2 (Bearer, via Identity Service)</mat-option>
        </mat-select>
      </mat-form-field>

      <!-- Developer testing affordance, not an end-user feature: pasting a login ticket by
           hand is not a real workflow. The real consumer is an ACA/ADF extension posting the
           ticket it already holds, which needs no field at all. Set showTicketField = false
           to hide it; ticket mode then behaves as before (ticket acquired from user/pw). -->
      <mat-form-field appearance="outline" class="full-width" *ngIf="authMethod === 'ticket' && showTicketField">
        <mat-label>Login ticket</mat-label>
        <input matInput type="password" [(ngModel)]="ticket" (ngModelChange)="update()"
               placeholder="e.g., TICKET_xxxxxxxx" autocomplete="new-password" />
        <mat-hint>Leave empty to fetch a ticket from the username and password below</mat-hint>
      </mat-form-field>

      <div class="form-row" *ngIf="!credentialsHidden && (authMethod === 'basic' || (authMethod === 'ticket' && !(showTicketField && ticket.trim())))">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Username</mat-label>
          <!-- repository credentials, not a login to this page: no password-manager autofill -->
          <input matInput [(ngModel)]="username" (ngModelChange)="update()" required autocomplete="off" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Password</mat-label>
          <input matInput type="password" [(ngModel)]="password" (ngModelChange)="update()" required autocomplete="new-password" />
        </mat-form-field>
      </div>

      <ng-container *ngIf="!credentialsHidden && authMethod === 'oauth2'">
        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Client ID</mat-label>
            <input matInput [(ngModel)]="clientId" (ngModelChange)="update()" required autocomplete="off" />
          </mat-form-field>
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Client Secret</mat-label>
            <input matInput type="password" [(ngModel)]="clientSecret" (ngModelChange)="update()" autocomplete="new-password"
                   [required]="!accessToken.trim()" />
            <mat-hint>Required unless an access token is given</mat-hint>
          </mat-form-field>
        </div>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Token Endpoint (optional)</mat-label>
          <input matInput [(ngModel)]="tokenEndpoint" (ngModelChange)="update()"
                 placeholder="e.g., https://<keycloak>/realms/alfresco/protocol/openid-connect/token" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Scope (optional)</mat-label>
          <input matInput [(ngModel)]="scope" (ngModelChange)="update()" />
        </mat-form-field>
        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Access Token (optional)</mat-label>
            <input matInput type="password" [(ngModel)]="accessToken" (ngModelChange)="update()" autocomplete="new-password" />
            <mat-hint>Provide a pre-obtained token instead of client_credentials</mat-hint>
          </mat-form-field>
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Refresh Token (optional)</mat-label>
            <input matInput type="password" [(ngModel)]="refreshToken" (ngModelChange)="update()" autocomplete="new-password" />
          </mat-form-field>
        </div>
      </ng-container>

      <div class="path-row">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Path</mat-label>
          <input matInput [(ngModel)]="path" (ngModelChange)="onPathTyped()"
                 [disabled]="nodes.length > 0"
                 placeholder="e.g., /Shared/GraphRAG" required />
          <mat-hint *ngIf="nodes.length">The folder holding the picked items</mat-hint>
        </mat-form-field>
        <button mat-stroked-button type="button" class="browse-button" [disabled]="!canBrowse()"
                [title]="canBrowse() ? 'Pick folders and documents in the repository' : 'Fill in the URL and sign in (or credentials) first'"
                (click)="browse()">
          <mat-icon>folder_open</mat-icon> Browse…
        </button>
        <mat-checkbox class="deep" [checked]="recursive" (change)="ownDeep = $event.checked; update()"
                    title="Include subfolders, at every depth, in the ingest and its auto sync">Deep</mat-checkbox>
      </div>
      <div class="picked" *ngIf="nodes.length">
        <div class="picked-caption">
          {{ nodes.length === 1 ? '1 item picked' : nodes.length + ' items picked' }}: the ingest reads these instead of the path
        </div>
        <mat-chip-set>
          <mat-chip *ngFor="let n of nodes" (removed)="removeNode(n)" [title]="n.path">
            <mat-icon matChipAvatar>{{ n.isFolder ? 'folder' : 'description' }}</mat-icon>
            {{ n.path }}
            <button matChipRemove type="button" [attr.aria-label]="'Remove ' + n.name"><mat-icon>cancel</mat-icon></button>
          </mat-chip>
        </mat-chip-set>
        <button mat-button type="button" (click)="clearNodes()">Clear</button>
      </div>
    </app-base-source-form>
  `,
  styles: [`
    .full-width { width: 100%; margin-bottom: 16px; }
    .form-row { display: flex; gap: 16px; margin-bottom: 16px; }
    .half-width { flex: 1; }
    .sign-in-row { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
    .sign-in-row .hint { opacity: 0.7; }
    .path-row { display: flex; align-items: flex-start; gap: 8px; }
    .path-row .full-width { flex: 1; }
    .path-row .deep { margin-top: 12px; white-space: nowrap; }
    .browse-button { height: 56px; white-space: nowrap; flex: none; }
    .picked { margin-bottom: 16px; }
    .picked-caption { font-size: 12px; opacity: 0.8; margin-bottom: 4px; }
  `],
  standalone: false
})
export class AlfrescoSourceFormComponent implements OnInit, OnDestroy {
  // an ingest started: the picks empty (the run's rows stay in Processing)
  private readonly ingestStarted = inject(IngestSignalService).started
    .pipe(takeUntilDestroyed()).subscribe(() => this.clearNodes());
  readonly fgConfig = inject(FlexibleGraphragConfigService);
  readonly auth = inject(SourceAuthService);

  // The Alfresco sign-in (planning/SOURCE-AUTH-LOGIN.md). When signed in to this server, the
  // ingest uses that session's ticket -- nobody types a ticket. "Use other credentials" falls
  // back to the fields (e.g. a service account for Auto Sync, which needs durable credentials).
  readonly signin = new FormSignIn(this.auth, this.fgConfig, 'alfresco');

  get usingSignIn(): boolean { return this.signin.using(this.url); }
  /** Host-signed-in (KG Spaces): an ingest to the host's own Alfresco server uses its ticket. */
  get usingHostSignIn(): boolean { return this.fgConfig.hostCovers('alfresco', this.url); }
  get credentialsHidden(): boolean { return this.usingSignIn || this.usingHostSignIn; }
  defaultUrl = this.fgConfig.alfrescoBaseUrl;

  url: string = this.defaultUrl;
  authMethod: string = 'basic';
  path: string = '/Shared/GraphRAG';
  // Deep: include subfolders (recursive). Unset: the backend's DEFAULT_RECURSIVE, else off
  private readonly uiDefaults = inject(UiDefaultsService);
  ownDeep: boolean | undefined = undefined;
  get recursive(): boolean { return this.ownDeep ?? this.uiDefaults.defaults.recursive ?? false; }

  // No pre-filled credentials (they were admin/admin): sign in, or type a username/password
  username: string = '';
  password: string = '';
  // A ticket obtained elsewhere (e.g. one an ADF front end already holds). When set it
  // replaces username/password entirely rather than being fetched from them.
  ticket: string = '';
  // Hidden developer testing affordance. Flip to true to expose the hand-entry ticket field
  // (see the template comment) when exercising the pass-through path from this UI. Off by
  // default: pasting a ticket by hand is not an end-user workflow, and the real consumer --
  // an ACA/ADF extension posting the ticket it already holds -- needs no field at all.
  showTicketField = false;

  clientId: string = '';
  clientSecret: string = '';
  tokenEndpoint: string = '';
  scope: string = '';
  accessToken: string = '';
  refreshToken: string = '';

  @Input() value: any = null;
  @Output() valueChange = new EventEmitter<any>();
  @Output() configurationChange = new EventEmitter<AlfrescoSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  ngOnInit() {
    const v = this.value || {};
    if (v.url !== undefined) this.url = v.url;
    if (v.auth_method) this.authMethod = v.auth_method;
    if (v.path !== undefined) this.path = v.path;
    if (Array.isArray(v.nodeDetails)) this.nodes = v.nodeDetails;
    if (typeof v.recursive === 'boolean') this.ownDeep = v.recursive;
    if (v.username !== undefined) this.username = v.username;
    if (v.password !== undefined) this.password = v.password;
    if (v.ticket !== undefined) this.ticket = v.ticket;
    const o = v.oauth2 || {};
    if (o.client_id !== undefined) this.clientId = o.client_id;
    if (o.client_secret !== undefined) this.clientSecret = o.client_secret;
    if (o.token_endpoint !== undefined) this.tokenEndpoint = o.token_endpoint;
    if (o.scope !== undefined) this.scope = o.scope;
    if (o.access_token !== undefined) this.accessToken = o.access_token;
    if (o.refresh_token !== undefined) this.refreshToken = o.refresh_token;
    // re-emit when the user signs in / out, so the ingest config follows
    this.signin.start(() => this.update());
    this.uiDefaults.load().then(() => this.update());  // the Deep default may have changed
  }

  ngOnDestroy(): void {
    this.signin.stop();
  }

  private isValid(): boolean {
    return this.path.trim() !== '' && this.canBrowse();
  }

  /** The URL and a way to sign in (what browsing needs; an ingest needs a path too). */
  canBrowse(): boolean {
    if (this.url.trim() === '') return false;
    if (this.credentialsHidden) return true;
    if (this.authMethod === 'oauth2') {
      return this.clientId.trim() !== '' && (this.accessToken.trim() !== '' || this.clientSecret.trim() !== '');
    }
    if (this.authMethod === 'ticket' && this.showTicketField && this.ticket.trim() !== '') return true;
    return this.username.trim() !== '' && this.password.trim() !== '';
  }

  // Documents / folders picked in the browser (nodeDetails)
  nodes: BrowsedNodeDetail[] = [];
  private readonly browser = inject(SourceBrowserService);
  private readonly provider = this.browser.provider('alfresco', 'Alfresco repository', () => this.browseConfig());

  /** The ingest config, plus the host's own ticket when the host signs the user in (KG Spaces):
   *  the host adds it to an ingest itself, but a browse goes straight to /api/browse. */
  private browseConfig(): AlfrescoSourceConfig {
    const config = this.buildConfig();
    if (this.usingHostSignIn && !config.ticket) {
      const ticket = this.fgConfig.questionHeaders()['X-Alfresco-Ticket'];
      if (ticket) return { ...config, auth_method: 'ticket', ticket };
    }
    return config;
  }

  /** One folder: the path. Documents, or several items: nodeDetails by id, with the path their
   *  common parent folder (as ACA's multi-select sends it). */
  async browse(): Promise<void> {
    const items = await this.browser.pick({ provider: this.provider, title: 'Pick folders and documents: Alfresco' });
    if (!items.length) return;
    if (items.length === 1 && items[0].isDirectory) {
      this.path = items[0].path || `/${items[0].name}`;
      this.nodes = [];
    } else {
      this.nodes = toNodeDetails(items);
      this.path = commonParentPath(this.nodes.map((n) => n.path));
    }
    this.update();
  }

  removeNode(node: BrowsedNodeDetail): void {
    this.nodes = this.nodes.filter((n) => n !== node);
    if (this.nodes.length) this.path = commonParentPath(this.nodes.map((n) => n.path));
    this.update();
  }

  clearNodes(): void {
    this.nodes = [];
    this.update();
  }

  /** A typed path replaces picked items. */
  onPathTyped(): void {
    this.nodes = [];
    this.update();
  }

  private buildConfig(): AlfrescoSourceConfig {
    const nodeDetails = this.nodes.length ? { nodeDetails: this.nodes } : {};
    if (this.usingHostSignIn) {
      // the host adds its signed-in user's ticket (KG Spaces: withAcaTicket)
      return { url: this.url, path: this.path, ...nodeDetails, recursive: this.recursive, auth_method: 'ticket' };
    }
    const signedIn = this.signin.credential(this.url);
    if (signedIn) {
      return { url: this.url, path: this.path, ...nodeDetails, recursive: this.recursive, ...signedIn } as AlfrescoSourceConfig;
    }
    const config: AlfrescoSourceConfig = { url: this.url, auth_method: this.authMethod, path: this.path,
                                           ...nodeDetails, recursive: this.recursive };
    if (this.authMethod === 'oauth2') {
      config.oauth2 = {
        client_id: this.clientId,
        client_secret: this.clientSecret || undefined,
        token_endpoint: this.tokenEndpoint || undefined,
        scope: this.scope || undefined,
        access_token: this.accessToken || undefined,
        refresh_token: this.refreshToken || undefined,
      };
    } else if (this.authMethod === 'ticket' && this.showTicketField && this.ticket.trim() !== '') {
      config.ticket = this.ticket.trim();
    } else {
      config.username = this.username;
      config.password = this.password;
    }
    return config;
  }

  update(): void {
    this.validationChange.emit(this.isValid());
    // Two different things: the backend payload keeps ticket and username/password mutually
    // exclusive, while the restore snapshot must carry every field. Emitting the payload as
    // the snapshot loses whichever keys it omitted, and ngOnInit then falls back to the class
    // defaults -- so clearing the credentials and setting a ticket resurrected admin/admin.
    this.configurationChange.emit(this.buildConfig());
    this.valueChange.emit(this.snapshot());
  }

  /** Full form state, for [(value)] round-tripping. Never sent to the backend. */
  private snapshot(): any {
    return {
      url: this.url,
      auth_method: this.authMethod,
      path: this.path,
      nodeDetails: this.nodes.length ? this.nodes : undefined,
      recursive: this.ownDeep,
      username: this.username,
      password: this.password,
      ticket: this.ticket,
      oauth2: {
        client_id: this.clientId,
        client_secret: this.clientSecret,
        token_endpoint: this.tokenEndpoint,
        scope: this.scope,
        access_token: this.accessToken,
        refresh_token: this.refreshToken,
      },
    };
  }
}
