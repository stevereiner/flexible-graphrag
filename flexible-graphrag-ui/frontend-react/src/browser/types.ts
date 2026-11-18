/**
 * One browse model for every place content can be picked from: the local disk (desktop app), and
 * later the remote data sources through the backend (POST /api/browse) and the OpenArch mirror.
 * Shaped after ADF's TreeService.getSubNodes(parentId, skipCount, maxItems) so a provider can
 * also back an ADF tree later.
 */
export interface BrowseItem {
  /** The source's own id: a native path (local disk), node id, object key... */
  id: string;
  name: string;
  /** The source's own path for it (native path on the local disk), when it has one. */
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
  /** Shown in the browser's title, e.g. "This computer". */
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
