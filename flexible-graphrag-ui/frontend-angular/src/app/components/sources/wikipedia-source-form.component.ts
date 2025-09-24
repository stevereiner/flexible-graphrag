import { Component, Input, Output, EventEmitter, OnInit, OnDestroy } from '@angular/core';

export interface WikipediaSourceConfig {
  query: string;
  language: string;
  max_docs: number;
}

@Component({
  selector: 'app-wikipedia-source-form',
  template: `
    <app-base-source-form 
      title="Wikipedia" 
      description="Extract content from Wikipedia articles">
      
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Wikipedia URL or Query</mat-label>
        <input matInput
               [(ngModel)]="url"
               (ngModelChange)="onUrlChange()"
               placeholder="https://en.wikipedia.org/wiki/Article_Name or search query"
               required />
        <mat-hint>Enter a Wikipedia URL or search query to extract content from</mat-hint>
      </mat-form-field>

      <div class="form-row">
        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Language</mat-label>
          <mat-select [(value)]="language" (selectionChange)="onLanguageChange()">
            <mat-option value="en">English</mat-option>
            <mat-option value="es">Spanish</mat-option>
            <mat-option value="fr">French</mat-option>
            <mat-option value="de">German</mat-option>
            <mat-option value="it">Italian</mat-option>
            <mat-option value="pt">Portuguese</mat-option>
            <mat-option value="ru">Russian</mat-option>
            <mat-option value="zh">Chinese</mat-option>
            <mat-option value="ja">Japanese</mat-option>
            <mat-option value="ko">Korean</mat-option>
          </mat-select>
        </mat-form-field>

        <mat-form-field appearance="outline" class="half-width">
          <mat-label>Max Documents</mat-label>
          <input matInput
                 type="number"
                 [(ngModel)]="maxDocs"
                 (ngModelChange)="onMaxDocsChange()"
                 min="1"
                 max="50" />
          <mat-hint>Maximum number of articles to retrieve</mat-hint>
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
export class WikipediaSourceFormComponent implements OnInit, OnDestroy {
  @Input() url: string = '';
  @Input() language: string = 'en';
  @Input() maxDocs: number = 5;
  
  @Output() urlChange = new EventEmitter<string>();
  @Output() languageChange = new EventEmitter<string>();
  @Output() maxDocsChange = new EventEmitter<number>();
  @Output() configurationChange = new EventEmitter<WikipediaSourceConfig>();
  @Output() validationChange = new EventEmitter<boolean>();

  ngOnInit() {
    this.updateValidationAndConfig();
  }

  ngOnDestroy() {
    // Cleanup if needed
  }

  private updateValidationAndConfig() {
    const isValid = this.url.trim() !== '';
    
    // Extract query from URL if it's a Wikipedia URL
    let query = this.url;
    if (this.url.includes('wikipedia.org/wiki/')) {
      const parts = this.url.split('/wiki/');
      if (parts.length > 1) {
        // For Wikipedia URLs, preserve the exact page title format
        // Don't replace underscores with spaces for titles like "Nasdaq-100"
        query = decodeURIComponent(parts[1]);
        // Only replace underscores with spaces if the title doesn't contain hyphens
        // This preserves titles like "Nasdaq-100" while still handling "Albert_Einstein"
        if (!query.includes('-')) {
          query = query.replace(/_/g, ' ');
        }
      }
    }

    console.log('🔍 Angular Wikipedia URL parsing:', {
      originalUrl: this.url,
      extractedQuery: query,
      language: this.language,
      maxDocs: this.maxDocs
    });

    const config: WikipediaSourceConfig = {
      query: query,
      language: this.language,
      max_docs: this.maxDocs
    };
    
    this.validationChange.emit(isValid);
    this.configurationChange.emit(config);
  }

  onUrlChange(): void {
    this.urlChange.emit(this.url);
    this.updateValidationAndConfig();
  }

  onLanguageChange(): void {
    this.languageChange.emit(this.language);
    this.updateValidationAndConfig();
  }

  onMaxDocsChange(): void {
    this.maxDocsChange.emit(this.maxDocs);
    this.updateValidationAndConfig();
  }
}
