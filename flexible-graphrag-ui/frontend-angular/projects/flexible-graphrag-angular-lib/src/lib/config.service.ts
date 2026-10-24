import { Inject, Injectable, Optional } from '@angular/core';
import { readPickedSources, sameServer, sourceAuthBody } from './services/source-auth.storage';
import {
  FLEXIBLE_GRAPHRAG_CONFIG,
  FLEXIBLE_GRAPHRAG_DEFAULTS,
  FlexibleGraphragConfig,
  HostSourceAuth
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
  get runInBackground(): boolean { return !!this.cfg.runInBackground; }
  /** The host passes its own signed-in user's Alfresco ticket with every question (KG Spaces in
   *  ACA): Alfresco ingests to that host's server use it too, so no credentials are asked for. */
  get hostSuppliesAlfrescoTicket(): boolean { return !!this.hostHeaders()['X-Alfresco-Ticket']; }
  /** The Alfresco server the host's ticket belongs to (X-Alfresco-Url, else alfrescoBaseUrl). */
  get hostAlfrescoUrl(): string { return this.hostHeaders()['X-Alfresco-Url'] || this.alfrescoBaseUrl; }
  /** The library's own sign-in is in use (sourceSignIn, default true). In a host that supplies
   *  its Alfresco ticket it still covers every OTHER server (Nuxeo, CMIS, a second Alfresco), but
   *  for ingest only: see searchSignIn. */
  get sourceSignIn(): boolean { return this.cfg.sourceSignIn !== false; }
  /** The source picker on Search / AI Chat (sourcePicker, default true -- in KG Spaces too). */
  get sourcePicker(): boolean { return this.cfg.sourcePicker !== false; }
  /** The library's sign-ins also apply to search / chat: the sign-in pill, a sign-in before the
   *  question, source_auth on it (next to the host's own identity). The searchSignIn option;
   *  unset, off in a host that supplies its own Alfresco ticket (questions then carry only that). */
  get searchSignIn(): boolean {
    return this.sourceSignIn && (this.cfg.searchSignIn ?? !this.hostSuppliesAlfrescoTicket);
  }
  /** The host already identifies the user on this server: the library needs no sign-in there. */
  hostCovers(source: string, url: string): boolean {
    if (source === 'alfresco' && this.hostSuppliesAlfrescoTicket && sameServer('alfresco', url, this.hostAlfrescoUrl)) {
      return true;
    }
    const host = this.hostIdentity();
    return !!host && host.source === source && sameServer(source, url, host.url);
  }

  /** Who is using the app (currentUser): the owner of its ingests and of its Jobs list; null when unknown. */
  currentUser(): string | null {
    try {
      return this.cfg.currentUser?.() || null;
    } catch {
      return null;
    }
  }

  /** The host's own identity on a repository (hostSourceAuth), or null. */
  hostIdentity(): HostSourceAuth | null {
    try {
      return this.cfg.hostSourceAuth?.() || null;
    } catch {
      return null;
    }
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
  /** Headers for a search / chat question: the host's own (e.g. KG Spaces' X-Alfresco-Ticket);
   *  {} when none. The library's sign-ins go in the body instead (questionSourceAuth). */
  questionHeaders(): Record<string, string> {
    return this.hostHeaders();
  }

  /** The library's sign-ins as a question's source_auth (one identity per server; servers the
   *  host already covers are left out), or undefined when there are none. */
  questionSourceAuth(): Record<string, any[]> | undefined {
    const body = this.searchSignIn ? sourceAuthBody((s) => this.hostCovers(s.source, s.url)) : {};
    const host = this.hostIdentity();   // the host's own identity goes in whether sign-ins are on or not
    if (host) {
      (body[host.source] ||= []).unshift({ url: host.url, ...host.auth });
    }
    return Object.keys(body).length ? body : undefined;
  }

  /** A search / chat request body with the library's sign-ins added as source_auth. Call it when
   *  posting (not once up front), so a retry after signing in again carries the new credential. */
  questionBody<T extends object>(body: T): T & { source_auth?: Record<string, any[]>; sources?: any[] } {
    const sourceAuth = this.questionSourceAuth();
    let out: any = sourceAuth ? { ...body, source_auth: sourceAuth } : body;
    // the source picker's choice (Search / AI Chat), unless the caller chose its own
    const picked = this.sourcePicker ? readPickedSources() : [];
    if (picked.length && !(out as any).sources) {
      out = { ...out, sources: picked.map((p) => (p.url ? { source: p.source, url: p.url } : { source: p.source })) };
    }
    return out;
  }

  private hostHeaders(): Record<string, string> {
    try {
      return this.cfg.requestHeaders?.() || {};
    } catch {
      return {};
    }
  }
}
