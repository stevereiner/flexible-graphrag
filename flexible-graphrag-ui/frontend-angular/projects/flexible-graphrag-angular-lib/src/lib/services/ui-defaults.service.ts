import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { FlexibleGraphragConfigService } from '../config.service';

/** GET /api/ui-defaults: where the UI's choices start. */
export interface UiDefaults {
  recursive?: boolean;      // the Deep checkbox on the Alfresco / Nuxeo / Box forms (DEFAULT_RECURSIVE)
  enabled_graph?: boolean;  // a new Processing row's Graph checkbox (DEFAULT_ENABLED_GRAPH)
  enabled_rdf?: boolean;    // ...and its RDF checkbox (DEFAULT_ENABLED_RDF)
  show_graph?: boolean;
  show_rdf?: boolean;
}

/**
 * The backend's UI defaults, asked once per page load. An older backend has no such endpoint:
 * {} then, and each caller falls back to what that backend did when not told.
 */
@Injectable({ providedIn: 'root' })
export class UiDefaultsService {
  private readonly http = inject(HttpClient);
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private request: Promise<UiDefaults> | null = null;
  /** What has arrived so far ({} until then). */
  defaults: UiDefaults = {};

  load(): Promise<UiDefaults> {
    // v0.9.0: restore the request below. The 0.8.6 backend has no /api/ui-defaults, and asking it only
    // logs a 404; until then every caller gets {} and uses its fallback.
    // this.request ||= firstValueFrom(this.http.get<UiDefaults>(`${this.fgConfig.apiUrl}/ui-defaults`))
    //   .then((d) => (this.defaults = d || {}))
    //   .catch(() => ({}));
    this.request ||= Promise.resolve(this.defaults);
    return this.request;
  }
}
