import axios from 'axios';
import { isRemoteBackend } from '../apiConnection';

/**
 * The local folders (and files) the user has added in the desktop app. The backend refuses a
 * filesystem ingest outside its allowed folders (uploads/, SOURCE_PATHS, INGEST_ALLOWED_PATHS);
 * the desktop app adds these at runtime with PUT /api/ingest-allowed-paths, which the backend
 * accepts only with API_TOKEN set. Kept here (localStorage) and sent again at every start, since
 * the backend keeps them in memory.
 */
const KEY = 'fg.desktop.ingestRoots';

export const getLocalRoots = (): string[] => {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) || '[]');
    return Array.isArray(v) ? v.filter((p) => typeof p === 'string') : [];
  } catch {
    return [];
  }
};

export interface RootsResult {
  ok: boolean;
  message?: string;
}

const REMOTE_MESSAGE = 'This backend runs on another machine, so it can\'t read files on this ' +
  'computer: use File Upload to send them to it.';

/** The message for picks a backend won't ingest from (it takes only its own allowed folders). */
const outsideMessage = ({ outside, suggested }: Outside): string =>
  `Not in this backend's INGEST_ALLOWED_PATHS. To ingest ${outside.length > 1 ? 'these' : 'it'}, ` +
  'set this in the backend\'s .env and restart the backend: INGEST_ALLOWED_PATHS=' +
  JSON.stringify(suggested.map((p) => p.replace(/\\/g, '/'))).replace(/","/g, '", "');

/** The picks outside a backend's allowed folders, and the INGEST_ALLOWED_PATHS that would take them. */
interface Outside {
  outside: string[];
  suggested: string[];
}

/**
 * A backend the app didn't start ingests only from its own allowed folders (INGEST_ALLOWED_PATHS
 * etc.): which of `paths` are outside them. null: the backend can't say (an older one).
 */
async function outsideAllowed(paths: string[]): Promise<Outside | null> {
  if (!paths.length) return { outside: [], suggested: [] };
  try {
    const res = await axios.post('/api/ingest-allowed-paths/check', { paths });
    const outside = res.data?.outside;
    if (!Array.isArray(outside)) return null;
    const suggested = res.data?.ingest_allowed_paths;
    return { outside, suggested: Array.isArray(suggested) ? suggested : outside };
  } catch {
    return null;
  }
}

/** Send the stored folders to the backend. `picked`: the ones just picked (to check those only). */
export async function syncLocalRoots(picked?: string[]): Promise<RootsResult> {
  try {
    const res = await axios.put('/api/ingest-allowed-paths', { paths: getLocalRoots() });
    const rejected: string[] = res.data?.rejected || [];
    return rejected.length
      ? { ok: true, message: `Not found, left out: ${rejected.join(', ')}` }
      : { ok: true };
  } catch (err: any) {
    const status = err?.response?.status;
    // 403 / 401: a backend the app didn't start (one you run yourself). Don't send people to give it
    // an API_TOKEN for the app's sake: that token would then lock out the browser UI and MCP too.
    if (status === 403) {
      // a backend on another machine (a team server) can't read this computer's disk at all
      if (isRemoteBackend()) return { ok: false, message: REMOTE_MESSAGE };
      // it can't take folders from the app, but its own allowed folders may cover the picks
      const outside = await outsideAllowed(picked ?? getLocalRoots());
      if (outside && !outside.outside.length) return { ok: true };
      return { ok: false, message: outside ? outsideMessage(outside) : 'This backend ingests only from ' +
        'the folders in INGEST_ALLOWED_PATHS in its .env: to ingest from another, list it there and ' +
        'restart the backend.' };
    }
    if (status === 401) {
      return { ok: false, message: 'This backend wants an API token the app does not have: set api_token ' +
        'in desktop.json (or FLEXIBLE_GRAPHRAG_API_TOKEN) to its API_TOKEN.' };
    }
    return { ok: false, message: `Could not reach the backend: ${err?.message || err}` };
  }
}

let backendFolders: string[] | null = null;

/**
 * The folders the desktop app opens result documents from (desktop/src-tauri/src/open_file.rs):
 * the ones added in the app, plus the backend's own allowed folders (its uploads/, SOURCE_PATHS,
 * INGEST_ALLOWED_PATHS) when it runs on this computer, e.g. for a file uploaded in a browser UI.
 */
export async function openRoots(): Promise<string[]> {
  if (backendFolders === null && !isRemoteBackend()) {
    try {
      const res = await axios.get('/api/ingest-allowed-paths');
      backendFolders = Array.isArray(res.data?.resolved) ? res.data.resolved : [];
    } catch {
      // asked again next time
    }
  }
  return [...getLocalRoots(), ...(backendFolders || [])];
}

/** Add folders / files to the stored list and send the list to the backend. */
export async function addLocalRoots(paths: string[]): Promise<RootsResult> {
  const all = [...getLocalRoots()];
  for (const p of paths) if (!all.includes(p)) all.push(p);
  localStorage.setItem(KEY, JSON.stringify(all));
  return syncLocalRoots(paths);
}
