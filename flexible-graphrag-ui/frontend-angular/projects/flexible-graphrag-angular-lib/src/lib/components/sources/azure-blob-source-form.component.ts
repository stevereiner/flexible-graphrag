import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface AzureBlobSourceConfig {
  container_name: string;
  account_url: string;
  blob?: string;
  prefix?: string;
  account_name: string;
  account_key: string;
}

@Component({
  selector: 'app-azure-blob-source-form',
  template: `
    <app-base-source-form 
      title="Azure Blob Storage" 
      description="Connect to Azure Blob Storage using Account Key Authentication (Method 1)">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Account URL *</mat-label>
        <input matInput
               [(ngModel)]="accountUrl"
               (ngModelChange)="onAccountUrlChange()"
               placeholder="https://mystorageaccount.blob.core.windows.net"
               required />
        <mat-hint>Azure Storage account URL (required)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Container Name *</mat-label>
        <input matInput
               [(ngModel)]="containerName"
               (ngModelChange)="onContainerNameChange()"
               placeholder="my-container"
               required />
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Blob (Optional)</mat-label>
        <input matInput
               [(ngModel)]="blobName"
               (ngModelChange)="onBlobNameChange()"
               placeholder="specific-file.pdf" />
        <mat-hint>Optional: specific blob/file name</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Prefix (Optional)</mat-label>
        <input matInput
               [(ngModel)]="prefix"
               (ngModelChange)="onPrefixChange()"
               placeholder="documents/reports/" />
        <mat-hint>Optional: folder path prefix within container</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Account Name *</mat-label>
        <input matInput
               [(ngModel)]="accountName"
               (ngModelChange)="onAccountNameChange()"
               placeholder="mystorageaccount"
               required />
        <mat-hint>Azure Storage account name (required)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Account Key *</mat-label>
        <input matInput
               type="password"
               [(ngModel)]="accountKey"
               (ngModelChange)="onAccountKeyChange()"
               placeholder="account-key-here"
               required />
        <mat-hint>Azure Storage account key (required)</mat-hint>
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
export class AzureBlobSourceFormComponent implements OnInit, OnDestroy {
  @Input() connectionString: string = '';
  @Input() containerName: string = '';
  @Input() blobName: string = '';
  @Input() accountName: string = '';
  @Input() accountKey: string = '';
  
  @Output() connectionStringChange = new EventEmitter<string>();
  @Output() containerNameChange = new EventEmitter<string>();
  @Output() blobNameChange = new EventEmitter<string>();
  @Output() accountNameChange = new EventEmitter<string>();
  @Output() accountKeyChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<AzureBlobSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  prefix: string = '';
  accountUrl: string = '';

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    // Method 1 requires: account_url, container_name, account_name, account_key
    const isValid = this.accountUrl.trim() !== '' && 
                   this.containerName.trim() !== '' && 
                   this.accountName.trim() !== '' && 
                   this.accountKey.trim() !== '';
    
    const config: AzureBlobSourceConfig = {
      // Method 1 (Account Key Authentication) fields
      container_name: this.containerName,
      account_url: this.accountUrl,
      blob: this.blobName || undefined,
      prefix: this.prefix || undefined,
      account_name: this.accountName,
      account_key: this.accountKey
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onAccountUrlChange(): void {
    this.updateValidationAndConfig();
  }

  onContainerNameChange(): void {
    this.containerNameChange.emit(this.containerName);
    this.updateValidationAndConfig();
  }

  onBlobNameChange(): void {
    this.blobNameChange.emit(this.blobName);
    this.updateValidationAndConfig();
  }

  onPrefixChange(): void {
    this.updateValidationAndConfig();
  }

  onAccountNameChange(): void {
    this.accountNameChange.emit(this.accountName);
    this.updateValidationAndConfig();
  }

  onAccountKeyChange(): void {
    this.accountKeyChange.emit(this.accountKey);
    this.updateValidationAndConfig();
  }
}
