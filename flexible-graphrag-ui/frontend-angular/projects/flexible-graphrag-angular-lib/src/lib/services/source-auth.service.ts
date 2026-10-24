import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { MatDialog } from '@angular/material/dialog';
import { BehaviorSubject, Subject, firstValueFrom } from 'rxjs';
import { map } from 'rxjs/operators';
import { FlexibleGraphragConfigService } from '../config.service';
import {
  SourceKind, SourceSelector, SourceSession, continuedWithout, credentialOf, findSession, isKeySource, isPopupSource, labelOf, readPickedSources,
  readSessions, sameServer, serverKey, setContinuedWithout, sourceKey, writePickedSources, writeSessions,
} from './source-auth.storage';

export type { AlfrescoSession, SourceKind, SourceSelector, SourceSession } from './source-auth.storage';
export { SOURCE_LABELS, POPUP_SOURCES, KEY_SOURCES, credentialLabels, isKeySource, isPopupSource, labelOf, ingestCredential, sameServer, serverKey, sourceKey } from './source-auth.storage';

/** Each repository's colour on the sign-in pill (connected) and the source picker; grey when offline. */
export const SOURCE_COLORS: Record<string, string> = {
  alfresco: '#7cb342', nuxeo: '#00acc1', cmis: '#ab47bc', microsoft: '#0078d4', sharepoint: '#038387', onedrive: '#0364b8',
  box: '#0061d5', google: '#4285f4', google_drive: '#1fa463', gcs: '#4285f4', azure: '#0089d6', azure_blob: '#0089d6', s3: '#ff9900',
};

/** A source with documents in the stores (GET /api/sources/available). */
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

export interface AuthProvider {
  source: SourceKind | string;
  label?: string;
  url: string;
  methods: string[];         // 'basic', 'oauth2'
  documents: number | null;  // null = unknown (no incremental registry)
  required?: boolean;        // its documents are hidden without this sign-in
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

/** Why the dialog opens: before a search / chat question, or to ingest from a repository. */
export type SignInReason = 'ask' | 'ingest';

export interface AuthRequirements {
  required: boolean;
  providers: AuthProvider[];
}


const fingerprint = (list: SourceSession[]) => list.map((s) => `${s.source}|${s.url}|${credentialOf(s)}`).join(',');

/**
 * Repository sign-in for search / AI chat (planning/SOURCE-AUTH-LOGIN.md): who is asking, so the
 * backend answers only from the documents this user may read. One sign-in per server -- Alfresco
 * (a ticket), Nuxeo (a token), CMIS (its vendor's ticket / token) -- from the backend's sign-in
 * endpoints; nobody types a ticket. Off when the host sets sourceSignIn: false; a server the host
 * already identifies the user on (KG Spaces passes ACA's ticket) needs no sign-in here.
 */
@Injectable({ providedIn: 'root' })
export class SourceAuthService {
  private readonly http = inject(HttpClient);
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private readonly dialog = inject(MatDialog);

  readonly sessions$ = new BehaviorSubject<SourceSession[]>(readSessions());
  /** @deprecated the first Alfresco sign-in; use sessions$ */
  readonly session$ = this.sessions$.pipe(map((list) => list.find((s) => s.source === 'alfresco') || null));
  private requirementsCache: { at: number; value: AuthRequirements } | null = null;
  private availableCache: { at: number; value: AvailableSource[] } | null = null;
  /** The stores changed (an ingest or a removal finished): the source list and sign-ins needed may have too. */
  readonly storesChanged$ = new Subject<void>();

  /** Called when a run finished: forget the cached source list and requirements, and tell whoever shows them. */
  storesChanged(): void {
    this.availableCache = null;
    this.requirementsCache = null;
    this.storesChanged$.next();
  }
  /** The source picker's choice (Search / AI Chat), shared by both; empty = all sources. */
  readonly picked$ = new BehaviorSubject<SourceSelector[]>(readPickedSources());
  private openDialog: Promise<boolean> | null = null;

  private lastValidated = 0;

  constructor() {
    // A credential kept from earlier may be dead by now: check on load and when the tab comes back
    this.validateSessions(true);
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', () => { this.syncFromStorage(); this.validateSessions(); });
    }
  }

  get active(): boolean { return this.fgConfig.sourceSignIn; }

  get sessions(): SourceSession[] { return this.sessions$.value; }

  session(source: SourceKind, url?: string): SourceSession | null {
    return findSession(source, url);
  }

  private setSessions(sessions: SourceSession[]): void {
    writeSessions(sessions);
    this.sessions$.next(sessions);
  }

