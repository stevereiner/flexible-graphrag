import axios from 'axios';
import { BrowseItem, BrowseProvider, Listing } from './types';

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

const errorText = (e: any): string => e?.response?.data?.detail || e?.message || String(e);

/**
 * A data source browsed through the backend (POST /api/browse), with the form's current config:
 * the same credentials and root the ingest will use, so the browser shows what the ingest reads.
 */
export function remoteProvider(dataSource: string, label: string, getConfig: () => Record<string, any>): BrowseProvider {
  const page = async (parent: BrowseItem | null, pageToken?: string | null): Promise<Listing> => {
    try {
      const { data } = await axios.post('/api/browse', {
        data_source: dataSource,
        config: getConfig(),
        parent: parent ? { id: parent.id, path: parent.path } : null,
        page_token: pageToken || null,
      });
      return {
        items: (data.items as RemoteItem[]).map((i) => ({
          id: i.id,
          name: i.name,
          path: i.path,
          isDirectory: i.kind === 'folder',
          size: i.size ?? undefined,
          modified: i.modified ?? undefined,
        })),
        nextPageToken: data.next_page_token,
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
