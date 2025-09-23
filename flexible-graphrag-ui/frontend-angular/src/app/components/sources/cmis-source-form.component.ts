import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';
import { environment } from '../../../environments/environment';

export interface CMISSourceConfig {
  url: string;
  username: string;
  password: string;
  folder_path: string;
}

@Component({
  selector: 'app-cmis-source-form',
  template: `
    <app-base-source-form 
      title="CMIS Repository" 
      description="Connect to a CMIS-compliant content management system">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>CMIS Repository URL *</mat-label>
        <input matInput
               [(ngModel)]="url"
               (ngModelChange)="onUrlChange()"
               [placeholder]="placeholder"
               required />
      </mat-form-field>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Username *</mat-label>
          <input matInput
                 [(ngModel)]="username"
                 (ngModelChange)="onUsernameChange()"
                 required />
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Password *</mat-label>
          <input matInput
                 type="password"
                 [(ngModel)]="password"
                 (ngModelChange)="onPasswordChange()"
                 required />
        </mat-form-field>
      </div>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Folder Path *</mat-label>
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
  @Input() url: string = '';
  @Input() username: string = 'admin';
  @Input() password: string = 'admin';
  @Input() folderPath: string = '/Shared/GraphRAG';
  
  @Output() urlChange = new EventEmitter<string>();
  @Output() usernameChange = new EventEmitter<string>();
  @Output() passwordChange = new EventEmitter<string>();
  @Output() folderPathChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<CMISSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  get placeholder(): string {
    const baseUrl = environment.cmisBaseUrl || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  }

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.url.trim() !== '' && 
                   this.username.trim() !== '' && 
                   this.password.trim() !== '' && 
                   this.folderPath.trim() !== '';
    
    const config: CMISSourceConfig = {
      url: this.url,
      username: this.username,
      password: this.password,
      folder_path: this.folderPath
    };
    
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
