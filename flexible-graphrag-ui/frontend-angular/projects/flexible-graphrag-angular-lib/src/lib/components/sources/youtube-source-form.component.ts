import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface YouTubeSourceConfig {
  url: string;
  chunk_size_seconds: number;
}

@Component({
  selector: 'app-youtube-source-form',
  template: `
    <app-base-source-form 
      title="YouTube" 
      description="Extract transcripts from YouTube videos">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>YouTube URL</mat-label>
        <input matInput
               [(ngModel)]="url"
               (ngModelChange)="onUrlChange()"
               placeholder="https://www.youtube.com/watch?v=..."
               required />
        <mat-hint>Enter a YouTube video URL to extract transcript from</mat-hint>
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
export class YouTubeSourceFormComponent implements OnInit, OnDestroy {
  @Input() url: string = '';
  
  @Output() urlChange = new EventEmitter<string>();
  @Output() configurationChange = new EventEmitter<YouTubeSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.url.trim() !== '' && 
                   (this.url.includes('youtube.com/watch') || this.url.includes('youtu.be/'));
    
    const config: YouTubeSourceConfig = {
      url: this.url,
      chunk_size_seconds: 60  // Use default value
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onUrlChange(): void {
    this.urlChange.emit(this.url);
    this.updateValidationAndConfig();
  }
}
