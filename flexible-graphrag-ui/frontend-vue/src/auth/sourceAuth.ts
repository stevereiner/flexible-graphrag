// Source sign-in (planning/SOURCE-AUTH-LOGIN.md): who is asking, so the backend answers only from
// the repository documents this user may read. One sign-in per repository server -- Alfresco
// (a ticket), Nuxeo (a token) and CMIS (the server vendor's ticket / token) -- each from the
// backend's sign-in endpoint; nobody types a ticket. Kept in sessionStorage, like ACA keeps its
// own, so they are gone when the tab closes.
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

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

export interface AuthProvider {
  source: SourceKind | string;
  label?: string;
  url: string;
  methods: string[];        // 'basic', 'oauth2'
  documents: number | null; // null = unknown (no incremental registry)
  required?: boolean;       // its documents are hidden without this sign-in
  // Microsoft 365 / Google: the services one sign-in covers, with their documents
  services?: { source: string; label: string; documents: number }[];
}

const SERVICE_ORDER = ['sharepoint', 'onedrive', 'google_drive', 'gcs'];
const services = (p: AuthProvider) => [...(p.services || [])]
  .sort((a, b) => SERVICE_ORDER.indexOf(a.source) - SERVICE_ORDER.indexOf(b.source));
const docCount = (n: number) => `${n} doc${n === 1 ? '' : 's'}`;

/** A sign-in's name: the services it covers when it has several ("SharePoint, OneDrive" for one
 *  Microsoft 365 sign-in), else the source ("Nuxeo"). */
export function providerTitle(p: AuthProvider): string {
  const names = services(p).map((s) => s.label);
  return names.length ? names.join(', ') : labelOf(p.source);
}

/** A menu row's caption: its documents first, then the server (a long CMIS URL is cut off at the
 *  end, not the counts). Microsoft 365: "SharePoint 2 docs · OneDrive 1 doc" -- its tenant id
 *  means nothing to a reader, so it is only in the tooltip (providerTooltip). */
export function providerCaption(p: AuthProvider): string {
  if (p.services?.length) return services(p).map((s) => `${s.label} ${docCount(s.documents)}`).join(' · ');
  return [p.documents != null ? docCount(p.documents) : '', p.url].filter(Boolean).join(' · ');
}

/** The menu row's tooltip: the caption plus the server it signs in to (Microsoft: the tenant). */
export function providerTooltip(p: AuthProvider): string {
  return p.services?.length ? `${providerCaption(p)} · ${labelOf(p.source)} tenant ${p.url}` : providerCaption(p);
}

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

/** @deprecated kept for older imports: an Alfresco session */
export type AlfrescoSession = SourceSession;

const KEY = 'fg.sourceAuth.sessions';
const LEGACY_ALFRESCO_KEY = 'fg.sourceAuth.alfresco';
const SKIP_KEY = 'fg.sourceAuth.skip';  // "Continue without" for this session

export const labelOf = (source: string) => SOURCE_LABELS[source] || source;

/** One spelling per server: trailing slashes, case and Alfresco's /alfresco suffix don't matter. */
export function serverKey(source: string, url: string | undefined | null): string {
  let u = (url || '').trim().replace(/\/+$/, '');
  if (source === 'alfresco') u = u.replace(/\/alfresco$/i, '');
  return u.toLowerCase();
}

export const sameServer = (source: string, a: string, b: string) => serverKey(source, a) === serverKey(source, b);

type Listener = () => void;
const listeners = new Set<Listener>();
const notify = () => listeners.forEach((l) => l());

