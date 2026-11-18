import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, inject } from '@angular/core';
import { SourceBrowserService } from '../../browser/remote-browse.provider';

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
        <mat-label>Bucket Name</mat-label>
        <input matInput
               [(ngModel)]="bucketName"
               (ngModelChange)="onBucketNameChange()"
               placeholder="my-gcs-bucket"
               required />
        <mat-hint>GCS bucket name (required)</mat-hint>
      </mat-form-field>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Prefix (Optional)</mat-label>
          <input matInput
                 [(ngModel)]="prefix"
                 (ngModelChange)="onPrefixChange()"
                 placeholder="sample-docs/" />
          <mat-hint>Optional: folder path prefix (e.g., 'sample-docs/' for a specific folder)</mat-hint>
        </mat-form-field>
        <button mat-stroked-button type="button" class="browse-button" [disabled]="!isValid()"
                [title]="isValid() ? 'Pick a folder in the bucket' : 'Fill in the bucket and the credentials first'"
                (click)="browse()">
          <mat-icon>folder_open</mat-icon> Browse…
        </button>
      </div>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Service Account Credentials (JSON)</mat-label>
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

  private readonly browser = inject(SourceBrowserService);
  private readonly provider = this.browser.provider('gcs', 'GCS bucket', () => this.config());

  isValid(): boolean {
    return this.bucketName.trim() !== '' && this.credentials.trim() !== '';
  }

  private config(): GCSSourceConfig {
    return {
      bucket_name: this.bucketName,
      credentials: this.credentials,
      prefix: this.prefix || undefined,
      pubsub_subscription: this.pubsubSubscription || undefined
    };
  }

  /** A folder's prefix ("docs/2024/"): the ingest reads a prefix as a folder (one object would
   *  need GCSConfig `key`, not taken from the UI yet). */
  async browse(): Promise<void> {
    const [folder] = await this.browser.pick({
      provider: this.provider, title: `Pick a folder: gs://${this.bucketName}`, files: false, multiple: false,
    });
    if (!folder) return;
    this.prefix = folder.path || folder.id;
    this.onPrefixChange();
  }

  private updateValidationAndConfig() {
    this.validationChange.emit(this.isValid());
    this.configurationChange.emit(this.config());
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
