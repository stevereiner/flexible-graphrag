import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';
import { environment } from '../../../environments/environment';

export interface AlfrescoSourceConfig {
  url: string;
  username: string;
  password: string;
  path: string;
}

@Component({
  selector: 'app-alfresco-source-form',
  template: `
    <app-base-source-form 
      title="Alfresco Repository" 
      description="Connect to an Alfresco content management system">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Alfresco Base URL *</mat-label>
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
        <mat-label>Path *</mat-label>
        <input matInput
               [(ngModel)]="path"
               (ngModelChange)="onPathChange()"
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
export class AlfrescoSourceFormComponent implements OnInit, OnDestroy {
  @Input() url: string = '';
  @Input() username: string = 'admin';
  @Input() password: string = 'admin';
  @Input() path: string = '/Shared/GraphRAG';
  
  @Output() urlChange = new EventEmitter<string>();
  @Output() usernameChange = new EventEmitter<string>();
  @Output() passwordChange = new EventEmitter<string>();
  @Output() pathChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<AlfrescoSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  get placeholder(): string {
    const baseUrl = environment.alfrescoBaseUrl || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco`;
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
                   this.path.trim() !== '';
    
    const config: AlfrescoSourceConfig = {
      url: this.url,
      username: this.username,
      password: this.password,
      path: this.path
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

  onPathChange(): void {
    this.pathChange.emit(this.path);
    this.updateValidationAndConfig();
  }
}