export function onAuthChange(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function read<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

export function getSessions(): SourceSession[] {
  const sessions = read<SourceSession[]>(KEY);
  // a Microsoft / Box access token is useless once expired (~1 h): treat it as signed out
  if (sessions) return sessions.filter((s) => !s.expires_at || s.expires_at * 1000 > Date.now() + 30_000);
  const legacy = read<{ ticket: string; user_id: string; url: string }>(LEGACY_ALFRESCO_KEY);
  return legacy ? [{ source: 'alfresco', ...legacy }] : [];
}

/** The session for a source on a server (url omitted: the first one for that source). */
export function getSession(source: SourceKind, url?: string): SourceSession | null {
  return getSessions().find((s) => s.source === source && (url === undefined || sameServer(source, s.url, url))) || null;
}

export function getAlfrescoSession(): SourceSession | null {
  return getSession('alfresco');
}

const credentialOf = (s: SourceSession | null | undefined) => (s ? s.ticket || s.token || '' : '');
const fingerprint = (list: SourceSession[]) => list.map((s) => `${s.source}|${s.url}|${credentialOf(s)}`).join(',');

function setSessions(sessions: SourceSession[]): void {
  try {
    if (sessions.length) sessionStorage.setItem(KEY, JSON.stringify(sessions));
    else sessionStorage.removeItem(KEY);
    sessionStorage.removeItem(LEGACY_ALFRESCO_KEY);
  } catch { /* storage blocked: the sessions just aren't remembered */ }
  shown = fingerprint(sessions);
  notify();
}

function putSession(session: SourceSession): void {
  setSessions([...getSessions().filter((s) => !(s.source === session.source && sameServer(s.source, s.url, session.url))), session]);
}

function dropSession(session: SourceSession): void {
  setSessions(getSessions().filter((s) => !(s.source === session.source && sameServer(s.source, s.url, session.url))));
}

// The sessions the UI currently shows. Storage can change behind the app's back (DevTools, a
// script clearing it) without any event, leaving a stale chip; syncFromStorage() notices that and
// refreshes the header / forms.
let shown = fingerprint(getSessions());

export function syncFromStorage(): void {
  const now = fingerprint(getSessions());
  if (now !== shown) {
    shown = now;
    notify();
  }
}

function skipped(): boolean {
  return read<boolean>(SKIP_KEY) === true;
}

export function continueWithout(): void {
  try { sessionStorage.setItem(SKIP_KEY, 'true'); } catch { /* ignore */ }
  notify();
}

// ---- requirements -------------------------------------------------------------------------

export interface Requirements { required: boolean; providers: AuthProvider[] }
let requirementsCache: { at: number; value: Requirements } | null = null;

export async function getRequirements(force = false): Promise<Requirements> {
  if (!force && requirementsCache && Date.now() - requirementsCache.at < 30_000) {
    return requirementsCache.value;
  }
  try {
    const { data } = await axios.get('/api/auth/requirements');
    // older backends list Alfresco only and have no per-provider "required"
    const providers = (data.providers || []).map((p: AuthProvider) => ({ ...p, required: p.required ?? data.required }));
    requirementsCache = { at: Date.now(), value: { required: !!data.required, providers } };
    return requirementsCache.value;
  } catch {
    return { required: false, providers: [] };  // an older backend without the endpoint
  }
}

/** Servers whose documents are hidden until the user signs in there. */
export function missingProviders(req: Requirements): AuthProvider[] {
  return req.providers.filter((p) => p.required && !getSession(p.source as SourceKind, p.url));
}

/** Every server the header's sign-in pill lists: the providers the stores need, plus servers
 *  signed in to from a data-source form that the stores hold nothing from yet. */
export function signInRows(req: Requirements): { provider: AuthProvider; session: SourceSession | null }[] {
  const rows = req.providers.map((p) => ({ provider: p, session: getSession(p.source as SourceKind, p.url) }));
  for (const s of getSessions()) {
    if (!req.providers.some((p) => p.source === s.source && sameServer(s.source, p.url, s.url))) {
      rows.push({ provider: { source: s.source, url: s.url, methods: ['basic'], documents: null }, session: s });
    }
  }
  return rows;
}

// ---- source picker: which sources a question covers ---------------------------------------

export interface AvailableSource {
  source: string;
  label: string;
  url: string | null;
  documents: number;
  login_gated: boolean;
  auth_source?: string | null;  // the sign-in that unlocks it (SharePoint / OneDrive: 'microsoft')
  auth_url?: string | null;     // that sign-in's server (Microsoft: the tenant)
}

/** The sign-in provider a source needs: {source, url} of its auth_source (else itself). */
export function signInFor(src: AvailableSource): { source: string; url: string } {
  return { source: src.auth_source || src.source, url: (src.auth_url ?? src.url) || '' };
}

let availableCache: { at: number; value: AvailableSource[] } | null = null;

/** The sources with documents in the stores (empty without the incremental registry). */
export async function getAvailableSources(force = false): Promise<AvailableSource[]> {
  if (!force && availableCache && Date.now() - availableCache.at < 30_000) return availableCache.value;
  try {
    const { data } = await axios.get('/api/sources/available');
    availableCache = { at: Date.now(), value: data.available ? data.sources : [] };
  } catch {
    availableCache = { at: Date.now(), value: [] };  // an older backend without the endpoint
  }
  return availableCache.value;
}

/** A run changed what the stores hold: the source lists are asked again and the pickers refresh. */
export function storesChanged(): void {
  if (availableCache) availableCache.at = 0;  // stale, but still there for the request interceptor
  if (requirementsCache) requirementsCache.at = 0;
  notify();
}

export const sourceKey = (s: { source: string; url?: string | null }) => `${s.source}|${serverKey(s.source, s.url)}`;

const PICK_KEY = 'fg.sourcePicker';

/** The sources picked for questions (keys from sourceKey); empty = all sources. */
export function getPickedSources(): string[] {
  return read<string[]>(PICK_KEY) || [];
}

export function setPickedSources(keys: string[]): void {
  try {
    if (keys.length) sessionStorage.setItem(PICK_KEY, JSON.stringify(keys));
    else sessionStorage.removeItem(PICK_KEY);
  } catch { /* ignore */ }
  notify();
}

/** A login-gated source answers only once signed in to its server (unless its query auth is optional). */
export function sourceNeedsSignIn(src: AvailableSource, req: Requirements): boolean {
  const need = signInFor(src);
  if (!src.login_gated || getSession(need.source as SourceKind, need.url || undefined)) return false;
  const p = req.providers.find((x) => x.source === need.source && sameServer(need.source, x.url, need.url));
  return p ? !!p.required : req.required;
}

/** Whether a provider is needed by the picked sources (true when none are picked: all sources). */
function isPickedOrAll(p: AuthProvider): boolean {
  const picked = new Set(getPickedSources());
  if (!picked.size) return true;
  return (availableCache?.value || []).some((s) => picked.has(sourceKey(s)) && sourceKey(signInFor(s)) === sourceKey(p));
}

function pickedSelectors(): { source: string; url?: string }[] {
  const picked = new Set(getPickedSources());
  if (!picked.size || !availableCache) return [];
  return availableCache.value.filter((s) => picked.has(sourceKey(s)))
    .map((s) => (s.url ? { source: s.source, url: s.url } : { source: s.source }));
}

// ---- sign in / out ------------------------------------------------------------------------

/** Popup sign-in (Microsoft 365 = SharePoint + OneDrive, Box): the vendor's own login in a popup,
 *  which the backend completes (sources/oauth_popup.py); here we only wait for the outcome. Call
 *  it straight from the click: the popup opens on a real backend URL before anything is awaited,
 *  so the browser does not block it. */
const hintKey = (source: string) => `fg.sourceAuth.${source}.lastUser`;

export async function signInPopup(source: SourceKind): Promise<SourceSession> {
  const label = labelOf(source);
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  const state = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  // the account signed in with last time: a vendor that takes a hint (Microsoft) then picks it
  // itself, with no account picker when the browser holds several (only a hint -- no token kept)
  let hint = '';
  try { hint = localStorage.getItem(hintKey(source)) || ''; } catch { /* ignore */ }
  const popup = window.open(`/api/auth/${source}/popup?state=${state}${hint ? `&login_hint=${encodeURIComponent(hint)}` : ''}`,
    `fg-${source}-signin`, 'width=520,height=680');
  if (!popup) {
    throw new Error(`The browser blocked the ${label} sign-in window. Allow pop-ups for this site and try again.`);
  }
  const started = Date.now();
  let closedPolls = 0;
  while (Date.now() - started < 10 * 60_000) {
    await new Promise((r) => setTimeout(r, 1500));
    const r = await axios.get(`/api/auth/${source}/result`, { params: { state }, validateStatus: () => true });
    if (r.status === 200) {
      const session: SourceSession = {
        source, url: r.data.url, user_id: r.data.user_id, token: r.data.access_token, expires_at: r.data.expires_at,
      };
      try { sessionStorage.removeItem(SKIP_KEY); } catch { /* ignore */ }
      try { if (session.user_id) localStorage.setItem(hintKey(source), session.user_id); } catch { /* ignore */ }
      // the popup's own window.close() is often ignored once it has been through the vendor's pages
      try { popup.close(); } catch { /* ignore */ }
      putSession(session);
      return session;
    }
    if (r.status !== 202) throw new Error(r.data?.detail || `${label} sign-in failed`);
    if (popup.closed && ++closedPolls > 2) throw new Error('The sign-in window was closed before signing in.');
  }
  throw new Error(`${label} sign-in timed out.`);
}

/** @deprecated use signInPopup('microsoft') */
export const signInMicrosoft = () => signInPopup('microsoft');

export async function signIn(source: SourceKind, username: string, password: string, url?: string): Promise<SourceSession> {
  const { data } = await axios.post(`/api/auth/${source}/login`, { username, password, url });
  const session: SourceSession = {
    source, url: data.url, user_id: data.user_id,
    auth_method: data.auth_method, ticket: data.ticket, token: data.token, vendor: data.vendor,
    expires_at: data.expires_at,  // s3: its session's end
  };
  try { sessionStorage.removeItem(SKIP_KEY); } catch { /* ignore */ }
  putSession(session);
  return session;
}

/** Typed a username / password into a repository's data-source form while not signed in to that
 *  server: sign in with them too, so search and chat use the same identity (header shows
 *  "<Source>: <user>"). Only for username/password credentials; never replaces an existing
 *  sign-in. Failures are ignored here -- the ingest itself reports bad credentials. */
export async function signInFromSourceConfig(source: string, cfg: any): Promise<void> {
  if (!['alfresco', 'nuxeo', 'cmis'].includes(source) || !cfg?.url) return;  // (Microsoft: popup only)
  const kind = source as SourceKind;
  if (getSession(kind, cfg.url) || cfg.ticket || cfg.token) return;
  const method = (cfg.auth_method || 'basic').toLowerCase();
  if (!['basic', 'ticket', 'token'].includes(method) || !cfg.username?.trim() || !cfg.password) return;
  try {
    await signIn(kind, cfg.username.trim(), cfg.password, cfg.url);
  } catch { /* the ingest will say what is wrong */ }
}

/** Forget a sign-in (or all of them) in this UI only. Nothing is invalidated on the repository:
 *  Alfresco keeps one ticket per user, so deleting it would also sign the user out of ACA, KG
 *  Spaces and every other tab using it; a Nuxeo token may be stored as an Auto Sync credential. */
export async function signOut(session?: SourceSession | null): Promise<void> {
  if (session) dropSession(session);
  else setSessions([]);
}

function meRequest(s: SourceSession) {
  if (isPopupSource(s.source) || isKeySource(s.source)) {
    return axios.get(`/api/auth/${s.source}/me`, { headers: { 'X-Auth-Token': s.token } });
  }
  if (s.source === 'nuxeo') {
    return axios.get('/api/auth/nuxeo/me', { params: { url: s.url }, headers: { 'X-Nuxeo-Token': s.token } });
  }
  if (s.source === 'cmis') {
    return axios.get('/api/auth/cmis/me', {
      params: { url: s.url, auth_method: s.auth_method }, headers: { 'X-Cmis-Credential': credentialOf(s) },
    });
  }
  return axios.get('/api/auth/alfresco/me', { params: { url: s.url }, headers: { 'X-Alfresco-Ticket': s.ticket } });
}

let lastValidated = 0;

/** Drop stored sign-ins their repository no longer accepts (expired, revoked, or ended by a
 *  sign-out elsewhere), so the UI shows "Sign in" instead of sending a dead credential. At most
 *  every 30 s unless forced. Returns the sessions dropped. */
export async function validateSessions(force = false): Promise<SourceSession[]> {
  const sessions = getSessions();
  if (!sessions.length || (!force && Date.now() - lastValidated < 30_000)) return [];
  lastValidated = Date.now();
  const dead: SourceSession[] = [];
  await Promise.all(sessions.map(async (s) => {
    try {
      // {valid: false} (an older backend answered 401): the repository no longer accepts it
      const { data } = await meRequest(s);
      if (data?.valid === false) dead.push(s);
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 401) dead.push(s);
    }
  }));
  // only drop what is still stored as it was (a new sign-in may have replaced it meanwhile)
  const still = dead.filter((d) => credentialOf(getSession(d.source, d.url)) === credentialOf(d));
  if (still.length) {
    const gone = new Set(still.map((d) => `${d.source}|${serverKey(d.source, d.url)}`));
    setSessions(getSessions().filter((s) => !gone.has(`${s.source}|${serverKey(s.source, s.url)}`)));
  }
  return still;
}

