import { Component, Input, Output, EventEmitter, OnDestroy, OnInit, inject } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';
import { SourceAuthService } from '../../services/source-auth.service';
import { FormSignIn } from '../source-sign-in/source-sign-in';
import { UiDefaultsService } from '../../services/ui-defaults.service';

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
          <input matInput [(ngModel)]="path" (ngModelChange)="update()"
                 placeholder="e.g., /Shared/GraphRAG" required />
        </mat-form-field>
        <mat-checkbox class="deep" [checked]="recursive" (change)="ownDeep = $event.checked; update()"
                    title="Include subfolders, at every depth, in the ingest and its auto sync">Deep</mat-checkbox>
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
  `],
  standalone: false
})
export class AlfrescoSourceFormComponent implements OnInit, OnDestroy {
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
    if (this.url.trim() === '' || this.path.trim() === '') return false;
    if (this.credentialsHidden) return true;
    if (this.authMethod === 'oauth2') {
      return this.clientId.trim() !== '' && (this.accessToken.trim() !== '' || this.clientSecret.trim() !== '');
    }
    if (this.authMethod === 'ticket' && this.showTicketField && this.ticket.trim() !== '') return true;
    return this.username.trim() !== '' && this.password.trim() !== '';
  }

  private buildConfig(): AlfrescoSourceConfig {
    if (this.usingHostSignIn) {
      // the host adds its signed-in user's ticket (KG Spaces: withAcaTicket)
      return { url: this.url, path: this.path, recursive: this.recursive, auth_method: 'ticket' };
    }
    const signedIn = this.signin.credential(this.url);
    if (signedIn) {
      return { url: this.url, path: this.path, recursive: this.recursive, ...signedIn } as AlfrescoSourceConfig;
    }
    const config: AlfrescoSourceConfig = { url: this.url, auth_method: this.authMethod, path: this.path,
                                           recursive: this.recursive };
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
