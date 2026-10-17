// The library's Alfresco sign-in, as kept in sessionStorage (planning/SOURCE-AUTH-LOGIN.md). Like
// ACA keeps its own ticket: gone when the tab closes. Dependency-free so FlexibleGraphragConfigService
// can read the ticket without importing SourceAuthService (which injects it).

export interface AlfrescoSession {
  ticket: string;
  user_id: string;
  url: string;
}

const KEY = 'fg.sourceAuth.alfresco';
const SKIP_KEY = 'fg.sourceAuth.alfresco.skip';  // "Continue without" for this session

function read<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function readAlfrescoSession(): AlfrescoSession | null {
  return read<AlfrescoSession>(KEY);
}

export function writeAlfrescoSession(session: AlfrescoSession | null): void {
  try {
    if (session) sessionStorage.setItem(KEY, JSON.stringify(session));
    else sessionStorage.removeItem(KEY);
  } catch { /* storage blocked: the session just isn't remembered */ }
}

export function signedInAlfrescoTicket(): string | null {
  return readAlfrescoSession()?.ticket || null;
}

export function continuedWithout(): boolean {
  return read<boolean>(SKIP_KEY) === true;
}

export function setContinuedWithout(value: boolean): void {
  try {
    if (value) sessionStorage.setItem(SKIP_KEY, 'true');
    else sessionStorage.removeItem(SKIP_KEY);
  } catch { /* ignore */ }
}
