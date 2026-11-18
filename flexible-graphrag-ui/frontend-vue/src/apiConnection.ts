import axios from 'axios';
import { invoke, isTauri } from './desktop/tauri';

/**
 * Where the backend is and the API token it wants (the backend's API_TOKEN, sent as X-API-Token),
 * as in the React UI (frontend-react/src/apiConnection.ts).
 *
 * - Browser: the dev server / nginx proxies /api, so requests stay relative and nothing changes.
 *   A token, when the backend requires one, may come from VITE_API_TOKEN (it is then in the page:
 *   only for your own deployment).
 * - Desktop app: the backend URL and token come from the app (`backend_info`), and axios calls
 *   that URL itself, built or under the dev server (the dev server's /api proxy is not used, so
 *   the UI always talks to the backend the app chose).
 *
 * Every /api call in this UI goes through the default axios instance, so the interceptor covers
 * them all; the sign-in popup URL uses apiBase().
 */
interface BackendInfo {
  url: string | null;
  token: string | null;
}

let apiToken: string | null = null;
let backendUrl: string | null = null;
let remoteBackend = false;
let installed = false;

export const getApiToken = (): string | null => apiToken;

const isLocalUrl = (url: string): boolean => {
  try {
    return ['localhost', '127.0.0.1', '[::1]', '::1'].includes(new URL(url).hostname);
  } catch {
    return true;
  }
};

/** Desktop app with a backend on another machine (desktop.json backend_url): it can't read this
 *  machine's disk, so local files go in by File Upload there, not Local Files and Folders. */
export const isRemoteBackend = (): boolean => remoteBackend;

/** The backend's base URL when requests don't go through a proxy, else '' (relative /api). */
export const apiBase = (): string => backendUrl || '';

export async function installApiConnection(): Promise<void> {
  if (installed) return;
  installed = true;

  if (isTauri()) {
    try {
      const info = await invoke<BackendInfo>('backend_info');
      apiToken = info.token || null;
      remoteBackend = !!info.url && !isLocalUrl(info.url);
      // the backend the app chose, called directly, under the dev server too: its /api proxy
      // (VITE_API_PROXY_TARGET) may point at another backend than the one the app uses
      if (info.url) backendUrl = info.url.replace(/\/+$/, '');
    } catch (e) {
      console.warn('Desktop app: backend_info unavailable', e);
    }
  } else {
    apiToken = (import.meta.env.VITE_API_TOKEN as string | undefined) || null;
  }

  if (backendUrl) axios.defaults.baseURL = backendUrl;

  axios.interceptors.request.use((config) => {
    const url = config.url || '';
    const ours = url.startsWith('/api') || (!!backendUrl && url.startsWith(backendUrl));
    if (apiToken && ours) config.headers.set('X-API-Token', apiToken);
    return config;
  });
}