/** @deprecated use validateSessions */
export const validateSession = (force = false) => validateSessions(force).then(() => undefined);

/** The signed-in identities as the request's source_auth: one list per source. */
export function sourceAuthBody(): Record<string, any[]> {
  const out: Record<string, any[]> = {};
  for (const s of getSessions()) {
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
  const s = getSession(source, url);
  if (!s) return null;
  if (source === 'alfresco') return { auth_method: 'ticket', ticket: s.ticket! };
  // the username keeps the datasource id the same as a username/password ingest's
  if (source === 'nuxeo') return { auth_method: 'token', token: s.token!, username: s.user_id };
  return s.auth_method === 'ticket'
    ? { auth_method: 'ticket', ticket: s.ticket!, username: s.user_id }
    : { auth_method: 'token', token: s.token!, username: s.user_id };
}

// ---- the dialog, opened from anywhere ------------------------------------------------------

/** Why the dialog opens: before a search / chat question, or to ingest from a repository. */
export type SignInReason = 'ask' | 'ingest';

type Opener = (provider: AuthProvider | null, reason: SignInReason) => Promise<boolean>;
let opener: Opener | null = null;

/** Registered by <SourceSignIn/>; resolves true when the user signed in. */
export function registerSignInDialog(open: Opener): () => void {
  opener = open;
  return () => { if (opener === open) opener = null; };
}

export function openSignIn(provider: AuthProvider | null = null, reason: SignInReason = 'ask'): Promise<boolean> {
  return opener ? opener(provider, reason) : Promise.resolve(false);
}

// ---- axios: attach the identities, ask for a sign-in when the stores need one ---------------

const ASK_ENDPOINTS = /\/api\/(search|query)$/;

function isAsk(config: InternalAxiosRequestConfig): boolean {
  return (config.method || 'get').toLowerCase() === 'post' && ASK_ENDPOINTS.test(config.url || '');
}

/** Merge the signed-in identities into the request body's source_auth (the caller's own entries
 *  come first, so an explicit credential wins for its server). */
function withSourceAuth(data: any): any {
  const mine = sourceAuthBody();
  if (!Object.keys(mine).length) return data;
  let body = data;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { return data; }
  }
  body = { ...(body || {}) };
  const given = body.source_auth || {};
  const merged: Record<string, any> = { ...given };
  for (const [source, entries] of Object.entries(mine)) {
    const theirs = given[source] ? (Array.isArray(given[source]) ? given[source] : [given[source]]) : [];
    merged[source] = [...theirs, ...entries];
  }
  body.source_auth = merged;
  return body;
}

