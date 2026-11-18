import { Component, Input, Output, EventEmitter, OnInit, OnDestroy, inject } from '@angular/core';
import { SourceBrowserService } from '../../browser/remote-browse.provider';

export interface S3SourceConfig {
  bucket_name: string;
  prefix?: string;
  access_key: string;
  secret_key: string;
  region_name: string;
  sqs_queue_url?: string;
}

@Component({
  selector: 'app-s3-source-form',
  template: `
    <app-base-source-form 
      title="Amazon S3" 
      description="Connect to Amazon S3 buckets using bucket name and credentials">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Bucket Name</mat-label>
        <input matInput
               [(ngModel)]="bucketName"
               (ngModelChange)="onBucketNameChange()"
               placeholder="my-bucket"
               required
               autocomplete="off" />
        <mat-hint>S3 bucket name (required)</mat-hint>
      </mat-form-field>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Prefix/Path (Optional)</mat-label>
          <input matInput
                 [(ngModel)]="prefix"
                 (ngModelChange)="onPrefixChange()"
                 placeholder="documents/reports/"
                 autocomplete="off" />
          <mat-hint>Optional: a folder prefix within the bucket (ending in /), or one object's key</mat-hint>
        </mat-form-field>
        <button mat-stroked-button type="button" class="browse-button" [disabled]="!isValid()"
                [title]="isValid() ? 'Pick a folder or a file in the bucket' : 'Fill in the bucket, region and keys first'"
                (click)="browse()">
          <mat-icon>folder_open</mat-icon> Browse…
        </button>
      </div>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>AWS Region</mat-label>
        <input matInput
               [(ngModel)]="regionName"
               (ngModelChange)="onRegionNameChange()"
               placeholder="us-east-1"
               required
               autocomplete="off" />
        <mat-hint>AWS region where the bucket is located (e.g., us-east-1, us-east-2, eu-west-1)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>SQS Queue URL (Optional)</mat-label>
        <input matInput
               type="url"
               name="sqs-endpoint-url"
               [(ngModel)]="sqsQueueUrl"
               (ngModelChange)="onSqsQueueUrlChange()"
               placeholder="https://sqs.us-east-2.amazonaws.com/123456789/my-queue"
               autocomplete="off"
               data-lpignore="true"
               data-form-type="other"
               data-1p-ignore="true" />
        <mat-hint>Optional: SQS queue URL for real-time event-based sync (leave empty for periodic polling)</mat-hint>
      </mat-form-field>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Access Key</mat-label>
          <input matInput
                 type="password"
                 [(ngModel)]="accessKey"
                 (ngModelChange)="onAccessKeyChange()"
                 required
                 autocomplete="new-password" />
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Secret Key</mat-label>
          <input matInput
                 type="password"
                 [(ngModel)]="secretKey"
                 (ngModelChange)="onSecretKeyChange()"
                 required
                 autocomplete="new-password" />
        </mat-form-field>
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
export class S3SourceFormComponent implements OnInit, OnDestroy {
  @Input() accessKey: string = '';
  @Input() secretKey: string = '';
  
  @Output() accessKeyChange = new EventEmitter<string>();
  @Output() secretKeyChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<S3SourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  bucketName: string = '';
  prefix: string = '';
  regionName: string = '';  // starts empty; placeholder shows e.g. us-east-1
  sqsQueueUrl: string = '';

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private readonly browser = inject(SourceBrowserService);
  private readonly provider = this.browser.provider('s3', 'S3 bucket', () => this.config());

  isValid(): boolean {
    return this.bucketName.trim() !== '' && this.accessKey.trim() !== '' &&
      this.secretKey.trim() !== '' && this.regionName.trim() !== '';
  }

  private config(): S3SourceConfig {
    return {
      bucket_name: this.bucketName,
      prefix: this.prefix || undefined,
      access_key: this.accessKey,
      secret_key: this.secretKey,
      region_name: this.regionName,
      sqs_queue_url: this.sqsQueueUrl || undefined
    };
  }

  /** One folder ("docs/reports/") or one object's key: the prefix takes either. */
  async browse(): Promise<void> {
    const [item] = await this.browser.pick({
      provider: this.provider, title: `Pick a folder or a file: s3://${this.bucketName}`, multiple: false,
    });
    if (!item) return;
    this.prefix = item.path || item.id;
    this.updateValidationAndConfig();
  }

  private updateValidationAndConfig() {
    this.validationChange.emit(this.isValid());
    this.configurationChange.emit(this.config());
  }

  onBucketNameChange(): void {
    this.updateValidationAndConfig();
  }

  onPrefixChange(): void {
    this.updateValidationAndConfig();
  }

  onRegionNameChange(): void {
    this.updateValidationAndConfig();
  }

  onSqsQueueUrlChange(): void {
    this.updateValidationAndConfig();
  }

  onAccessKeyChange(): void {
    this.accessKeyChange.emit(this.accessKey);
    this.updateValidationAndConfig();
  }

  onSecretKeyChange(): void {
    this.secretKeyChange.emit(this.secretKey);
    this.updateValidationAndConfig();
  }
}
