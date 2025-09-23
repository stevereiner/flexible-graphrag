import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface BoxSourceConfig {
  client_id: string;
  client_secret: string;
  developer_token: string;
  folder_id?: string;
}

@Component({
  selector: 'app-box-source-form',
  template: `
    <app-base-source-form 
      title="Box" 
      description="Connect to Box cloud storage">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Client ID *</mat-label>
        <input matInput
               [(ngModel)]="clientId"
               (ngModelChange)="onClientIdChange()"
               placeholder="your-box-client-id"
               required />
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Client Secret *</mat-label>
        <input matInput
               type="password"
               [(ngModel)]="clientSecret"
               (ngModelChange)="onClientSecretChange()"
               required />
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Developer Token *</mat-label>
        <input matInput
               type="password"
               [(ngModel)]="developerToken"
               (ngModelChange)="onDeveloperTokenChange()"
               required />
        <mat-hint>Box developer token for authentication</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Folder ID (Optional)</mat-label>
        <input matInput
               [(ngModel)]="folderId"
               (ngModelChange)="onFolderIdChange()"
               placeholder="123456789" />
        <mat-hint>Optional: specific Box folder ID</mat-hint>
      </mat-form-field>
    </app-base-source-form>
  `,
  styles: [`
    .full-width {
      width: 100%;
      margin-bottom: 16px;
    }
  `],
  standalone: false
})
export class BoxSourceFormComponent implements OnInit, OnDestroy {
  @Input() clientId: string = '';
  @Input() clientSecret: string = '';
  @Input() developerToken: string = '';
  
  @Output() clientIdChange = new EventEmitter<string>();
  @Output() clientSecretChange = new EventEmitter<string>();
  @Output() developerTokenChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<BoxSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  folderId: string = '';

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.clientId.trim() !== '' && 
                   this.clientSecret.trim() !== '' && 
                   this.developerToken.trim() !== '';
    
    const config: BoxSourceConfig = {
      client_id: this.clientId,
      client_secret: this.clientSecret,
      developer_token: this.developerToken,
      folder_id: this.folderId || undefined
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
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

  onFolderIdChange(): void {
    this.updateValidationAndConfig();
  }
}
