import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-base-source-form',
  template: `
    <div class="base-source-form">
      <h3>{{ title }}</h3>
      <p *ngIf="description" class="description">{{ description }}</p>
      <ng-content></ng-content>
    </div>
  `,
  styles: [`
    .base-source-form {
      margin-bottom: 16px;
    }
    
    h3 {
      margin-bottom: 8px;
      font-weight: 500;
    }
    
    .description {
      color: var(--mat-sys-on-surface-variant);
      margin-bottom: 16px;
      font-size: 14px;
    }
    
    /* Fallback for older Material versions */
    :host-context(.mat-app-background) .description {
      color: rgba(0, 0, 0, 0.6);
    }
    
    /* Dark theme support */
    :host-context(.dark-theme) .description,
    :host-context([data-theme="dark"]) .description {
      color: rgba(255, 255, 255, 0.7);
    }
  `],
  standalone: false
})
export class BaseSourceFormComponent {
  @Input() title: string = '';
  @Input() description: string = '';
}
