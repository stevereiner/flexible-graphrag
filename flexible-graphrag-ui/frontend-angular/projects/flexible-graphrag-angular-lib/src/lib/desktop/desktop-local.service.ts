import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, firstValueFrom } from 'rxjs';
import { FlexibleGraphragConfigService } from '../config.service';
import { IngestSignalService } from '../services/ingest-signal.service';
import { isDesktopRemoteBackend } from './desktop-bridge';

/** A picked local file or folder: its native path. */
export interface LocalItem {
  path: string;
  isDirectory: boolean;
}

/** The Local Files and Folders source's config: what the filesystem ingest takes. */
export interface LocalFilesConfig {
  paths: string[];
  items: LocalItem[];
}

export interface LocalRootsResult {
  ok: boolean;
  message?: string;
}

/** Folders added in the app, sent to the backend at every start (it keeps them in memory). */
const KEY = 'fg.desktop.ingestRoots';

/**
 * Desktop app only: the local files and folders picked on the Sources tab (kept here, so the
 * Processing tab's row removal and the form agree), and the folders the backend may ingest.
 * The backend refuses a filesystem ingest outside its allowed folders (uploads/, SOURCE_PATHS,
 * INGEST_ALLOWED_PATHS); the desktop app adds the picked ones at runtime with
 * PUT /api/ingest-allowed-paths, which the backend accepts only with API_TOKEN set (a backend the
 * app started). Unused outside the desktop app.
 */
@Injectable({ providedIn: 'root' })
export class DesktopLocalService {
  private readonly http = inject(HttpClient);
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private readonly items$ = new BehaviorSubject<LocalItem[]>([]);
  readonly itemChanges = this.items$.asObservable();

  get items(): LocalItem[] {
    return this.items$.value;
  }

  setItems(items: LocalItem[]): void {
    this.items$.next(items);
  }

  constructor() {
    // An ingest started (Processing tab): the list empties (picks add up, several folders, only
    // until an ingest). The run's own rows come from the configured filesystem config, so they stay.
    inject(IngestSignalService).started.subscribe(() => {
      if (this.items.length) this.setItems([]);
    });
  }

  static configOf(items: LocalItem[]): LocalFilesConfig {
    return { paths: items.map((i) => i.path), items };
  }

  getLocalRoots(): string[] {
    try {
      const v = JSON.parse(localStorage.getItem(KEY) || '[]');
      return Array.isArray(v) ? v.filter((p) => typeof p === 'string') : [];
    } catch {
      return [];
    }
  }

  /**
   * A backend the app didn't start ingests only from its own allowed folders (INGEST_ALLOWED_PATHS
   * etc.): which of `paths` are outside them. null: the backend can't say (an older one).
   */
  private async outsideAllowed(paths: string[]): Promise<{ outside: string[]; suggested: string[] } | null> {
    if (!paths.length) return { outside: [], suggested: [] };
    try {
      const res: any = await firstValueFrom(this.http.post(`${this.fgConfig.apiUrl}/ingest-allowed-paths/check`,
        { paths }));
      if (!Array.isArray(res?.outside)) return null;
      // the whole INGEST_ALLOWED_PATHS that would take them (the current list plus their folders)
      const suggested = Array.isArray(res?.ingest_allowed_paths) ? res.ingest_allowed_paths : res.outside;
      return { outside: res.outside, suggested };
    } catch {
      return null;
    }
  }

  /** Send the stored folders to the backend. `picked`: the ones just picked (to check those only). */
  async syncLocalRoots(picked?: string[]): Promise<LocalRootsResult> {
    try {
      const res: any = await firstValueFrom(this.http.put(`${this.fgConfig.apiUrl}/ingest-allowed-paths`,
        { paths: this.getLocalRoots() }));
      const rejected: string[] = res?.rejected || [];
      return rejected.length ? { ok: true, message: `Not found, left out: ${rejected.join(', ')}` } : { ok: true };
    } catch (err: any) {
      const status = err?.status;
      // 403 / 401: a backend the app didn't start (one you run yourself). Don't send people to give
      // it an API_TOKEN for the app's sake: that token would then lock out the browser UI and MCP too.
      if (status === 403) {
        // a backend on another machine (a team server) can't read this computer's disk at all
        if (isDesktopRemoteBackend()) {
          return { ok: false, message: 'This backend runs on another machine, so it can\'t read files on ' +
            'this computer: use File Upload to send them to it.' };
        }
        // it can't take folders from the app, but its own allowed folders may cover the picks
        const outside = await this.outsideAllowed(picked ?? this.getLocalRoots());
        if (outside && !outside.outside.length) return { ok: true };
        if (!outside) {
          return { ok: false, message: 'This backend ingests only from the folders in INGEST_ALLOWED_PATHS ' +
            'in its .env: to ingest from another, list it there and restart the backend.' };
        }
        const line = JSON.stringify(outside.suggested.map((p: string) => p.replace(/\\/g, '/')))
          .replace(/","/g, '", "');
        return { ok: false, message: 'Not in this backend\'s INGEST_ALLOWED_PATHS. To ingest ' +
          `${outside.outside.length > 1 ? 'these' : 'it'}, set this in the backend's .env and restart the ` +
          `backend: INGEST_ALLOWED_PATHS=${line}` };
      }
      if (status === 401) {
        return { ok: false, message: 'This backend wants an API token the app does not have: set api_token ' +
          'in desktop.json (or FLEXIBLE_GRAPHRAG_API_TOKEN) to its API_TOKEN.' };
      }
      return { ok: false, message: `Could not reach the backend: ${err?.message || err}` };
    }
  }

  private backendFolders: string[] | null = null;

  /**
   * The folders the desktop app opens result documents from (desktop/src-tauri/src/open_file.rs):
   * the ones added in the app, plus the backend's own allowed folders (its uploads/, SOURCE_PATHS,
   * INGEST_ALLOWED_PATHS) when it runs on this computer, e.g. for a file uploaded in a browser UI.
   */
  async openRoots(): Promise<string[]> {
    if (this.backendFolders === null && !isDesktopRemoteBackend()) {
      try {
        const res: any = await firstValueFrom(this.http.get(`${this.fgConfig.apiUrl}/ingest-allowed-paths`));
        this.backendFolders = Array.isArray(res?.resolved) ? res.resolved : [];
      } catch {
        // asked again next time
      }
    }
    return [...this.getLocalRoots(), ...(this.backendFolders || [])];
  }

  /** Add folders / files to the stored list and send the list to the backend. */
  async addLocalRoots(paths: string[]): Promise<LocalRootsResult> {
    const all = [...this.getLocalRoots()];
    for (const p of paths) if (!all.includes(p)) all.push(p);
    try { localStorage.setItem(KEY, JSON.stringify(all)); } catch { /* storage blocked */ }
    return this.syncLocalRoots(paths);
  }
}