  private meRequest(s: SourceSession) {
    const api = this.fgConfig.apiUrl;
    if (isPopupSource(s.source) || isKeySource(s.source)) {
      return this.http.get(`${api}/auth/${s.source}/me`, { headers: { 'X-Auth-Token': s.token || '' } });
    }
    if (s.source === 'nuxeo') {
      return this.http.get(`${api}/auth/nuxeo/me`, { params: { url: s.url }, headers: { 'X-Nuxeo-Token': s.token || '' } });
    }
    if (s.source === 'cmis') {
      return this.http.get(`${api}/auth/cmis/me`, {
        params: { url: s.url, auth_method: s.auth_method || '' }, headers: { 'X-Cmis-Credential': credentialOf(s) },
      });
    }
    return this.http.get(`${api}/auth/alfresco/me`, { params: { url: s.url }, headers: { 'X-Alfresco-Ticket': s.ticket || '' } });
  }

  /** Drop stored sign-ins their repository no longer accepts (expired, revoked, or ended by a
   *  sign-out elsewhere), so the UI shows "Sign in" instead of sending a dead credential. At most
   *  every 30 s unless forced. Returns the sessions dropped. */
  async validateSessions(force = false): Promise<SourceSession[]> {
    const sessions = readSessions();
    if (!this.active || !sessions.length || (!force && Date.now() - this.lastValidated < 30_000)) return [];
    this.lastValidated = Date.now();
    const dead: SourceSession[] = [];
    await Promise.all(sessions.map(async (s) => {
      try {
        // {valid: false} (an older backend answered 401): the repository no longer accepts it
        const res: any = await firstValueFrom(this.meRequest(s));
        if (res?.valid === false) dead.push(s);
      } catch (err: any) {
        if (err?.status === 401) dead.push(s);
      }
    }));
    // only drop what is still stored as it was (a new sign-in may have replaced it meanwhile)
    const still = dead.filter((d) => credentialOf(findSession(d.source, d.url)) === credentialOf(d));
    if (still.length) {
      const gone = new Set(still.map((d) => `${d.source}|${serverKey(d.source, d.url)}`));
      this.setSessions(readSessions().filter((s) => !gone.has(`${s.source}|${serverKey(s.source, s.url)}`)));
    }
    return still;
  }

  /** @deprecated use validateSessions */
  async validateSession(force = false): Promise<void> {
    await this.validateSessions(force);
  }

  async requirements(force = false): Promise<AuthRequirements> {
    if (!force && this.requirementsCache && Date.now() - this.requirementsCache.at < 30_000) {
      return this.requirementsCache.value;
    }
    try {
      const data = await firstValueFrom(
        this.http.get<AuthRequirements>(`${this.fgConfig.apiUrl}/auth/requirements`));
      // older backends list Alfresco only and have no per-provider "required"
      const providers = (data.providers || []).map((p) => ({ ...p, required: p.required ?? data.required }));
      const value = { required: !!data.required, providers };
      this.requirementsCache = { at: Date.now(), value };
      return value;
    } catch {
      return { required: false, providers: [] };  // an older backend without the endpoint
    }
  }

  /** The sources with documents in the stores (empty without the incremental registry). */
  async availableSources(force = false): Promise<AvailableSource[]> {
    if (!force && this.availableCache && Date.now() - this.availableCache.at < 30_000) return this.availableCache.value;
    try {
      const data = await firstValueFrom(
        this.http.get<{ available: boolean; sources: AvailableSource[] }>(`${this.fgConfig.apiUrl}/sources/available`));
      this.availableCache = { at: Date.now(), value: data.available ? data.sources : [] };
    } catch {
      this.availableCache = { at: Date.now(), value: [] };  // an older backend without the endpoint
    }
    return this.availableCache.value;
  }

  /** A login-gated source answers only once signed in to its server (unless its query auth is optional). */
  sourceNeedsSignIn(src: AvailableSource, req: AuthRequirements): boolean {
    const need = signInFor(src);
    if (!src.login_gated || this.fgConfig.hostCovers(need.source, need.url)) return false;
    // the library's own sign-ins only count where questions carry them (not in KG Spaces)
    if (this.fgConfig.searchSignIn && findSession(need.source as SourceKind, need.url || undefined)) return false;
    const p = req.providers.find((x) => x.source === need.source && sameServer(need.source, x.url, need.url));
    return p ? !!p.required : req.required;
  }

  setPicked(picked: SourceSelector[]): void {
    writePickedSources(picked);
    this.picked$.next(picked);
  }

