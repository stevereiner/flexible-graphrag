import { InjectionToken } from '@angular/core';

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
}

export const FLEXIBLE_GRAPHRAG_CONFIG = new InjectionToken<FlexibleGraphragConfig>(
  'FLEXIBLE_GRAPHRAG_CONFIG'
);

/** Defaults for anything the host leaves unset. */
export const FLEXIBLE_GRAPHRAG_DEFAULTS: Required<Omit<FlexibleGraphragConfig, 'enabledSources'>> = {
  apiUrl: '/api',
  defaultFolderPath: '/Shared/GraphRAG',
  cmisBaseUrl: 'http://localhost:8080',
  alfrescoBaseUrl: 'http://localhost:8080',
  nuxeoBaseUrl: 'http://localhost:8081/nuxeo',
  nuxeoPath: '/default-domain/workspaces/GraphRAG',
  agentIconUrl: 'assets/agent.png'
};
