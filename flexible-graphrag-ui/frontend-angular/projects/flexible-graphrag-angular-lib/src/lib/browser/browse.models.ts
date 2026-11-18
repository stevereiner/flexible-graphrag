/**
 * One browse model for every place content can be picked from: the remote data sources through
 * the backend (POST /api/browse), and later the local disk and the OpenArch mirror. Shaped after
 * ADF's TreeService.getSubNodes(parentId, skipCount, maxItems), so a provider can also back an
 * adf-tree later (in an app that has ADF; this library does not depend on it).
 */
export interface BrowseItem {
  /** The source's own id: node id, object key, prefix... */
  id: string;
  name: string;
  /** The source's own path for it, when it has one (what path-based configs take). */
  path?: string;
  isDirectory: boolean;
  size?: number;
  /** ISO 8601 */
  modified?: string;
}

export interface BrowseListing {
  items: BrowseItem[];
  /** More items follow: pass it back to `list` for the next page. */
  nextPageToken?: string | null;
}

export interface BrowseProvider {
  /** Shown in the browser's title and breadcrumb, e.g. "S3 bucket". */
  label: string;
  /** Names the source for the browser's memory of the folder last open in it ("local",
   *  "source:box"...). None: the browser starts at the roots each time. */
  key?: string;
  /** Where the browser starts when it remembers no folder: the folders from a root down (empty or
   *  none: the roots). */
  startTrail?(): Promise<BrowseItem[]>;
  /** The top level: the repository root, the bucket, the drive... */
  roots(): Promise<BrowseItem[]>;
  /** One level of a folder's children, a page at a time. */
  list(folder: BrowseItem, pageToken?: string | null): Promise<BrowseListing>;
}

/**
 * The folder last open in a source's browser, kept in localStorage per provider key: the opened
 * folders, root first (empty = the roots). The browser opens there next time when its root is
 * still among the roots and it still lists.
 */
const trailStorageKey = (key: string) => `fg-browser-last:${key}`;

/** The remembered folders; null when none was ever kept (then the provider's start folder). */
export function loadBrowseTrail(key?: string): BrowseItem[] | null {
  if (!key) return null;
  try {
    const stored = localStorage.getItem(trailStorageKey(key));
    if (stored === null) return null;
    const trail = JSON.parse(stored);
    return Array.isArray(trail) && trail.every((f) => f && typeof f.id === 'string' && typeof f.name === 'string')
      ? trail : null;
  } catch {
    return null;
  }
}

/** The folder to open: the remembered one, else the provider's start folder, else the roots. */
export async function browseStartTrail(provider: BrowseProvider): Promise<BrowseItem[]> {
  const saved = loadBrowseTrail(provider.key);
  if (saved) return saved;
  try {
    return (await provider.startTrail?.()) ?? [];
  } catch {
    return [];
  }
}

export function saveBrowseTrail(key: string | undefined, trail: BrowseItem[]): void {
  if (!key) return;
  try {
    const folders = trail.map(({ id, name, path }) => ({ id, name, path, isDirectory: true }));
    localStorage.setItem(trailStorageKey(key), JSON.stringify(folders));
  } catch { /* storage full or off: no memory */ }
}

/** What the source's config can hold, as SourceBrowserDialogComponent's data. */
export interface SourceBrowserData {
  provider: BrowseProvider;
  title?: string;
  /** Files too (default yes). */
  files?: boolean;
  /** Several items (default yes). */
  multiple?: boolean;
  /** Folders and files together (default yes; no = one folder, or files only: OneDrive folder_path
   *  / file_ids). files + multiple=false: one folder or one file (CMIS folder_path, S3 prefix). */
  mixed?: boolean;
}

/** Alfresco / Nuxeo nodeDetails entry, as their configs (and ACA's multi-select) hold it. */
export interface BrowsedNodeDetail {
  id: string;
  name: string;
  path: string;
  isFile: boolean;
  isFolder: boolean;
}

/** nodeDetails for picked items. */
export function toNodeDetails(items: BrowseItem[]): BrowsedNodeDetail[] {
  return items.map((i) => ({
    id: i.id, name: i.name, path: i.path || `/${i.name}`, isFile: !i.isDirectory, isFolder: i.isDirectory,
  }));
}

/** The folder that holds every one of these paths ("/" when they share none). */
export function commonParentPath(paths: string[]): string {
  const parents = paths.map((p) => {
    const parts = p.split('/').filter(Boolean);
    return parts.slice(0, -1);
  });
  if (!parents.length) return '/';
  const first = parents[0];
  let n = first.length;
  for (const p of parents.slice(1)) {
    let i = 0;
    while (i < n && i < p.length && p[i] === first[i]) i++;
    n = i;
  }
  return '/' + first.slice(0, n).join('/');
}
