// Source sign-in (planning/SOURCE-AUTH-LOGIN.md): who is asking, so the backend answers only from
// the Alfresco documents this user may read. The ticket comes from the backend's sign-in, which
// uses the same ticket API as ACA; nobody types a ticket. Kept in sessionStorage, like ACA keeps
// its own, so it is gone when the tab closes.
import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

export interface AuthProvider {
  source: string;          // 'alfresco' (others later)
  url: string;
  methods: string[];       // 'basic', 'oauth2'
  documents: number | null; // null = unknown (no incremental registry)
}

export interface AlfrescoSession {
  ticket: string;
  user_id: string;
  url: string;
}

const KEY = 'fg.sourceAuth.alfresco';
const SKIP_KEY = 'fg.sourceAuth.alfresco.skip';  // "Continue without" for this session

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

export function getAlfrescoSession(): AlfrescoSession | null {
  return read<AlfrescoSession>(KEY);
}

function setAlfrescoSession(session: AlfrescoSession | null): void {
  try {
    if (session) sessionStorage.setItem(KEY, JSON.stringify(session));
    else sessionStorage.removeItem(KEY);
  } catch { /* storage blocked: the session just isn't remembered */ }
  shownTicket = session?.ticket ?? null;
  notify();
}

// The ticket the UI currently shows. Storage can change behind the app's back (DevTools, a script
// clearing it) without any event, leaving a stale "Alfresco: <user>" chip; syncFromStorage()
// notices that and refreshes the header / form.
let shownTicket: string | null = getAlfrescoSession()?.ticket ?? null;

export function syncFromStorage(): void {
  const stored = getAlfrescoSession()?.ticket ?? null;
  if (stored !== shownTicket) {
    shownTicket = stored;
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

let requirementsCache: { at: number; value: { required: boolean; providers: AuthProvider[] } } | null = null;

export async function getRequirements(force = false): Promise<{ required: boolean; providers: AuthProvider[] }> {
  if (!force && requirementsCache && Date.now() - requirementsCache.at < 30_000) {
    return requirementsCache.value;
  }
  try {
    const { data } = await axios.get('/api/auth/requirements');
    requirementsCache = { at: Date.now(), value: data };
    return data;
  } catch {
    return { required: false, providers: [] };  // an older backend without the endpoint
  }
}

// ---- sign in / out ------------------------------------------------------------------------

export async function signIn(username: string, password: string, url?: string): Promise<AlfrescoSession> {
  const { data } = await axios.post('/api/auth/alfresco/login', { username, password, url });
  const session: AlfrescoSession = { ticket: data.ticket, user_id: data.user_id, url: data.url };
  try { sessionStorage.removeItem(SKIP_KEY); } catch { /* ignore */ }
  setAlfrescoSession(session);
  return session;
}

/** Typed a username / password into the Alfresco data-source form while not signed in: sign in
 *  with them too, so search and chat use the same identity (header shows "Alfresco: <user>").
 *  Only for basic / fetch-a-ticket credentials; never replaces an existing sign-in. Failures are
 *  ignored here -- the ingest itself reports bad credentials. */
export async function signInFromSourceConfig(cfg: any): Promise<void> {
  if (!cfg || getAlfrescoSession() || cfg.ticket) return;
  const method = (cfg.auth_method || 'basic').toLowerCase();
  if ((method !== 'basic' && method !== 'ticket') || !cfg.username?.trim() || !cfg.password) return;
  try {
    await signIn(cfg.username.trim(), cfg.password, cfg.url);
  } catch { /* the ingest will say what is wrong */ }
}

/** Forget the sign-in in this UI only. The ticket is NOT invalidated on Alfresco: Alfresco keeps
 *  one ticket per user, so deleting it would also sign the user out of ACA, KG Spaces and every
 *  other tab using it (which then fail with "Node -root- not found"). */
export async function signOut(): Promise<void> {
  setAlfrescoSession(null);
}

let lastValidated = 0;

/** Drop a stored sign-in Alfresco no longer accepts (expired, or ended by a sign-out elsewhere),
 *  so the UI shows "Sign in" instead of sending a dead ticket. At most every 30 s. */
export async function validateSession(force = false): Promise<void> {
  const session = getAlfrescoSession();
  if (!session || (!force && Date.now() - lastValidated < 30_000)) return;
  lastValidated = Date.now();
  try {
    await axios.get('/api/auth/alfresco/me', {
      params: { url: session.url },
      headers: { 'X-Alfresco-Ticket': session.ticket },
    });
  } catch (err) {
    if (axios.isAxiosError(err) && err.response?.status === 401 && getAlfrescoSession()?.ticket === session.ticket) {
      setAlfrescoSession(null);
    }
  }
}

// ---- the dialog, opened from anywhere ------------------------------------------------------

/** Why the dialog opens: before a search / chat question, or to ingest from Alfresco. */
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

// ---- axios: attach the ticket, ask for a sign-in when the stores need one ------------------

const ASK_ENDPOINTS = /\/api\/(search|query)$/;

function isAsk(config: InternalAxiosRequestConfig): boolean {
  return (config.method || 'get').toLowerCase() === 'post' && ASK_ENDPOINTS.test(config.url || '');
}

let installed = false;

export function installSourceAuth(): void {
  if (installed) return;
  installed = true;

  // A ticket kept from earlier may be dead by now: check it on load and when the tab comes back
  validateSession(true);
  window.addEventListener('focus', () => { syncFromStorage(); validateSession(); });

  axios.interceptors.request.use(async (config) => {
    if (!isAsk(config)) return config;
    syncFromStorage();
    if (!getAlfrescoSession() && !skipped()) {
      const req = await getRequirements();
      const provider = req.required ? req.providers.find((p) => p.source === 'alfresco') : undefined;
      if (provider) await openSignIn(provider);  // signed in, or chose "Continue without"
    }
    const session = getAlfrescoSession();
    if (session) {
      config.headers.set('X-Alfresco-Ticket', session.ticket);
      // which Alfresco server the ticket belongs to (several servers can be in the stores)
      config.headers.set('X-Alfresco-Url', session.url);
    }
    return config;
  });

  axios.interceptors.response.use(undefined, async (error: AxiosError) => {
    const config = error.config as (InternalAxiosRequestConfig & { _signedInAgain?: boolean }) | undefined;
    if (error.response?.status === 401 && config && isAsk(config) && !config._signedInAgain && getAlfrescoSession()) {
      // The ticket expired or was signed out elsewhere: sign in again and retry once
      setAlfrescoSession(null);
      const req = await getRequirements();
      if (await openSignIn(req.providers.find((p) => p.source === 'alfresco') || null)) {
        config._signedInAgain = true;
        return axios.request(config);
      }
    }
    return Promise.reject(error);
  });
}
