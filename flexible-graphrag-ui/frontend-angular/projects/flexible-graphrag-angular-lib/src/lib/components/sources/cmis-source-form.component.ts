import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, inject } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';
import { SourceAuthService } from '../../services/source-auth.service';
import { FormSignIn } from '../source-sign-in/source-sign-in';
import { SourceBrowserService } from '../../browser/remote-browse.provider';

export interface CMISSourceConfig {
  url: string;
  username?: string;
  password?: string;
  folder_path: string;
  // from the CMIS sign-in: an Alfresco server's ticket or a Nuxeo server's token
  auth_method?: string;
  ticket?: string;
  token?: string;
}

@Component({
  selector: 'app-cmis-source-form',
  template: `
    <app-base-source-form 
      title="CMIS Repository" 
      description="Connect to a CMIS-compliant content management system">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>CMIS Repository URL</mat-label>
        <input matInput
               [(ngModel)]="url"
               (ngModelChange)="onUrlChange()"
               [placeholder]="placeholder"
               required />
      </mat-form-field>

      <!-- The CMIS sign-in: an Alfresco / Nuxeo CMIS server's ticket / token instead of a password -->
      <app-source-sign-in-section source="cmis" [url]="url"
          [useOther]="signin.useOther" (useOtherChange)="signin.useOther = $event; updateValidationAndConfig()">
      </app-source-sign-in-section>

      <div class="form-row" *ngIf="!usingSignIn">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Username</mat-label>
          <input matInput
                 [(ngModel)]="username"
                 (ngModelChange)="onUsernameChange()"
                 required autocomplete="off" />
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Password</mat-label>
          <input matInput
                 type="password"
                 [(ngModel)]="password"
                 (ngModelChange)="onPasswordChange()"
                 required autocomplete="new-password" />
        </mat-form-field>
      </div>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Folder Path</mat-label>
          <input matInput
                 [(ngModel)]="folderPath"
                 (ngModelChange)="onFolderPathChange()"
                 placeholder="e.g., /Sites/example/documentLibrary"
                 required />
          <mat-hint>A folder (all its subfolders are read), or one document's path</mat-hint>
        </mat-form-field>
        <button mat-stroked-button type="button" class="browse-button" [disabled]="!canBrowse()"
                [title]="canBrowse() ? 'Pick a folder or a document in the repository' : 'Fill in the URL and sign in (or a username and password) first'"
                (click)="browse()">
          <mat-icon>folder_open</mat-icon> Browse…
        </button>
      </div>
    </app-base-source-form>
  `,
  styles: [`
    .full-width {
      width: 100%;
      margin-bottom: 16px;
    }
    
    .form-row {
      display: flex;
      gap: 16px;
      margin-bottom: 16px;
    }
    
    .half-width {
      flex: 1;
    }

    .browse-button {
      height: 56px;
      white-space: nowrap;
      flex: none;
    }
  `],
  standalone: false
})
export class CMISSourceFormComponent implements OnInit, OnDestroy {
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private readonly auth = inject(SourceAuthService);
  readonly signin = new FormSignIn(this.auth, this.fgConfig, 'cmis');
  get usingSignIn(): boolean { return this.signin.using(this.url); }
  @Input() url: string = '';
  // no pre-filled credentials (were admin/admin)
  @Input() username: string = '';
  @Input() password: string = '';
  @Input() folderPath: string = '/Shared/GraphRAG';
  
  @Output() urlChange = new EventEmitter<string>();
  @Output() usernameChange = new EventEmitter<string>();
  @Output() passwordChange = new EventEmitter<string>();
  @Output() folderPathChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<CMISSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  get placeholder(): string {
    const baseUrl = this.fgConfig.cmisBaseUrl;
    return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  }

  ngOnInit() {
    this.updateValidationAndConfig();
    this.signin.start(() => this.updateValidationAndConfig());  // re-emit when the user signs in / out
  }

  ngOnDestroy() {
    this.signin.stop();
  }

  private readonly browser = inject(SourceBrowserService);
  private readonly provider = this.browser.provider('cmis', 'CMIS repository', () => this.config());

  private config(): CMISSourceConfig {
    const signedIn = this.signin.credential(this.url);
    return signedIn
      ? { url: this.url, folder_path: this.folderPath, ...signedIn }
      : { url: this.url, username: this.username, password: this.password, folder_path: this.folderPath };
  }

  /** Browse needs the URL and a sign-in (or a username and password), not yet a folder path. */
  canBrowse(): boolean {
    return this.url.trim() !== '' &&
      (!!this.signin.credential(this.url) || (this.username.trim() !== '' && this.password.trim() !== ''));
  }

  /** One folder, or one document: folder_path takes either. */
  async browse(): Promise<void> {
    const [item] = await this.browser.pick({
      provider: this.provider, title: 'Pick a folder or a document: CMIS', multiple: false,
    });
    if (!item) return;
    this.folderPath = item.path || `/${item.name}`;
    this.onFolderPathChange();
  }

  updateValidationAndConfig() {
    const isValid = this.canBrowse() && this.folderPath.trim() !== '';
    this.validationChange.emit(isValid);
    this.configurationChange.emit(this.config());
  }

  onUrlChange(): void {
    this.urlChange.emit(this.url);
    this.updateValidationAndConfig();
  }

  onUsernameChange(): void {
    this.usernameChange.emit(this.username);
    this.updateValidationAndConfig();
  }

  onPasswordChange(): void {
    this.passwordChange.emit(this.password);
    this.updateValidationAndConfig();
  }

  onFolderPathChange(): void {
    this.folderPathChange.emit(this.folderPath);
    this.updateValidationAndConfig();
  }
}
