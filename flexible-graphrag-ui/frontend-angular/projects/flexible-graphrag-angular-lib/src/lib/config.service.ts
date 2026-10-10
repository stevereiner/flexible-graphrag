import { Inject, Injectable, Optional } from '@angular/core';
import {
  FLEXIBLE_GRAPHRAG_CONFIG,
  FLEXIBLE_GRAPHRAG_DEFAULTS,
  FlexibleGraphragConfig
} from './flexible-graphrag.config';
import type { SourceDocument } from './models/api.models';

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
  get noSourcesMessage(): string { return this.cfg.noSourcesMessage!; }
  get goToSourcesLabel(): string { return this.cfg.goToSourcesLabel!; }
  get chatWelcomeTitle(): string { return this.cfg.chatWelcomeTitle!; }
  get chatWelcomeLines(): string[] { return this.cfg.chatWelcomeLines!; }
  get showChatScope(): boolean { return !!this.cfg.showChatScope; }
  /** Open a source document in the host's viewer; false when the host does not handle it. */
  openDocument(doc: SourceDocument): boolean {
    try {
      return !!this.cfg.openDocument?.(doc);
    } catch {
      return false;
    }
  }
  canOpenDocument(doc: SourceDocument): boolean {
    try {
      return !!this.cfg.canOpenDocument?.(doc);
    } catch {
      return false;
    }
  }
  /** Headers for a search / chat question (e.g. the user's Alfresco ticket); {} when none. */
  questionHeaders(): Record<string, string> {
    try {
      return this.cfg.requestHeaders?.() || {};
    } catch {
      return {};
    }
  }
}
