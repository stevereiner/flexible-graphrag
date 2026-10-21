import { Component, Input, Output, EventEmitter, OnDestroy, OnInit, inject } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';
import { SourceAuthService } from '../../services/source-auth.service';
import { UiDefaultsService } from '../../services/ui-defaults.service';
import { FormSignIn } from '../source-sign-in/source-sign-in';

export interface NuxeoOAuth2Config {
  client_id?: string;
  client_secret?: string;
  access_token?: string;
  refresh_token?: string;
  token_endpoint?: string;
}

export interface NuxeoSourceConfig {
  url: string;
  auth_method: string;
  username?: string;
  password?: string;
  token?: string;
  oauth2?: NuxeoOAuth2Config;
  path?: string;
  recursive?: boolean;  // Deep: include subfolders, in the ingest and its auto sync
}

@Component({
  selector: 'app-nuxeo-source-form',
  template: `
    <app-base-source-form
      title="Nuxeo Repository"
      description="Connect to a Nuxeo content management system">

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Nuxeo Base URL</mat-label>
        <input matInput
               [(ngModel)]="url"
               (ngModelChange)="update()"
               placeholder="e.g., http://localhost:8081/nuxeo"
               required />
        <mat-hint>Base repository URL (no /api/v1 suffix)</mat-hint>
      </mat-form-field>

      <!-- The Nuxeo sign-in: when signed in to this server the ingest uses that session's token -->
      <app-source-sign-in-section source="nuxeo" [url]="url"
          [useOther]="signin.useOther" (useOtherChange)="signin.useOther = $event; update()">
      </app-source-sign-in-section>

      <mat-form-field appearance="outline" class="full-width" *ngIf="!usingSignIn">
        <mat-label>Authentication</mat-label>
        <mat-select [(ngModel)]="authMethod" (ngModelChange)="update()">
          <mat-option value="basic">Basic (username / password)</mat-option>
          <mat-option value="oauth2">OAuth2 (Bearer)</mat-option>
          <mat-option value="token">Token (X-Authentication-Token)</mat-option>
        </mat-select>
      </mat-form-field>

      <div class="form-row" *ngIf="!usingSignIn && (authMethod === 'basic' || authMethod === 'token')">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Username</mat-label>
          <input matInput [(ngModel)]="username" (ngModelChange)="update()" required autocomplete="off" />
        </mat-form-field>
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Password</mat-label>
          <input matInput type="password" [(ngModel)]="password" (ngModelChange)="update()" required autocomplete="new-password" />
        </mat-form-field>
      </div>

      <ng-container *ngIf="!usingSignIn && authMethod === 'oauth2'">
        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Client ID</mat-label>
            <input matInput [(ngModel)]="clientId" (ngModelChange)="update()" required />
          </mat-form-field>
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Client Secret</mat-label>
            <input matInput type="password" [(ngModel)]="clientSecret" (ngModelChange)="update()" autocomplete="new-password"
                   [required]="!accessToken.trim()" />
            <mat-hint>Required unless an access token is given</mat-hint>
          </mat-form-field>
        </div>
        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Access Token (optional)</mat-label>
            <input matInput type="password" [(ngModel)]="accessToken" (ngModelChange)="update()" autocomplete="new-password" />
            <mat-hint>Obtain out-of-band (authorization code + PKCE)</mat-hint>
          </mat-form-field>
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Refresh Token (optional)</mat-label>
            <input matInput type="password" [(ngModel)]="refreshToken" (ngModelChange)="update()" autocomplete="new-password" />
          </mat-form-field>
        </div>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Token Endpoint (optional)</mat-label>
          <input matInput [(ngModel)]="tokenEndpoint" (ngModelChange)="update()"
                 placeholder="defaults to <url>/oauth2/token" />
        </mat-form-field>
      </ng-container>

      <div class="path-row">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Path</mat-label>
          <input matInput [(ngModel)]="path" (ngModelChange)="update()"
                 placeholder="e.g., /default-domain/workspaces/GraphRAG" required />
          <mat-hint>Path to the folder or document to process</mat-hint>
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
    .path-row { display: flex; align-items: flex-start; gap: 8px; }
    .path-row .full-width { flex: 1; }
    .path-row .deep { margin-top: 12px; white-space: nowrap; }
  `],
  standalone: false
})
export class NuxeoSourceFormComponent implements OnInit, OnDestroy {
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private readonly auth = inject(SourceAuthService);
  readonly signin = new FormSignIn(this.auth, this.fgConfig, 'nuxeo');
  get usingSignIn(): boolean { return this.signin.using(this.url); }
  url: string = this.fgConfig.nuxeoBaseUrl;
  authMethod: string = 'basic';
  // Set NUXEO_PATH at build time (generate-env-config.ts) to point the dialog at
  // your own workspace.  The backend's .env NUXEO_PATH cannot reach the browser.
  path: string = this.fgConfig.nuxeoPath;
  // Deep: include subfolders (recursive). Unset: the backend's DEFAULT_RECURSIVE, else off
  private readonly uiDefaults = inject(UiDefaultsService);
  ownDeep: boolean | undefined = undefined;
  get recursive(): boolean { return this.ownDeep ?? this.uiDefaults.defaults.recursive ?? false; }

