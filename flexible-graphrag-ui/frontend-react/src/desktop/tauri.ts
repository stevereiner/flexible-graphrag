/**
 * The desktop app (flexible-graphrag-ui/desktop, Tauri) runs this same React app. These helpers
 * tell the two apart and call the desktop's Rust commands; in a browser they are never used, and
 * the Tauri API is loaded only when called.
 */

/** Whether this page runs inside the desktop app. */
export const isTauri = (): boolean =>
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

/** Call one of the desktop app's commands (desktop/src-tauri/src). */
export async function invoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const { invoke: tauriInvoke } = await import('@tauri-apps/api/core');
  return tauriInvoke<T>(command, args);
}
