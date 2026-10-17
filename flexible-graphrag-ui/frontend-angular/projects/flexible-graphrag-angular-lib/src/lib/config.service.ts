import { Inject, Injectable, Optional } from '@angular/core';
import { readAlfrescoSession } from './services/source-auth.storage';
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
  /** The library's own Alfresco sign-in is in use: enabled, and the host supplies no ticket. */
  /** The host passes its own signed-in user's Alfresco ticket with every question (KG Spaces in
   *  ACA): Alfresco ingests to that host's server use it too, so no credentials are asked for. */
  get hostSuppliesAlfrescoTicket(): boolean { return !!this.hostHeaders()['X-Alfresco-Ticket']; }
  get sourceSignIn(): boolean {
    return this.cfg.sourceSignIn !== false && !this.hostHeaders()['X-Alfresco-Ticket'];
  }
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
  /** Headers for a search / chat question (e.g. the user's Alfresco ticket); {} when none.
   *  The host's own headers win; otherwise the ticket from the library's sign-in, if any. */
  questionHeaders(): Record<string, string> {
    const headers = this.hostHeaders();
    if (!headers['X-Alfresco-Ticket'] && this.cfg.sourceSignIn !== false) {
      const session = readAlfrescoSession();
      // the ticket plus the Alfresco server it belongs to (several servers can be in the stores)
      if (session?.ticket) return { ...headers, 'X-Alfresco-Ticket': session.ticket, 'X-Alfresco-Url': session.url };
    }
    return headers;
  }

  private hostHeaders(): Record<string, string> {
    try {
      return this.cfg.requestHeaders?.() || {};
    } catch {
      return {};
    }
  }
}