  /** Every server the header's sign-in pill lists: the providers the stores need, plus servers
   *  signed in to from a data-source form that the stores hold nothing from yet. */
  async signInRows(force = false): Promise<{ provider: AuthProvider; session: SourceSession | null }[]> {
    const req = await this.requirements(force);
    const rows = req.providers.filter((p) => !this.fgConfig.hostCovers(p.source, p.url))
      .map((p) => ({ provider: p, session: findSession(p.source as SourceKind, p.url) }));
    for (const s of readSessions()) {
      if (!req.providers.some((p) => p.source === s.source && sameServer(s.source, p.url, s.url))) {
        rows.push({ provider: { source: s.source, url: s.url, methods: ['basic'], documents: null }, session: s });
      }
    }
    return rows;
  }

  /** Servers whose documents are hidden until the user signs in there (not those the host covers). */
  async missingProviders(force = false): Promise<AuthProvider[]> {
    if (!this.active) return [];
    const req = await this.requirements(force);
    return req.providers.filter((p) => p.required && !findSession(p.source as SourceKind, p.url)
      && !this.fgConfig.hostCovers(p.source, p.url));
  }

  /** @deprecated the first Alfresco server needing a sign-in; use missingProviders */
  async alfrescoProvider(): Promise<AuthProvider | null> {
    return (await this.missingProviders()).find((p) => p.source === 'alfresco') || null;
  }

  async signIn(source: SourceKind, username: string, password: string, url?: string): Promise<SourceSession> {
    const data = await firstValueFrom(this.http.post<any>(
      `${this.fgConfig.apiUrl}/auth/${source}/login`, { username, password, url }));
    const session: SourceSession = {
      source, url: data.url, user_id: data.user_id,
      auth_method: data.auth_method, ticket: data.ticket, token: data.token, vendor: data.vendor,
      expires_at: data.expires_at,  // s3: its session's end
    };
    setContinuedWithout(false);
    this.setSessions([...readSessions().filter((s) => !(s.source === source && sameServer(source, s.url, session.url))), session]);
    return session;
  }

  /** Popup sign-in (Microsoft 365 = SharePoint + OneDrive, Box): the vendor's own login in a
   *  popup, which the backend completes (sources/oauth_popup.py); here we only wait for the
   *  outcome. Call it straight from the click: the popup opens on a real backend URL before
   *  anything is awaited, so the browser does not block it. */
  async signInPopup(source: SourceKind): Promise<SourceSession> {
    const api = this.fgConfig.apiUrl;
    const label = labelOf(source);
    const hintKey = `fg.sourceAuth.${source}.lastUser`;
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    const state = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    // the account signed in with last time: a vendor that takes a hint (Microsoft) then picks it
    // itself, with no account picker when the browser holds several (only a hint -- no token kept)
    let hint = '';
    try { hint = localStorage.getItem(hintKey) || ''; } catch { /* ignore */ }
    const popup = window.open(`${api}/auth/${source}/popup?state=${state}${hint ? `&login_hint=${encodeURIComponent(hint)}` : ''}`,
      `fg-${source}-signin`, 'width=520,height=680');
    if (!popup) {
      throw new Error(`The browser blocked the ${label} sign-in window. Allow pop-ups for this site and try again.`);
    }
    const started = Date.now();
    let closedPolls = 0;
    while (Date.now() - started < 10 * 60_000) {
      await new Promise((r) => setTimeout(r, 1500));
      // withCredentials: the result is only released with the popup's sign-in cookie
      const r = await firstValueFrom(this.http.get<any>(`${api}/auth/${source}/result`,
        { params: { state }, observe: 'response', withCredentials: true })).catch((e) => e);
      if (r?.status === 200) {
        const session: SourceSession = {
          source, url: r.body.url, user_id: r.body.user_id, token: r.body.access_token, expires_at: r.body.expires_at,
        };
        setContinuedWithout(false);
        try { if (session.user_id) localStorage.setItem(hintKey, session.user_id); } catch { /* ignore */ }
        // the popup's own window.close() is often ignored once it has been through the vendor's pages
        try { popup.close(); } catch { /* ignore */ }
        this.setSessions([...readSessions().filter((s) => !(s.source === source && sameServer(source, s.url, session.url))), session]);
        return session;
      }
      if (r?.status !== 202) throw new Error(r?.error?.detail || `${label} sign-in failed`);
      if (popup.closed && ++closedPolls > 2) throw new Error('The sign-in window was closed before signing in.');
    }
    throw new Error(`${label} sign-in timed out.`);
  }

