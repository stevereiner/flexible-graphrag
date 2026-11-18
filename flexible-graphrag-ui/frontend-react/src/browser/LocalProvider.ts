import { invoke } from '../desktop/tauri';
import { BrowseItem, BrowseProvider, Listing } from './types';

/** An entry as the desktop app's Rust commands return it (desktop/src-tauri/src/fs_browse.rs). */
interface FsEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number | null;
  modified_ms?: number | null;
}

const toItem = (e: FsEntry): BrowseItem => ({
  id: e.path,
  name: e.name,
  path: e.path,
  isDirectory: e.is_dir,
  size: e.is_dir ? undefined : (e.size ?? undefined),
  modified: e.modified_ms ? new Date(e.modified_ms).toISOString() : undefined,
});

/** The local disk, listed by the desktop app (never through the backend). */
export const localProvider: BrowseProvider = {
  label: 'This computer',
  key: 'local',
  async roots() {
    return (await invoke<FsEntry[]>('fs_roots')).map(toItem);
  },
  // the app folder's sample-docs/, when it has one
  async startTrail() {
    return (await invoke<FsEntry[]>('fs_start')).map(toItem);
  },
  async list(folder: BrowseItem): Promise<Listing> {
    const entries = await invoke<FsEntry[]>('fs_list_dir', { path: folder.path || folder.id });
    return { items: entries.map(toItem), nextPageToken: null };
  },
};
