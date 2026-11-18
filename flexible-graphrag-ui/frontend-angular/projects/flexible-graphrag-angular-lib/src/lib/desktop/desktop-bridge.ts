/**
 * The desktop app (flexible-graphrag-ui/desktop, Tauri) can run the Angular UI. These helpers tell
 * it apart from a browser and call the desktop's Rust commands (desktop/src-tauri/src). Outside
 * the desktop app they are never used, and the library has no dependency for them: a host app
 * that has @tauri-apps/api can register its `invoke` with setDesktopInvoke(); otherwise the
 * Tauri global it wraps (`__TAURI_INTERNALS__.invoke`) is called directly.
 */
export type DesktopInvoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

let registered: DesktopInvoke | null = null;

/** Whether this page runs inside the desktop app. */
export const isDesktopApp = (): boolean =>
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

/** Use this function for desktop commands (the fg app passes @tauri-apps/api's `invoke`). */
export function setDesktopInvoke(fn: DesktopInvoke | null): void {
  registered = fn;
}

/** Call one of the desktop app's commands. */
export async function desktopInvoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  if (registered) return registered<T>(command, args);
  const internals = (window as any).__TAURI_INTERNALS__;
  if (!internals?.invoke) throw new Error('Not running in the desktop app');
  return internals.invoke(command, args ?? {}) as Promise<T>;
}

let remoteBackend = false;

/** The desktop app sets this from its backend's URL: a backend on another machine
 *  (desktop.json backend_url) can't read this machine's disk, so local files go in by File Upload
 *  there, not Local Files and Folders. */
export function setDesktopRemoteBackend(remote: boolean): void {
  remoteBackend = remote;
}

/** Desktop app with a backend on another machine. */
export const isDesktopRemoteBackend = (): boolean => remoteBackend;

/** A local file's path (Windows drive or UNC path, or a Unix path): the desktop app can open it. */
export const isLocalPath = (p?: string | null): boolean =>
  !!p && (/^[A-Za-z]:[\\/]/.test(p) || p.startsWith('\\\\') || p.startsWith('/'));
