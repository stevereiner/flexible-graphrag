/**
 * One browse model for every place content can be picked from: the remote data sources through
 * the backend (POST /api/browse), as in the React UI (frontend-react/src/browser/types.ts).
 * Shaped after ADF's TreeService.getSubNodes(parentId, skipCount, maxItems).
 */
export interface BrowseItem {
  /** The source's own id: node id, object key, drive item id... */
  id: string;
  name: string;
  /** The source's own path for it, when it has one. */
  path?: string;
  isDirectory: boolean;
  size?: number;
  /** ISO 8601 */
  modified?: string;
}

export interface Listing {
  items: BrowseItem[];
  /** More items follow: pass it back to `list` for the next page. */
  nextPageToken?: string | null;
}

export interface BrowseProvider {
  /** Shown in the browser's title, e.g. "Box". */
  label: string;
  /** Names the source for the browser's memory of the folder last open in it ("local",
   *  "source:box"...). None: the browser starts at the roots each time. */
  key?: string;
  /** Where the browser starts when it remembers no folder: the folders from a root down (empty or
   *  none: the roots). */
  startTrail?(): Promise<BrowseItem[]>;
  /** The top level: drives, buckets, sites, the repository root... */
  roots(): Promise<BrowseItem[]>;
  /** One level of a folder's children, a page at a time. */
  list(folder: BrowseItem, pageToken?: string | null): Promise<Listing>;
}

/** A picked repository document / folder, as AlfrescoConfig / NuxeoConfig.nodeDetails hold it. */
export interface NodeDetail {
  id: string;
  name: string;
  path: string;
  isFile: boolean;
  isFolder: boolean;
}

export const toNodeDetail = (i: BrowseItem): NodeDetail => ({
  id: i.id,
  name: i.name,
  path: i.path || `/${i.name}`,
  isFile: !i.isDirectory,
  isFolder: i.isDirectory,
});

/** The folder that holds all of ``paths`` ("/Shared/a.pdf", "/Shared/x" -> "/Shared"). */
export function commonParent(paths: string[]): string {
  const parents = paths.map((p) => p.replace(/\/+$/, '').split('/').slice(0, -1));
  if (!parents.length) return '/';
  const first = parents[0];
  let n = first.length;
  for (const p of parents.slice(1)) {
    let i = 0;
    while (i < n && i < p.length && p[i] === first[i]) i++;
    n = i;
  }
  return first.slice(0, n).join('/') || '/';
}
