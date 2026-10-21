import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, inject } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';
import { SourceAuthService } from '../../services/source-auth.service';
import { FormSignIn } from '../source-sign-in/source-sign-in';

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

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Folder Path</mat-label>
        <input matInput
               [(ngModel)]="folderPath"
               (ngModelChange)="onFolderPathChange()"
               placeholder="e.g., /Sites/example/documentLibrary"
               required />
        <mat-hint>Path to the folder containing documents to process</mat-hint>
      </mat-form-field>
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

  updateValidationAndConfig() {
    const signedIn = this.signin.credential(this.url);
    const isValid = this.url.trim() !== '' && this.folderPath.trim() !== '' &&
                   (!!signedIn || (this.username.trim() !== '' && this.password.trim() !== ''));

    const config: CMISSourceConfig = signedIn
      ? { url: this.url, folder_path: this.folderPath, ...signedIn }
      : { url: this.url, username: this.username, password: this.password, folder_path: this.folderPath };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
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
