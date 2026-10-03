import { Inject, Injectable, Optional } from '@angular/core';
import {
  FLEXIBLE_GRAPHRAG_CONFIG,
  FLEXIBLE_GRAPHRAG_DEFAULTS,
  FlexibleGraphragConfig
} from './flexible-graphrag.config';

/**
 * Resolves the host's configuration, falling back to defaults field by field so a host can
 * provide only what it cares about (an ACA extension typically sets just apiUrl).
 */
@Injectable({ providedIn: 'root' })
export class FlexibleGraphragConfigService {
  private readonly cfg: FlexibleGraphragConfig;

  constructor(@Optional() @Inject(FLEXIBLE_GRAPHRAG_CONFIG) provided: FlexibleGraphragConfig | null) {
    this.cfg = { ...FLEXIBLE_GRAPHRAG_DEFAULTS, ...(provided || {}) };
  }

  get apiUrl(): string { return this.cfg.apiUrl; }
  get defaultFolderPath(): string { return this.cfg.defaultFolderPath!; }
  get cmisBaseUrl(): string { return this.cfg.cmisBaseUrl!; }
  get alfrescoBaseUrl(): string { return this.cfg.alfrescoBaseUrl!; }
  get nuxeoBaseUrl(): string { return this.cfg.nuxeoBaseUrl!; }
  get nuxeoPath(): string { return this.cfg.nuxeoPath!; }
  get enabledSources(): string[] | undefined { return this.cfg.enabledSources; }
  get agentIconUrl(): string { return this.cfg.agentIconUrl!; }
}