  /** @deprecated use signInPopup('microsoft') */
  signInMicrosoft(): Promise<SourceSession> {
    return this.signInPopup('microsoft');
  }

  /** Forget a sign-in (or all of them) in this UI only. Nothing is invalidated on the repository:
   *  Alfresco keeps one ticket per user, so deleting it would also sign the user out of ACA, KG
   *  Spaces and every other tab using it; a Nuxeo token may be stored as an Auto Sync credential. */
  async signOut(session?: SourceSession | null): Promise<void> {
    if (!session) {
      this.setSessions([]);
      return;
    }
    this.setSessions(readSessions().filter((s) => !(s.source === session.source && sameServer(s.source, s.url, session.url))));
  }

  /** Typed a username / password into a repository's data-source form while not signed in to
   *  that server: sign in with them too, so search and chat use the same identity. Only for
   *  username/password credentials; never replaces an existing sign-in. Failures are ignored
   *  here -- the ingest itself reports bad credentials. */
  async signInFromSourceConfig(source: string, cfg: any): Promise<void> {
    if (!this.active || !['alfresco', 'nuxeo', 'cmis'].includes(source) || !cfg?.url) return;
    const kind = source as SourceKind;
    if (findSession(kind, cfg.url) || cfg.ticket || cfg.token || this.fgConfig.hostCovers(kind, cfg.url)) return;
    const method = (cfg.auth_method || 'basic').toLowerCase();
    if (!['basic', 'ticket', 'token'].includes(method) || !cfg.username?.trim() || !cfg.password) return;
    try {
      await this.signIn(kind, cfg.username.trim(), cfg.password, cfg.url);
    } catch { /* the ingest will say what is wrong */ }
  }

  continueWithout(): void {
    setContinuedWithout(true);
  }

  /** Open the sign-in dialog; resolves true when the user signed in. */
  async promptSignIn(provider?: AuthProvider | null, reason: SignInReason = 'ask'): Promise<boolean> {
    if (this.openDialog) return this.openDialog;  // one dialog for concurrent questions
    const { SourceSignInDialogComponent } = await import('../components/source-sign-in/source-sign-in');
    const p = provider ?? (await this.missingProviders())[0] ?? null;
    this.openDialog = firstValueFrom(
      this.dialog.open(SourceSignInDialogComponent, { width: '460px', data: { provider: p, reason } }).afterClosed()
    ).then((signedIn) => !!signedIn).finally(() => { this.openDialog = null; });
    return this.openDialog;
  }

  /** Storage can change behind the app's back (DevTools, a script clearing it) without any event,
   *  leaving a stale chip: re-read it and refresh the header / forms. */
  syncFromStorage(): void {
    const stored = readSessions();
    if (fingerprint(stored) !== fingerprint(this.sessions$.value)) this.sessions$.next(stored);
  }

  /** Before a question: one dialog per server still missing a sign-in, until all are signed in
   *  or the user chooses "Continue without" (then the rest's documents are left out). */
  async beforeQuestion(): Promise<void> {
    this.syncFromStorage();
    // (in a host that supplies its own Alfresco ticket -- KG Spaces -- questions carry only that)
    // (only among the picked sources when the source picker names some)
    const picked = new Set(readPickedSources().map(sourceKey));
    const available = picked.size ? await this.availableSources() : [];
    // the sign-ins the picked sources need (SharePoint / OneDrive -> Microsoft 365)
    const needed = new Set(available.filter((s) => picked.has(sourceKey(s))).map((s) => sourceKey(signInFor(s))));
    for (let shown = 0; this.fgConfig.searchSignIn && !continuedWithout() && shown < 5; shown++) {
      const missing = (await this.missingProviders()).filter((p) => !picked.size || needed.has(sourceKey(p)));
      if (!missing.length || !(await this.promptSignIn(missing[0]))) break;
    }
  }

  /** A question came back 401 (a credential expired or was revoked): drop the dead sign-in(s) and
   *  sign in again. Resolves true when the caller should retry the question. */
  async afterUnauthorized(): Promise<boolean> {
    if (!this.fgConfig.searchSignIn || !readSessions().length) return false;
    const dead = await this.validateSessions(true);
    if (!dead.length) return false;
    const d = dead[0];
    if (this.fgConfig.hostCovers(d.source, d.url)) return false;
    const req = await this.requirements();
    const provider = req.providers.find((p) => p.source === d.source && sameServer(d.source, p.url, d.url))
      || { source: d.source, url: d.url, methods: ['basic'], documents: null };
    return this.promptSignIn(provider);
  }
}
