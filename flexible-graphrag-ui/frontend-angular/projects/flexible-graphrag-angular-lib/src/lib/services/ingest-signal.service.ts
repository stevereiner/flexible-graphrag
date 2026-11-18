import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

/**
 * The Processing tab says here each time an ingest starts. The Sources tab's lists (uploaded
 * files, local files and folders, the documents / folders picked in a repository or cloud
 * browser) empty then: the run's rows come from the configured sources, held apart from the
 * forms, so they stay in the Processing tab, where a different setting can still be chosen.
 */
@Injectable({ providedIn: 'root' })
export class IngestSignalService {
  private readonly started$ = new Subject<void>();
  readonly started = this.started$.asObservable();

  markStarted(): void {
    this.started$.next();
  }
}