  // no pre-filled credentials (were Administrator/Administrator)
  username: string = '';
  password: string = '';
  token: string = '';

  clientId: string = '';
  clientSecret: string = '';
  accessToken: string = '';
  refreshToken: string = '';
  tokenEndpoint: string = '';

  // Single-object persistence: [(value)] seeds the form on mount and receives the config on
  // every edit, so the parent holds one object and state survives tab switches.
  @Input() value: any = null;
  @Output() valueChange = new EventEmitter<any>();
  @Output() configurationChange = new EventEmitter<NuxeoSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  ngOnInit() {
    const v = this.value || {};
    if (v.url !== undefined) this.url = v.url;
    if (v.auth_method) this.authMethod = v.auth_method;
    if (v.path !== undefined) this.path = v.path;
    if (typeof v.recursive === 'boolean') this.ownDeep = v.recursive;
    if (v.username !== undefined) this.username = v.username;
    if (v.password !== undefined) this.password = v.password;
    if (v.token !== undefined) this.token = v.token;
    const o = v.oauth2 || {};
    if (o.client_id !== undefined) this.clientId = o.client_id;
    if (o.client_secret !== undefined) this.clientSecret = o.client_secret;
    if (o.access_token !== undefined) this.accessToken = o.access_token;
    if (o.refresh_token !== undefined) this.refreshToken = o.refresh_token;
    if (o.token_endpoint !== undefined) this.tokenEndpoint = o.token_endpoint;
    this.update();
    this.signin.start(() => this.update());  // re-emit when the user signs in / out
    this.uiDefaults.load().then(() => this.update());  // the Deep default may have changed
  }

  ngOnDestroy(): void {
    this.signin.stop();
  }

  private isValid(): boolean {
    if (this.url.trim() === '') return false;
    if (this.usingSignIn) return true;
    // basic and token both use username/password (token mode fetches the auth token
    // from them on the backend, like Alfresco ticket).
    if (this.authMethod === 'basic' || this.authMethod === 'token') {
      return this.username.trim() !== '' && this.password.trim() !== '';
    }
    return this.clientId.trim() !== '' && (this.accessToken.trim() !== '' || this.clientSecret.trim() !== '');
  }

  private buildConfig(): NuxeoSourceConfig {
    const signedIn = this.signin.credential(this.url);
    if (signedIn) return { url: this.url, path: this.path, recursive: this.recursive, ...signedIn } as NuxeoSourceConfig;
    const config: NuxeoSourceConfig = { url: this.url, auth_method: this.authMethod, path: this.path,
                                        recursive: this.recursive };
    // token mode sends username/password; the backend fetches the auth token from them.
    if (this.authMethod === 'basic' || this.authMethod === 'token') {
      config.username = this.username;
      config.password = this.password;
    } else {
      config.oauth2 = {
        client_id: this.clientId,
        client_secret: this.clientSecret || undefined,
        access_token: this.accessToken || undefined,
        refresh_token: this.refreshToken || undefined,
        token_endpoint: this.tokenEndpoint || undefined,
      };
    }
    return config;
  }

  update(): void {
    const config = this.buildConfig();
    this.validationChange.emit(this.isValid());
    this.configurationChange.emit(config);
    // persist live config to the parent (with the user's own Deep choice only, not the default)
    this.valueChange.emit({ ...config, recursive: this.ownDeep });
  }
}
