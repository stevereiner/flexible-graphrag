import { Component, EventEmitter, NgZone, OnDestroy, OnInit, Output, inject } from '@angular/core';
import { FlexibleGraphragThemeService, desktopInvoke } from '@flexible-graphrag/angular-ui';

/** desktop/src-tauri/src/backend.rs `backend_status` */
interface BackendStatus {
  state: 'starting' | 'ready' | 'external' | 'failed';
  message?: string | null;
  log_path?: string | null;
}

/**
 * Desktop app: the app starts its own backend, which takes a while (first start: a minute or
 * more). Shown instead of the app until the backend answers, so the app's first requests don't
 * fail; a failure shows the backend's message (its log tail) and where the log is.
 */
@Component({
  selector: 'app-backend-gate',
  template: `
    <div class="gate">
      <div *ngIf="status.state === 'failed'; else starting" class="gate-failed">
        <div class="gate-error" role="alert">
          <h3>No Flexible GraphRAG backend to use.</h3>
          <pre>{{ status.message }}</pre>
          <p *ngIf="status.log_path">Log: {{ status.log_path }}</p>
        </div>
        <button mat-stroked-button type="button" class="gate-open" (click)="ready.emit()">Open the app anyway</button>
      </div>
      <ng-template #starting>
        <div class="gate-starting">
          <mat-spinner diameter="40"></mat-spinner>
          <h3>Starting the Flexible GraphRAG backend… {{ seconds > 0 ? seconds + ' s' : '' }}</h3>
          <p class="gate-muted">The first start can take a minute or more.</p>
          <p class="gate-muted gate-small" *ngIf="status.log_path">Log: {{ status.log_path }}</p>
        </div>
      </ng-template>
    </div>
  `,
  styles: [`
    .gate { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 32px;
            box-sizing: border-box; }
    .gate-starting { text-align: center; display: flex; flex-direction: column; align-items: center; }
    .gate-starting h3 { margin: 16px 0 4px; font-weight: 500; }
    .gate-muted { opacity: 0.7; margin: 4px 0; }
    .gate-small { font-size: 12px; }
    .gate-failed { max-width: 900px; width: 100%; }
    .gate-error { border-radius: 4px; padding: 12px 16px; margin-bottom: 16px;
                  background: rgba(244, 67, 54, 0.12); border: 1px solid rgba(244, 67, 54, 0.5); }
    .gate-error h3 { margin: 0 0 8px; font-weight: 500; }
    .gate-error pre { white-space: pre-wrap; word-break: break-word; font-family: monospace; margin: 0; font-size: 13px; }
    .gate-error p { margin: 8px 0 0; font-size: 13px; }
    :host-context(.dark-theme) .gate { background: #121212; color: #ffffff; }
    :host-context(.dark-theme) .gate-open { color: #ffffff; border-color: rgba(144, 202, 249, 0.7); }
  `],
  standalone: false
})
export class BackendGateComponent implements OnInit, OnDestroy {
  /** The backend answers (or the user opens the app anyway). */
  @Output() ready = new EventEmitter<void>();

  status: BackendStatus = { state: 'starting' };
  seconds = 0;
  private stop = false;
  private readonly zone = inject(NgZone);

  constructor() {
    inject(FlexibleGraphragThemeService);  // dark / light from the start (the title bar isn't shown yet)
  }

  ngOnInit(): void {
    this.poll();
  }

  ngOnDestroy(): void {
    this.stop = true;
  }

  private async poll(): Promise<void> {
    const started = Date.now();
    while (!this.stop) {
      // in the zone: the desktop's IPC answer may arrive outside it, and the screen must update
      try {
        const s = await desktopInvoke<BackendStatus>('backend_status');
        this.zone.run(() => (this.status = s));
        if (s.state === 'ready' || s.state === 'external') {
          this.zone.run(() => this.ready.emit());
          return;
        }
        if (s.state === 'failed') return;
      } catch (e) {
        this.zone.run(() => (this.status = { state: 'failed', message: `backend_status: ${e}` }));
        return;
      }
      this.zone.run(() => (this.seconds = Math.round((Date.now() - started) / 1000)));
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
}