let installed = false;

export function installSourceAuth(): void {
  if (installed) return;
  installed = true;

  // A credential kept from earlier may be dead by now: check on load and when the tab comes back
  validateSessions(true);
  window.addEventListener('focus', () => { syncFromStorage(); validateSessions(); });

  axios.interceptors.request.use(async (config) => {
    if (!isAsk(config)) return config;
    syncFromStorage();
    // One dialog per server still missing a sign-in, until all are signed in or the user
    // chooses "Continue without" (then the rest's documents are left out)
    // (only among the picked sources when the source picker names some)
    for (let shownCount = 0; !skipped() && shownCount < 5; shownCount++) {
      const missing = missingProviders(await getRequirements()).filter(isPickedOrAll);
      if (!missing.length || !(await openSignIn(missing[0]))) break;
    }
    config.data = withSourceAuth(config.data);
    // the source picker's choice (Search / AI Chat), unless the caller chose its own
    const selectors = pickedSelectors();
    if (selectors.length && config.data && typeof config.data === 'object' && !config.data.sources) {
      config.data = { ...config.data, sources: selectors };
    }
    return config;
  });

  axios.interceptors.response.use(undefined, async (error: AxiosError) => {
    const config = error.config as (InternalAxiosRequestConfig & { _signedInAgain?: boolean }) | undefined;
    if (error.response?.status === 401 && config && isAsk(config) && !config._signedInAgain && getSessions().length) {
      // A credential expired or was revoked: drop the dead one(s), sign in again and retry once
      const dead = await validateSessions(true);
      if (dead.length) {
        const req = await getRequirements();
        const d = dead[0];
        const provider = req.providers.find((p) => p.source === d.source && sameServer(d.source, p.url, d.url))
          || { source: d.source, url: d.url, methods: ['basic'], documents: null };
        if (await openSignIn(provider)) {
          config._signedInAgain = true;
          // the body still carries the dead credential: rebuild it from the current sessions
          const body = typeof config.data === 'string' ? JSON.parse(config.data) : { ...(config.data || {}) };
          delete body.source_auth;
          config.data = body;
          return axios.request(config);
        }
      }
    }
    return Promise.reject(error);
  });
}
