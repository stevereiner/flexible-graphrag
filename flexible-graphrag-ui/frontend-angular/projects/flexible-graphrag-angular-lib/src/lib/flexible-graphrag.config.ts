import { InjectionToken } from '@angular/core';
import type { SourceDocument } from './models/api.models';

/**
 * Host-supplied configuration for the shared Flexible GraphRAG UI.
 *
 * A library cannot import `environments/environment` -- that file is an application build
 * artifact, replaced per-configuration by angular.json's fileReplacements, and it does not
 * exist for a consumer such as an ACA extension. Each host provides this token instead: the
 * standalone app from its `environment`, an ACA/ADF extension from `app.config.json` via
 * AppConfigService.
 */
export interface FlexibleGraphragConfig {
  /** Base URL for Flexible GraphRAG API requests, e.g. '/api'. */
  apiUrl: string;
  /** Default folder shown in the CMIS / Alfresco source dialogs. */
  defaultFolderPath?: string;
  cmisBaseUrl?: string;
  alfrescoBaseUrl?: string;
  nuxeoBaseUrl?: string;
  nuxeoPath?: string;
  /**
   * Data sources to offer in the Sources tab. Omit for all of them. An ACA extension that
   * already knows its repository can narrow this, e.g. to hide the Alfresco form once the
   * node selection and ticket come from ACA itself.
   */
  enabledSources?: string[];
  /**
   * URL of the AI-chat agent avatar. A library cannot rely on a host serving
   * `assets/agent.png`: that path exists in the standalone app but not in an ACA host, where
   * the broken image is easy to miss. Each host points this at its own copy.
   */
  agentIconUrl?: string;
  /**
   * Processing tab text when no data source is configured, and the label of its button to the
   * Sources tab. A host where the selection comes from elsewhere (ACA's document list) says so.
   */
  noSourcesMessage?: string;
  goToSourcesLabel?: string;
  /** AI Chat welcome: its heading and the lines under it (a host brands it, e.g. KG Spaces). */
  chatWelcomeTitle?: string;
  chatWelcomeLines?: string[];
  /**
   * Show the AI Chat "Asking about: ..." bar even with no scope ("All content"). A host that
   * hands the chat a document or folder (ACA's "Ask AI about this ...") turns it on.
   */
  showChatScope?: boolean;
  /**
   * Extra HTTP headers for search / chat questions, evaluated per request. KG Spaces sends the
   * signed-in user's Alfresco ticket (X-Alfresco-Ticket) so answers come only from documents
   * that user may read.
   */
  requestHeaders?: () => Record<string, string>;
  /**
   * Repository sign-in for search / AI chat (planning/SOURCE-AUTH-LOGIN.md): before a question,
   * when the stores hold Alfresco, Nuxeo or CMIS documents, ask the user to sign in to each such
   * server (Alfresco ticket / Nuxeo token, as their own clients do) so answers come only from
   * what they may read. Default true. The server whose ticket requestHeaders supplies
   * (X-Alfresco-Ticket: KG Spaces passes ACA's) needs no sign-in of its own; see searchSignIn for
   * the others.
   */
  sourceSignIn?: boolean;
  /**
   * The library's sign-ins also apply to search / AI chat (the sign-in pill, a sign-in before a
   * question, `source_auth` on it) in a host that supplies its own Alfresco ticket. Unset: on,
   * except in such a host, where questions then carry only the host's identity and the forms'
   * sign-ins serve ingest only (KG Spaces before 0.8.6). KG Spaces sets it true: questions carry
   * ACA's ticket plus the user's sign-ins to every other server and source.
   */
  searchSignIn?: boolean;
  /**
   * Source picker on Search (Hybrid Search + AI Query) and AI Chat: "All sources" plus one chip per
   * source with documents in the stores, sent as the question's `sources`. Default true, KG Spaces
   * included. A repository the user has no identity for (outside what requestHeaders covers) shows
   * greyed.
   */
  sourcePicker?: boolean;
  /**
   * Open a result's / answer's source document in the host's own viewer. Return true when
   * handled; otherwise the document's `open_url` (if any) opens in a new tab. KG Spaces opens
   * Alfresco nodes in ACA's viewer.
   */
  openDocument?: (doc: SourceDocument) => boolean;
  /** Whether `openDocument` can open this document (shows it as a link without an open_url). */
  canOpenDocument?: (doc: SourceDocument) => boolean;
}

export const FLEXIBLE_GRAPHRAG_CONFIG = new InjectionToken<FlexibleGraphragConfig>(
  'FLEXIBLE_GRAPHRAG_CONFIG'
);

/** Defaults for anything the host leaves unset. */
export const FLEXIBLE_GRAPHRAG_DEFAULTS: Required<Omit<FlexibleGraphragConfig, 'enabledSources' | 'requestHeaders' | 'openDocument' | 'canOpenDocument' | 'searchSignIn'>> = {
  apiUrl: '/api',
  defaultFolderPath: '/Shared/GraphRAG',
  cmisBaseUrl: 'http://localhost:8080',
  alfrescoBaseUrl: 'http://localhost:8080',
  nuxeoBaseUrl: 'http://localhost:8081/nuxeo',
  nuxeoPath: '/default-domain/workspaces/GraphRAG',
  agentIconUrl: 'assets/agent.png',
  noSourcesMessage: 'Please go to the Sources tab to configure your data source first.',
  goToSourcesLabel: '← Go to Sources',
  sourceSignIn: true,
  sourcePicker: true,
  chatWelcomeTitle: 'Welcome to Flexible GraphRAG Chat',
  chatWelcomeLines: [
    'Ask questions about your documents and get conversational answers.',
    'The AI will provide detailed responses based on your processed documents.',
  ],
  showChatScope: false
};
