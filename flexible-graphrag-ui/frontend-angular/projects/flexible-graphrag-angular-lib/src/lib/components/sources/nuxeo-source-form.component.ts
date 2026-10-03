import { Component, Input, Output, EventEmitter, OnInit, inject } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';

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
}

@Component({
  selector: 'app-nuxeo-source-form',
  template: `
    <app-base-source-form
      title="Nuxeo Repository"
      description="Connect to a Nuxeo content management system">

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Nuxeo Base URL *</mat-label>
        <input matInput
               [(ngModel)]="url"
               (ngModelChange)="update()"
               placeholder="e.g., http://localhost:8081/nuxeo"
               required />
        <mat-hint>Base repository URL (no /api/v1 suffix)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Authentication</mat-label>
        <mat-select [(ngModel)]="authMethod" (ngModelChange)="update()">
          <mat-option value="basic">Basic (username / password)</mat-option>
          <mat-option value="oauth2">OAuth2 (Bearer)</mat-option>
          <mat-option value="token">Token (X-Authentication-Token)</mat-option>
        </mat-select>
      </mat-form-field>

      <div class="form-row" *ngIf="authMethod === 'basic' || authMethod === 'token'">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Username *</mat-label>
          <input matInput [(ngModel)]="username" (ngModelChange)="update()" required />
        </mat-form-field>
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Password *</mat-label>
          <input matInput type="password" [(ngModel)]="password" (ngModelChange)="update()" required />
        </mat-form-field>
      </div>

      <ng-container *ngIf="authMethod === 'oauth2'">
        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Client ID *</mat-label>
            <input matInput [(ngModel)]="clientId" (ngModelChange)="update()" required />
          </mat-form-field>
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Client Secret</mat-label>
            <input matInput type="password" [(ngModel)]="clientSecret" (ngModelChange)="update()" />
          </mat-form-field>
        </div>
        <div class="form-row">
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Access Token</mat-label>
            <input matInput type="password" [(ngModel)]="accessToken" (ngModelChange)="update()" />
            <mat-hint>Obtain out-of-band (authorization code + PKCE)</mat-hint>
          </mat-form-field>
          <mat-form-field appearance="outline" class="half-width">
            <mat-label>Refresh Token</mat-label>
            <input matInput type="password" [(ngModel)]="refreshToken" (ngModelChange)="update()" />
          </mat-form-field>
        </div>
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Token Endpoint (optional)</mat-label>
          <input matInput [(ngModel)]="tokenEndpoint" (ngModelChange)="update()"
                 placeholder="defaults to <url>/oauth2/token" />
        </mat-form-field>
      </ng-container>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Path *</mat-label>
        <input matInput [(ngModel)]="path" (ngModelChange)="update()"
               placeholder="e.g., /default-domain/workspaces/GraphRAG" required />
        <mat-hint>Path to the folder or document to process</mat-hint>
      </mat-form-field>
    </app-base-source-form>
  `,
  styles: [`
    .full-width { width: 100%; margin-bottom: 16px; }
    .form-row { display: flex; gap: 16px; margin-bottom: 16px; }
    .half-width { flex: 1; }
  `],
  standalone: false
})
export class NuxeoSourceFormComponent implements OnInit {
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  url: string = this.fgConfig.nuxeoBaseUrl;
  authMethod: string = 'basic';
  // Set NUXEO_PATH at build time (generate-env-config.ts) to point the dialog at
  // your own workspace.  The backend's .env NUXEO_PATH cannot reach the browser.
  path: string = this.fgConfig.nuxeoPath;

  username: string = 'Administrator';
  password: string = 'Administrator';
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
  }

  private isValid(): boolean {
    if (this.url.trim() === '') return false;
    // basic and token both use username/password (token mode fetches the auth token
    // from them on the backend, like Alfresco ticket).
    if (this.authMethod === 'basic' || this.authMethod === 'token') {
      return this.username.trim() !== '' && this.password.trim() !== '';
    }
    return this.clientId.trim() !== '' && (this.accessToken.trim() !== '' || this.clientSecret.trim() !== '');
  }

  private buildConfig(): NuxeoSourceConfig {
    const config: NuxeoSourceConfig = { url: this.url, auth_method: this.authMethod, path: this.path };
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
    this.valueChange.emit(config);  // persist live config to the parent
  }
}
