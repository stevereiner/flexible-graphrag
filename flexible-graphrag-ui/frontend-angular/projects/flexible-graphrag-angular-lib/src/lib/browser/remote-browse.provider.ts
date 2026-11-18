import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { MatDialog } from '@angular/material/dialog';
import { FlexibleGraphragConfigService } from '../config.service';
import { BrowseItem, BrowseListing, BrowseProvider, SourceBrowserData } from './browse.models';
import { SourceBrowserDialogComponent } from './source-browser-dialog.component';

/** backend browse/ BrowseItem */
interface RemoteItem {
  id: string;
  name: string;
  path: string;
  kind: 'folder' | 'file';
  size?: number | null;
  modified?: string | null;
}

const MAX_ROOT_PAGES = 50;

const errorText = (e: any): string => {
  if (e instanceof HttpErrorResponse) {
    const detail = e.error?.detail;
    return typeof detail === 'string' ? detail : e.message;
  }
  return e?.message || String(e);
};

/**
 * A data source browsed through the backend (POST {apiUrl}/browse), with the form's current
 * config: the same credentials and root the ingest will use, so the browser shows what the ingest
 * reads. The request goes through the host's HttpClient, so its interceptors (ADF's ticket in
 * KG Spaces, an API token) apply as on every other call this library makes.
 */
export function remoteBrowseProvider(http: HttpClient, apiUrl: string, dataSource: string, label: string,
                                     getConfig: () => Record<string, any>): BrowseProvider {
  const page = async (parent: BrowseItem | null, pageToken?: string | null): Promise<BrowseListing> => {
    try {
      const data: any = await firstValueFrom(http.post(`${apiUrl}/browse`, {
        data_source: dataSource,
        config: getConfig(),
        parent: parent ? { id: parent.id, path: parent.path } : null,
        page_token: pageToken || null,
      }));
      return {
        items: ((data?.items || []) as RemoteItem[]).map((i) => ({
          id: i.id,
          name: i.name,
          path: i.path,
          isDirectory: i.kind === 'folder',
          size: i.size ?? undefined,
          modified: i.modified ?? undefined,
        })),
        nextPageToken: data?.next_page_token,
      };
    } catch (e) {
      throw new Error(errorText(e));
    }
  };

  return {
    label,
    key: `source:${dataSource}`,
    async roots() {
      const items: BrowseItem[] = [];
      let token: string | null | undefined = null;
      for (let i = 0; i < MAX_ROOT_PAGES; i++) {
        const listing = await page(null, token);
        items.push(...listing.items);
        token = listing.nextPageToken;
        if (!token) break;
      }
      return items;
    },
    list: (folder, pageToken) => page(folder, pageToken),
  };
}

/** Remote providers on the library's API URL, and the browser dialog. */
@Injectable({ providedIn: 'root' })
export class SourceBrowserService {
  private readonly http = inject(HttpClient);
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private readonly dialog = inject(MatDialog);

  /** A provider for `dataSource` (POST /api/browse), reading the form's config at each request. */
  provider(dataSource: string, label: string, getConfig: () => Record<string, any>): BrowseProvider {
    return remoteBrowseProvider(this.http, this.fgConfig.apiUrl, dataSource, label, getConfig);
  }

  /** Open the browser; resolves with the picked items, or [] when cancelled. */
  pick(data: SourceBrowserData): Promise<BrowseItem[]> {
    const ref = this.dialog.open(SourceBrowserDialogComponent, {
      data, width: '960px', maxWidth: '95vw', autoFocus: false,
    });
    return firstValueFrom(ref.afterClosed()).then((items) => items || []);
  }
}
