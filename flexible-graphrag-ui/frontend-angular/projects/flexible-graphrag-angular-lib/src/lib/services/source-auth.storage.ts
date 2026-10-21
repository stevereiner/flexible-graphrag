// The library's repository sign-ins, as kept in sessionStorage (planning/SOURCE-AUTH-LOGIN.md): one
// per server -- Alfresco (a ticket), Nuxeo (a token), CMIS (its vendor's ticket / token). Like ACA
// keeps its own ticket: gone when the tab closes. Dependency-free so FlexibleGraphragConfigService
// can read them without importing SourceAuthService (which injects it).

export type SourceKind = 'alfresco' | 'nuxeo' | 'cmis' | 'microsoft' | 'box' | 'google' | 'azure' | 's3';

/** Sign-ins done at the vendor in a popup (OAuth), not with a username / password dialog. */
export const POPUP_SOURCES = ['microsoft', 'box', 'google', 'azure'];
export const isPopupSource = (source?: string) => !!source && POPUP_SOURCES.includes(source);

/** Sign-ins with an access key rather than a username / password (Amazon S3: an IAM user's key,
 *  exchanged once for a temporary session; only that session is kept). */
export const KEY_SOURCES = ['s3'];
export const isKeySource = (source?: string) => !!source && KEY_SOURCES.includes(source);
/** The sign-in dialog's two field labels for a source. */
export const credentialLabels = (source?: string): [string, string] =>
  isKeySource(source) ? ['Access key ID', 'Secret access key'] : ['Username', 'Password'];

export const SOURCE_LABELS: Record<string, string> = {
  alfresco: 'Alfresco', nuxeo: 'Nuxeo', cmis: 'CMIS', microsoft: 'Microsoft 365', box: 'Box', google: 'Google',
  google_drive: 'Google Drive', gcs: 'Google Cloud Storage', azure: 'Azure Storage', azure_blob: 'Azure Blob', s3: 'Amazon S3',
  sharepoint: 'SharePoint', onedrive: 'OneDrive',
};
export const labelOf = (source: string) => SOURCE_LABELS[source] || source;

export interface SourceSession {
  source: SourceKind;
  url: string;
  user_id: string;
  auth_method?: string;  // cmis: 'ticket' (Alfresco server) | 'token' (Nuxeo server)
  ticket?: string;       // alfresco, cmis on Alfresco
  token?: string;        // nuxeo, cmis on Nuxeo, microsoft / box (a delegated access token)
  vendor?: string;       // cmis: 'alfresco' | 'nuxeo'
  expires_at?: number;   // microsoft / box: epoch seconds the access token expires (about an hour)
}

/** @deprecated an Alfresco session; use SourceSession */
export type AlfrescoSession = SourceSession;

const KEY = 'fg.sourceAuth.sessions';
const LEGACY_ALFRESCO_KEY = 'fg.sourceAuth.alfresco';
const SKIP_KEY = 'fg.sourceAuth.skip';  // "Continue without" for this session

function read<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

/** One spelling per server: trailing slashes, case and Alfresco's /alfresco suffix don't matter. */
export function serverKey(source: string, url: string | undefined | null): string {
  let u = (url || '').trim().replace(/\/+$/, '');
  if (source === 'alfresco') u = u.replace(/\/alfresco$/i, '');
  return u.toLowerCase();
}

export const sameServer = (source: string, a: string, b: string) => serverKey(source, a) === serverKey(source, b);

export function readSessions(): SourceSession[] {
  const sessions = read<SourceSession[]>(KEY);
  // a Microsoft / Box access token is useless once expired (~1 h): treat it as signed out
  if (sessions) return sessions.filter((s) => !s.expires_at || s.expires_at * 1000 > Date.now() + 30_000);
  const legacy = read<{ ticket: string; user_id: string; url: string }>(LEGACY_ALFRESCO_KEY);
  return legacy ? [{ source: 'alfresco', ...legacy }] : [];
}

export function writeSessions(sessions: SourceSession[]): void {
  try {
    if (sessions.length) sessionStorage.setItem(KEY, JSON.stringify(sessions));
    else sessionStorage.removeItem(KEY);
    sessionStorage.removeItem(LEGACY_ALFRESCO_KEY);
  } catch { /* storage blocked: the sessions just aren't remembered */ }
}

/** The session for a source on a server (url omitted: the first one for that source). */
export function findSession(source: SourceKind, url?: string): SourceSession | null {
  return readSessions().find((s) => s.source === source && (url === undefined || sameServer(source, s.url, url))) || null;
}

export function readAlfrescoSession(): SourceSession | null {
  return findSession('alfresco');
}

export function signedInAlfrescoTicket(): string | null {
  return readAlfrescoSession()?.ticket || null;
}

export const credentialOf = (s: SourceSession | null | undefined) => (s ? s.ticket || s.token || '' : '');

/** The signed-in identities as a question's source_auth: one list per source. `skip` leaves a
 *  session out (e.g. an Alfresco server the host already identifies the user on). */
export function sourceAuthBody(skip: (s: SourceSession) => boolean = () => false): Record<string, any[]> {
  const out: Record<string, any[]> = {};
  for (const s of readSessions()) {
    if (skip(s)) continue;
    const entry: any = { url: s.url };
    if (s.source === 'alfresco') Object.assign(entry, { auth_method: 'ticket', ticket: s.ticket });
    else if (s.source === 'nuxeo') Object.assign(entry, { auth_method: 'token', token: s.token });
    else if (s.source === 's3') Object.assign(entry, { token: s.token });
    else if (isPopupSource(s.source)) Object.assign(entry, { access_token: s.token });
    else Object.assign(entry, { auth_method: s.auth_method, ticket: s.ticket, token: s.token });
    (out[s.source] ||= []).push(entry);
  }
  return out;
}

/** The ingest config fields that make an ingest from `source` at `url` use the sign-in, or null. */
export function ingestCredential(source: SourceKind, url: string): Record<string, string> | null {
  const s = findSession(source, url);
  if (!s) return null;
  if (source === 'alfresco') return { auth_method: 'ticket', ticket: s.ticket! };
  // the username keeps the datasource id the same as a username/password ingest's
  if (source === 'nuxeo') return { auth_method: 'token', token: s.token!, username: s.user_id };
  return s.auth_method === 'ticket'
    ? { auth_method: 'ticket', ticket: s.ticket!, username: s.user_id }
    : { auth_method: 'token', token: s.token!, username: s.user_id };
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

// ---- source picker: which sources a question covers -----------------------------------------

export interface SourceSelector { source: string; url?: string | null }

export const sourceKey = (s: SourceSelector) => `${s.source}|${serverKey(s.source, s.url)}`;

const PICK_KEY = 'fg.sourcePicker';

/** The sources picked for questions; empty = all sources. */
export function readPickedSources(): SourceSelector[] {
  return read<SourceSelector[]>(PICK_KEY) || [];
}

export function writePickedSources(picked: SourceSelector[]): void {
  try {
    if (picked.length) sessionStorage.setItem(PICK_KEY, JSON.stringify(picked));
    else sessionStorage.removeItem(PICK_KEY);
  } catch { /* ignore */ }
}
