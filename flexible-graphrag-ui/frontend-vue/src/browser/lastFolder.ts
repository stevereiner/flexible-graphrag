import type { BrowseItem, BrowseProvider } from './types';

/**
 * The folder last open in a source's browser, kept in this browser's localStorage per provider
 * key: the opened folders, root first (empty = the roots). The browser opens there next time when
 * its root is still among the roots and it still lists.
 */
const storageKey = (key: string) => `fg-browser-last:${key}`;

/** The remembered folders; null when none was ever kept (then the provider's start folder). */
export function loadTrail(key?: string): BrowseItem[] | null {
  if (!key) return null;
  try {
    const stored = localStorage.getItem(storageKey(key));
    if (stored === null) return null;
    const trail = JSON.parse(stored);
    return Array.isArray(trail) && trail.every((f) => f && typeof f.id === 'string' && typeof f.name === 'string')
      ? trail : null;
  } catch {
    return null;
  }
}

/** The folder to open: the remembered one, else the provider's start folder, else the roots. */
export async function startTrail(provider: BrowseProvider): Promise<BrowseItem[]> {
  const saved = loadTrail(provider.key);
  if (saved) return saved;
  try {
    return (await provider.startTrail?.()) ?? [];
  } catch {
    return [];
  }
}

export function saveTrail(key: string | undefined, trail: BrowseItem[]): void {
  if (!key) return;
  try {
    const folders = trail.map(({ id, name, path }) => ({ id, name, path, isDirectory: true }));
    localStorage.setItem(storageKey(key), JSON.stringify(folders));
  } catch { /* storage full or off: no memory */ }
}
