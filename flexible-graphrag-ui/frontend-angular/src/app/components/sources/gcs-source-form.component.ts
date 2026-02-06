import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface GCSSourceConfig {
  bucket_name: string;
  credentials: string;
  prefix?: string;
  pubsub_subscription?: string;
}

@Component({
  selector: 'app-gcs-source-form',
  template: `
    <app-base-source-form 
      title="Google Cloud Storage" 
      description="Connect to Google Cloud Storage buckets">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Bucket Name *</mat-label>
        <input matInput
               [(ngModel)]="bucketName"
               (ngModelChange)="onBucketNameChange()"
               placeholder="my-gcs-bucket"
               required />
        <mat-hint>GCS bucket name (required)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Prefix (Optional)</mat-label>
        <input matInput
               [(ngModel)]="prefix"
               (ngModelChange)="onPrefixChange()"
               placeholder="sample-docs/" />
        <mat-hint>Optional: folder path prefix (e.g., 'sample-docs/' for a specific folder)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Service Account Credentials (JSON) *</mat-label>
        <textarea matInput
                  [(ngModel)]="credentials"
                  (ngModelChange)="onCredentialsChange()"
                  placeholder='{"type": "service_account", "project_id": "...", ...}'
                  rows="4"
                  required></textarea>
        <mat-hint>JSON service account key (includes project_id)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Pub/Sub Subscription (Optional)</mat-label>
        <input matInput
               [(ngModel)]="pubsubSubscription"
               (ngModelChange)="onPubsubSubscriptionChange()"
               placeholder="gcs-notifications-sub" />
        <mat-hint>Pub/Sub subscription name for real-time change detection (leave empty for periodic polling)</mat-hint>
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
export class GCSSourceFormComponent implements OnInit, OnDestroy {
  @Input() bucketName: string = '';
  @Input() credentials: string = '';
  @Input() prefix: string = '';
  @Input() pubsubSubscription: string = '';
  
  @Output() bucketNameChange = new EventEmitter<string>();
  @Output() credentialsChange = new EventEmitter<string>();
  @Output() prefixChange = new EventEmitter<string>();
  @Output() pubsubSubscriptionChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<GCSSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.bucketName.trim() !== '' && 
                   this.credentials.trim() !== '';
    
    const config: GCSSourceConfig = {
      bucket_name: this.bucketName,
      credentials: this.credentials,
      prefix: this.prefix || undefined,
      pubsub_subscription: this.pubsubSubscription || undefined
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onBucketNameChange(): void {
    this.bucketNameChange.emit(this.bucketName);
    this.updateValidationAndConfig();
  }

  onCredentialsChange(): void {
    this.credentialsChange.emit(this.credentials);
    this.updateValidationAndConfig();
  }

  onPrefixChange(): void {
    this.prefixChange.emit(this.prefix);
    this.updateValidationAndConfig();
  }

  onPubsubSubscriptionChange(): void {
    this.pubsubSubscriptionChange.emit(this.pubsubSubscription);
    this.updateValidationAndConfig();
  }
}
