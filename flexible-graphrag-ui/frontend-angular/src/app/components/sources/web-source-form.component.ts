import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface WebSourceConfig {
  url: string;
}

@Component({
  selector: 'app-web-source-form',
  template: `
    <app-base-source-form 
      title="Web Page" 
      description="Extract content from any web page">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Website URL</mat-label>
        <input matInput
               [(ngModel)]="url"
               (ngModelChange)="onUrlChange()"
               placeholder="https://example.com"
               required />
        <mat-hint>Enter a valid website URL to extract content from</mat-hint>
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
export class WebSourceFormComponent implements OnInit, OnDestroy {
  @Input() url: string = '';
  @Output() urlChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<WebSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.url.trim() !== '' && this.url.startsWith('http');
    const config: WebSourceConfig = {
      url: this.url
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onUrlChange(): void {
    this.urlChange.emit(this.url);
    this.updateValidationAndConfig();
  }
}
