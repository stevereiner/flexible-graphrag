import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

type BoxAuthMode = 'developer_token' | 'ccg_user' | 'ccg_enterprise' | 'ccg_both';

export interface BoxSourceConfig {
  client_id?: string;
  client_secret?: string;
  developer_token?: string;
  user_id?: string;
  enterprise_id?: string;
  folder_id?: string;
}

@Component({
  selector: 'app-box-source-form',
  template: `
    <app-base-source-form 
      title="Box Storage" 
      description="Connect to Box with developer token or persistent app credentials">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Authentication Type</mat-label>
        <mat-select [(ngModel)]="authMode" (ngModelChange)="onAuthModeChange()">
          <mat-option value="developer_token">Developer Token</mat-option>
          <mat-option value="ccg_user">App Access (User)</mat-option>
          <mat-option value="ccg_enterprise">App Access (Enterprise)</mat-option>
          <mat-option value="ccg_both">App Access (User + Enterprise)</mat-option>
        </mat-select>
      </mat-form-field>

      <div *ngIf="authMode === 'developer_token'">
        <mat-form-field appearance="outline" class="full-width">
          <mat-label>Developer Token</mat-label>
          <input matInput
                 type="password"
                 [(ngModel)]="developerToken"
                 (ngModelChange)="onDeveloperTokenChange()" />
          <mat-hint>Temporary token for testing (expires after 1 hour)</mat-hint>
        </mat-form-field>
      </div>

      <div *ngIf="authMode !== 'developer_token'">
        <div class="d-flex gap-2 mb-3">
          <mat-form-field appearance="outline" class="flex-1">
            <mat-label>App Client ID</mat-label>
            <input matInput
                   [(ngModel)]="clientId"
                   (ngModelChange)="onClientIdChange()" />
          </mat-form-field>

          <mat-form-field appearance="outline" class="flex-1">
            <mat-label>App Client Secret</mat-label>
            <input matInput
                   type="password"
                   [(ngModel)]="clientSecret"
                   (ngModelChange)="onClientSecretChange()" />
          </mat-form-field>
        </div>

        <mat-form-field *ngIf="authMode === 'ccg_user' || authMode === 'ccg_both'" 
                        appearance="outline" class="full-width">
          <mat-label>Box User ID</mat-label>
          <input matInput
                 [(ngModel)]="userId"
                 (ngModelChange)="onUserIdChange()"
                 placeholder="12345678" />
          <mat-hint>Access files for a specific Box user</mat-hint>
        </mat-form-field>

        <mat-form-field *ngIf="authMode === 'ccg_enterprise' || authMode === 'ccg_both'" 
                        appearance="outline" class="full-width">
          <mat-label>Box Enterprise ID</mat-label>
          <input matInput
                 [(ngModel)]="enterpriseId"
                 (ngModelChange)="onEnterpriseIdChange()"
                 placeholder="987654321" />
          <mat-hint>Access files across your entire Box organization</mat-hint>
        </mat-form-field>
      </div>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Folder ID (Optional)</mat-label>
        <input matInput
               [(ngModel)]="folderId"
               (ngModelChange)="onFolderIdChange()"
               placeholder="0" />
        <mat-hint>Leave empty for root folder</mat-hint>
      </mat-form-field>
    </app-base-source-form>
  `,
  styles: [`
    .full-width {
      width: 100%;
      margin-bottom: 16px;
    }
    .d-flex {
      display: flex;
    }
    .gap-2 {
      gap: 16px;
    }
    .mb-3 {
      margin-bottom: 24px;
    }
    .flex-1 {
      flex: 1;
    }
  `],
  standalone: false
})
export class BoxSourceFormComponent implements OnInit, OnDestroy {
  @Input() clientId: string = '';
  @Input() clientSecret: string = '';
  @Input() developerToken: string = '';
  @Input() userId: string = '';
  @Input() enterpriseId: string = '';
  
  @Output() clientIdChange = new EventEmitter<string>();
  @Output() clientSecretChange = new EventEmitter<string>();
  @Output() developerTokenChange = new EventEmitter<string>();
  @Output() userIdChange = new EventEmitter<string>();
  @Output() enterpriseIdChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<BoxSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  folderId: string = '';
  authMode: BoxAuthMode = 'developer_token';

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    let isValid = false;
    switch (this.authMode) {
      case 'developer_token':
        isValid = this.developerToken.trim() !== '';
        break;
      case 'ccg_user':
        isValid = this.clientId.trim() !== '' && this.clientSecret.trim() !== '' && this.userId.trim() !== '';
        break;
      case 'ccg_enterprise':
        isValid = this.clientId.trim() !== '' && this.clientSecret.trim() !== '' && this.enterpriseId.trim() !== '';
        break;
      case 'ccg_both':
        isValid = this.clientId.trim() !== '' && this.clientSecret.trim() !== '' && 
                  this.userId.trim() !== '' && this.enterpriseId.trim() !== '';
        break;
    }
    
    const config: BoxSourceConfig = {
      client_id: this.authMode !== 'developer_token' ? this.clientId : undefined,
      client_secret: this.authMode !== 'developer_token' ? this.clientSecret : undefined,
      developer_token: this.authMode === 'developer_token' ? this.developerToken : undefined,
      user_id: (this.authMode === 'ccg_user' || this.authMode === 'ccg_both') ? this.userId : undefined,
      enterprise_id: (this.authMode === 'ccg_enterprise' || this.authMode === 'ccg_both') ? this.enterpriseId : undefined,
      folder_id: this.folderId || undefined
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onAuthModeChange(): void {
    this.updateValidationAndConfig();
  }

  onClientIdChange(): void {
    this.clientIdChange.emit(this.clientId);
    this.updateValidationAndConfig();
  }

  onClientSecretChange(): void {
    this.clientSecretChange.emit(this.clientSecret);
    this.updateValidationAndConfig();
  }

  onDeveloperTokenChange(): void {
    this.developerTokenChange.emit(this.developerToken);
    this.updateValidationAndConfig();
  }

  onUserIdChange(): void {
    this.userIdChange.emit(this.userId);
    this.updateValidationAndConfig();
  }

  onEnterpriseIdChange(): void {
    this.enterpriseIdChange.emit(this.enterpriseId);
    this.updateValidationAndConfig();
  }

  onFolderIdChange(): void {
    this.updateValidationAndConfig();
  }
}
