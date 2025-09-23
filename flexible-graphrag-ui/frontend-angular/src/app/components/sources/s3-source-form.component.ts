import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface S3SourceConfig {
  bucket_name: string;
  prefix?: string;
  access_key: string;
  secret_key: string;
}

@Component({
  selector: 'app-s3-source-form',
  template: `
    <app-base-source-form 
      title="Amazon S3" 
      description="Connect to Amazon S3 buckets using bucket name and credentials">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Bucket Name *</mat-label>
        <input matInput
               [(ngModel)]="bucketName"
               (ngModelChange)="onBucketNameChange()"
               placeholder="my-bucket"
               required
               autocomplete="off" />
        <mat-hint>S3 bucket name (required)</mat-hint>
      </mat-form-field>

      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Prefix/Path (Optional)</mat-label>
        <input matInput
               [(ngModel)]="prefix"
               (ngModelChange)="onPrefixChange()"
               placeholder="documents/reports/"
               autocomplete="off" />
        <mat-hint>Optional: folder path prefix within bucket</mat-hint>
      </mat-form-field>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Access Key *</mat-label>
          <input matInput
                 type="password"
                 [(ngModel)]="accessKey"
                 (ngModelChange)="onAccessKeyChange()"
                 required
                 autocomplete="off" />
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Secret Key *</mat-label>
          <input matInput
                 type="password"
                 [(ngModel)]="secretKey"
                 (ngModelChange)="onSecretKeyChange()"
                 required
                 autocomplete="off" />
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

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.bucketName.trim() !== '' && 
                   this.accessKey.trim() !== '' && 
                   this.secretKey.trim() !== '';
    
    const config: S3SourceConfig = {
      bucket_name: this.bucketName,
      prefix: this.prefix || undefined,
      access_key: this.accessKey,
      secret_key: this.secretKey
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onBucketNameChange(): void {
    this.updateValidationAndConfig();
  }

  onPrefixChange(): void {
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
