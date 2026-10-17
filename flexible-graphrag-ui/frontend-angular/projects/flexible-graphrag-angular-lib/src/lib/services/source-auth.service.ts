import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { MatDialog } from '@angular/material/dialog';
import { BehaviorSubject, firstValueFrom } from 'rxjs';
import { FlexibleGraphragConfigService } from '../config.service';
import {
  AlfrescoSession, continuedWithout, readAlfrescoSession, setContinuedWithout, writeAlfrescoSession,
} from './source-auth.storage';

export type { AlfrescoSession } from './source-auth.storage';

export interface AuthProvider {
  source: string;            // 'alfresco' (others later)
  url: string;
  methods: string[];         // 'basic', 'oauth2'
  documents: number | null;  // null = unknown (no incremental registry)
}

/** Why the dialog opens: before a search / chat question, or to ingest from Alfresco. */
export type SignInReason = 'ask' | 'ingest';

export interface AuthRequirements {
  required: boolean;
  providers: AuthProvider[];
}

/**
 * Alfresco sign-in for search / AI chat (planning/SOURCE-AUTH-LOGIN.md): who is asking, so the
 * backend answers only from the Alfresco documents this user may read. The ticket comes from the
 * backend's sign-in, which uses the same ticket API as ACA; nobody types a ticket. Inactive when
 * the host supplies its own ticket (KG Spaces) or sets sourceSignIn: false.
 */
@Injectable({ providedIn: 'root' })
export class SourceAuthService {
  private readonly http = inject(HttpClient);
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private readonly dialog = inject(MatDialog);

  readonly session$ = new BehaviorSubject<AlfrescoSession | null>(readAlfrescoSession());
  private requirementsCache: { at: number; value: AuthRequirements } | null = null;
  private openDialog: Promise<boolean> | null = null;

  private lastValidated = 0;

  constructor() {
    // A ticket kept from earlier may be dead by now: check it on load and when the tab comes back
    this.validateSession(true);
    if (typeof window !== 'undefined') {
      window.addEventListener('focus', () => { this.syncFromStorage(); this.validateSession(); });
    }
  }

  get active(): boolean { return this.fgConfig.sourceSignIn; }

  /** Drop a stored sign-in Alfresco no longer accepts (expired, or ended by a sign-out
   *  elsewhere), so the UI shows "Sign in" instead of sending a dead ticket. At most every 30 s. */
  async validateSession(force = false): Promise<void> {
    const session = readAlfrescoSession();
    if (!this.active || !session || (!force && Date.now() - this.lastValidated < 30_000)) return;
    this.lastValidated = Date.now();
    try {
      await firstValueFrom(this.http.get(`${this.fgConfig.apiUrl}/auth/alfresco/me`, {
        params: { url: session.url },
        headers: { 'X-Alfresco-Ticket': session.ticket },
      }));
    } catch (err: any) {
      if (err?.status === 401 && readAlfrescoSession()?.ticket === session.ticket) {
        writeAlfrescoSession(null);
        this.session$.next(null);
      }
    }
  }

  async requirements(force = false): Promise<AuthRequirements> {
    if (!force && this.requirementsCache && Date.now() - this.requirementsCache.at < 30_000) {
      return this.requirementsCache.value;
    }
    try {
      const value = await firstValueFrom(
        this.http.get<AuthRequirements>(`${this.fgConfig.apiUrl}/auth/requirements`));
      this.requirementsCache = { at: Date.now(), value };
      return value;
    } catch {
      return { required: false, providers: [] };  // an older backend without the endpoint
    }
  }

  async alfrescoProvider(): Promise<AuthProvider | null> {
    if (!this.active) return null;
    const req = await this.requirements();
    return req.providers.find((p) => p.source === 'alfresco') || null;
  }

  async signIn(username: string, password: string, url?: string): Promise<AlfrescoSession> {
    const data = await firstValueFrom(this.http.post<AlfrescoSession>(
      `${this.fgConfig.apiUrl}/auth/alfresco/login`, { username, password, url }));
    const session: AlfrescoSession = { ticket: data.ticket, user_id: data.user_id, url: data.url };
    setContinuedWithout(false);
    writeAlfrescoSession(session);
    this.session$.next(session);
    return session;
  }

  /** Forget the sign-in in this UI only. The ticket is NOT invalidated on Alfresco: Alfresco keeps
   *  one ticket per user, so deleting it would also sign the user out of ACA, KG Spaces and every
   *  other tab using it (which then fail with "Node -root- not found"). */
  async signOut(): Promise<void> {
    writeAlfrescoSession(null);
    this.session$.next(null);
  }

  /** Typed a username / password into the Alfresco data-source form while not signed in: sign in
   *  with them too, so search and chat use the same identity (header shows "Alfresco: <user>").
   *  Only for basic / fetch-a-ticket credentials; never replaces an existing sign-in. Failures
   *  are ignored here -- the ingest itself reports bad credentials. */
  async signInFromSourceConfig(cfg: any): Promise<void> {
    if (!this.active || !cfg || readAlfrescoSession() || cfg.ticket) return;
    const method = (cfg.auth_method || 'basic').toLowerCase();
    if ((method !== 'basic' && method !== 'ticket') || !cfg.username?.trim() || !cfg.password) return;
    try {
      await this.signIn(cfg.username.trim(), cfg.password, cfg.url);
    } catch { /* the ingest will say what is wrong */ }
  }

  continueWithout(): void {
    setContinuedWithout(true);
  }

  /** Open the sign-in dialog; resolves true when the user signed in. */
  async promptSignIn(provider?: AuthProvider | null, reason: SignInReason = 'ask'): Promise<boolean> {
    if (this.openDialog) return this.openDialog;  // one dialog for concurrent questions
    const { SourceSignInDialogComponent } = await import('../components/source-sign-in/source-sign-in');
    const p = provider ?? await this.alfrescoProvider();
    this.openDialog = firstValueFrom(
      this.dialog.open(SourceSignInDialogComponent, { width: '420px', data: { provider: p, reason } }).afterClosed()
    ).then((signedIn) => !!signedIn).finally(() => { this.openDialog = null; });
    return this.openDialog;
  }

  /** Before a question: ask for a sign-in when the stores need one and the user has none yet. */
  /** Storage can change behind the app's back (DevTools, a script clearing it) without any event,
   *  leaving a stale "Alfresco: <user>" chip: re-read it and refresh the header / form. */
  syncFromStorage(): void {
    const stored = readAlfrescoSession();
    if ((stored?.ticket ?? null) !== (this.session$.value?.ticket ?? null)) this.session$.next(stored);
  }

  async beforeQuestion(): Promise<void> {
    this.syncFromStorage();
    if (!this.active || readAlfrescoSession() || continuedWithout()) return;
    const req = await this.requirements();
    const provider = req.required ? req.providers.find((p) => p.source === 'alfresco') : undefined;
    if (provider) await this.promptSignIn(provider);
  }

  /** A question came back 401 with our ticket (expired / signed out elsewhere): sign in again.
   *  Resolves true when the caller should retry the question. */
  async afterUnauthorized(): Promise<boolean> {
    if (!this.active || !readAlfrescoSession()) return false;
    writeAlfrescoSession(null);
    this.session$.next(null);
    return this.promptSignIn();
  }
}
