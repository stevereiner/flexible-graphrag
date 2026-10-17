import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { Subscription } from 'rxjs';
import { AlfrescoSession, AuthProvider, SignInReason, SourceAuthService } from '../../services/source-auth.service';

/**
 * Header control for the Alfresco sign-in (planning/SOURCE-AUTH-LOGIN.md): "Sign in to Alfresco"
 * when the stores hold Alfresco documents, or the signed-in user with sign-out. Renders nothing
 * when the host supplies its own ticket (KG Spaces) or sets sourceSignIn: false.
 */
@Component({
  selector: 'app-source-sign-in',
  template: `
    <ng-container *ngIf="auth.active">
      <mat-chip-set *ngIf="session; else signInButton">
        <mat-chip [title]="'Signed in to Alfresco at ' + session.url" (removed)="auth.signOut()">
          Alfresco: {{ session.user_id }}
          <button matChipRemove aria-label="Sign out of Alfresco"><mat-icon>cancel</mat-icon></button>
        </mat-chip>
      </mat-chip-set>
      <ng-template #signInButton>
        <button *ngIf="provider" mat-button class="sign-in-button" (click)="auth.promptSignIn(provider)">Sign in to Alfresco</button>
      </ng-template>
    </ng-container>
  `,
  styles: [`
    :host {
      display: inline-flex; align-items: center; margin-right: 12px;
      /* readable on a coloured toolbar: the chip takes the toolbar's text colour */
      --mat-chip-elevated-container-color: rgba(255, 255, 255, 0.18);
      --mat-chip-label-text-color: currentColor;
      --mat-chip-with-trailing-icon-trailing-icon-color: currentColor;
      --mat-chip-outline-width: 0;
      /* the "Sign in to Alfresco" button too, not the theme's primary colour */
      --mat-button-text-label-text-color: currentColor;
    }
    :host .sign-in-button { color: inherit !important; }
    :host ::ng-deep .mat-mdc-chip { background-color: rgba(255, 255, 255, 0.18) !important; }
    :host ::ng-deep .mat-mdc-chip .mdc-evolution-chip__text-label,
    :host ::ng-deep .mat-mdc-chip .mat-mdc-chip-remove { color: inherit !important; opacity: 1; }
  `],
  standalone: false
})
export class SourceSignInComponent implements OnInit, OnDestroy {
  readonly auth = inject(SourceAuthService);
  session: AlfrescoSession | null = null;
  provider: AuthProvider | null = null;
  private sub?: Subscription;

  ngOnInit(): void {
    this.sub = this.auth.session$.subscribe(async (s) => {
      this.session = s;
      this.provider = await this.auth.alfrescoProvider();
    });
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
  }
}

/** The sign-in dialog. Closes with true when signed in, false for "Continue without" / dismiss. */
@Component({
  selector: 'app-source-sign-in-dialog',
  template: `
    <h2 mat-dialog-title>Sign in to Alfresco</h2>
    <mat-dialog-content>
      <p *ngIf="reason === 'ingest'">
        Sign in to add documents from Alfresco. The same sign-in is used for search and AI chat.
      </p>
      <p *ngIf="reason !== 'ingest'">
        {{ docs ? docs + ' document(s) from Alfresco are in the stores. ' : 'The stores may hold Alfresco documents. ' }}
        Sign in to search and ask about the ones you may read.
      </p>
      <mat-form-field *ngIf="reason === 'ask' && providers.length > 1; else oneServer" appearance="outline" class="full-width">
        <mat-label>Alfresco server</mat-label>
        <mat-select [(ngModel)]="selectedUrl">
          <mat-option *ngFor="let p of providers" [value]="p.url">
            {{ p.url }}{{ p.documents != null ? ' (' + p.documents + ' document' + (p.documents === 1 ? '' : 's') + ')' : '' }}
          </mat-option>
        </mat-select>
        <mat-hint>One Alfresco sign-in at a time: documents from the other server(s) are left out</mat-hint>
      </mat-form-field>
      <ng-template #oneServer>
        <div *ngIf="provider?.url" class="url">{{ provider?.url }}</div>
      </ng-template>
      <div *ngIf="error" class="error">{{ error }}</div>
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Username</mat-label>
        <input matInput [(ngModel)]="username" autocomplete="off" cdkFocusInitial />
      </mat-form-field>
      <mat-form-field appearance="outline" class="full-width">
        <mat-label>Password</mat-label>
        <input matInput type="password" [(ngModel)]="password" autocomplete="new-password"
               (keydown.enter)="username.trim() && password && signIn()" />
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button [disabled]="busy" (click)="continueWithout()">{{ reason === 'ingest' ? 'Cancel' : 'Continue without' }}</button>
      <button mat-flat-button color="primary" [disabled]="busy || !username.trim() || !password" (click)="signIn()">
        Sign in
      </button>
    </mat-dialog-actions>
  `,
  styles: [`
    .full-width { width: 100%; }
    .url { font-size: 0.85rem; opacity: 0.8; margin-bottom: 12px; }
    .error { color: #f44336; margin-bottom: 12px; }
  `],
  standalone: false
})
export class SourceSignInDialogComponent {
  private readonly auth = inject(SourceAuthService);
  private readonly ref = inject(MatDialogRef<SourceSignInDialogComponent, boolean>);
  private readonly data = inject<{ provider: AuthProvider | null; reason?: SignInReason }>(MAT_DIALOG_DATA);
  readonly provider: AuthProvider | null = this.data?.provider ?? null;
  readonly reason: SignInReason = this.data?.reason ?? 'ask';
  // every Alfresco server with documents in the stores -- the dialog lets the user pick one
  providers: AuthProvider[] = [];
  selectedUrl = this.provider?.url ?? '';

  constructor() {
    if (this.reason === 'ask') {
      this.auth.requirements(true).then((req) => {
        this.providers = req.providers.filter((p) => p.source === 'alfresco');
        if (!this.selectedUrl && this.providers.length) this.selectedUrl = this.providers[0].url;
      });
    }
  }
  username = '';
  password = '';
  error = '';
  busy = false;

  get docs(): number | null | undefined { return this.provider?.documents; }

  async signIn(): Promise<void> {
    this.busy = true;
    this.error = '';
    try {
      await this.auth.signIn(this.username.trim(), this.password, this.selectedUrl || this.provider?.url);
      this.ref.close(true);
    } catch (err: any) {
      this.error = err?.error?.detail || 'Sign-in failed';
    } finally {
      this.busy = false;
    }
  }

  continueWithout(): void {
    if (this.reason === 'ask') this.auth.continueWithout();  // only questions remember "without"
    this.ref.close(false);
  }
}
