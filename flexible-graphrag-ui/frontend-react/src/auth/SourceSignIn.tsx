import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogContentText,
  DialogTitle, Divider, Menu, MenuItem, TextField, Typography,
} from '@mui/material';
import AccountCircleIcon from '@mui/icons-material/AccountCircle';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import axios from 'axios';
import {
  AuthProvider, Requirements, SignInReason, SourceKind, SourceSession, continueWithout, getRequirements,
  getSessions, labelOf, missingProviders, onAuthChange, providerCaption, providerTitle, providerTooltip, registerSignInDialog,
  credentialLabels, isKeySource, isPopupSource, serverKey, signIn, signInPopup, signInRows, signOut,
} from './sourceAuth';

const providerKey = (p: AuthProvider) => `${p.source}|${serverKey(p.source, p.url)}`;

/** Each repository's colour on the sign-in pill (connected); grey when offline. */
export const SOURCE_COLORS: Record<string, string> = {
  alfresco: '#7cb342', nuxeo: '#00acc1', cmis: '#ab47bc', microsoft: '#0078d4', sharepoint: '#038387', onedrive: '#0364b8',
  box: '#0061d5', google: '#4285f4', google_drive: '#1fa463', gcs: '#4285f4', azure: '#0089d6', azure_blob: '#0089d6', s3: '#ff9900',
};

// Repository sign-in for search / AI chat (planning/SOURCE-AUTH-LOGIN.md): Alfresco, Nuxeo and
// CMIS. Renders one header pill ("Sign-ins 1/2") whose menu lists every server -- signed in (its
// colour + user + Sign out) or offline (Sign in) -- and hosts the dialog that
// sourceAuth.openSignIn() opens before a question or from a data-source form. Not used in
// kg-spaces-aca, which passes ACA's own ticket.
export const SourceSignIn: React.FC = () => {
  const [sessions, setSessions] = useState<SourceSession[]>(getSessions());
  // servers with documents in the stores and no sign-in yet -- the dialog lets the user pick one
  const [missing, setMissing] = useState<AuthProvider[]>([]);
  const [requirements, setRequirements] = useState<Requirements>({ required: false, providers: [] });
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  const [dialogProvider, setDialogProvider] = useState<AuthProvider | null>(null);
  const [reason, setReason] = useState<SignInReason>('ask');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const resolver = useRef<((signedIn: boolean) => void) | null>(null);

  const refreshMissing = useCallback((force = false) =>
    getRequirements(force).then((req) => {
      const m = missingProviders(req);
      setRequirements(req);
      setMissing(m);
      return m;
    }), []);

  useEffect(() => onAuthChange(() => setSessions(getSessions())), []);
  useEffect(() => { refreshMissing(); }, [sessions, refreshMissing]);

  const finish = useCallback((signedIn: boolean) => {
    setOpen(false);
    setPassword('');
    setError('');
    resolver.current?.(signedIn);
    resolver.current = null;
  }, []);

  const show = useCallback((p: AuthProvider | null, why: SignInReason) => {
    setDialogProvider(p);
    setReason(why);
    setError('');
    setOpen(true);
  }, []);

  useEffect(() => registerSignInDialog((p, why) => {
    resolver.current?.(false);  // a dialog already open is superseded
    show(p, why);
    if (why === 'ask') refreshMissing(true);  // refresh the server list for the picker
    return new Promise<boolean>((resolve) => { resolver.current = resolve; });
  }), [show, refreshMissing]);

  const shownProvider = dialogProvider || missing[0] || null;
  const label = labelOf(shownProvider?.source || 'alfresco');

  const handleSignIn = async () => {
    if (!shownProvider) return;
    setBusy(true);
    setError('');
    try {
      await signIn(shownProvider.source as SourceKind, username.trim(), password, shownProvider.url || undefined);
      finish(true);
    } catch (err) {
      setError(axios.isAxiosError(err) ? err.response?.data?.detail || 'Sign-in failed' : 'Sign-in failed');
    } finally {
      setBusy(false);
    }
  };

  // Microsoft 365 / Box: signInPopup opens the popup synchronously, so call it first in the click
  const handlePopup = async () => {
    const signingIn = signInPopup(shownProvider!.source as SourceKind);
    setBusy(true);
    setError('');
    try {
      await signingIn;
      finish(true);
    } catch (err) {
      setError(axios.isAxiosError(err) ? err.response?.data?.detail || 'Sign-in failed' : (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleContinueWithout = () => {
    if (reason === 'ask') continueWithout();  // only questions remember "without"
    finish(false);
  };

  const docs = shownProvider?.documents;
  const isPopup = isPopupSource(shownProvider?.source);
  const rows = signInRows(requirements);
  const signedInCount = rows.filter((r) => r.session).length;
  const missingCount = missing.length;
  // short: the name before the @ (full names and servers are in the tooltip and the menu)
  const pillLabel = rows.length === 1
    ? `${providerTitle(rows[0].provider)}: ${rows[0].session ? rows[0].session.user_id.split('@')[0] : 'offline'}`
    : `Sign-ins ${signedInCount}/${rows.length}`;
  const pillTitle = rows.map((r) => `${providerTitle(r.provider)}: ${r.session ? r.session.user_id : 'offline'}`).join('\n');
  // one source per dialog (Alfresco, then Nuxeo, ...): its servers in the picker
  const servers = missing.filter((p) => p.source === shownProvider?.source);
  const picker = reason === 'ask' && servers.length > 1;

  return (
    <>
      {/* One pill for every repository sign-in; its menu lists each server, signed in or offline */}
      {rows.length > 0 && (
        <Chip
          icon={<AccountCircleIcon style={{ color: 'inherit' }} />}
          deleteIcon={<ArrowDropDownIcon style={{ color: 'inherit' }} />}
          onDelete={(e: any) => setMenuAnchor(e.currentTarget.parentElement)}
          onClick={(e) => setMenuAnchor(e.currentTarget)}
          label={pillLabel}
          title={pillTitle}
          sx={{ mr: 1, maxWidth: 240, color: 'inherit', bgcolor: signedInCount ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.1)',
                border: missingCount ? '1px dashed rgba(255,255,255,0.6)' : 'none' }}
        />
      )}
      <Menu anchorEl={menuAnchor} open={!!menuAnchor} onClose={() => setMenuAnchor(null)}>
        <Typography variant="overline" sx={{ px: 2, opacity: 0.7 }}>Repository sign-ins</Typography>
        <Divider />
        {rows.map(({ provider, session }) => (
          <MenuItem key={providerKey(provider)} disableRipple sx={{ gap: 1.5, alignItems: 'center', cursor: 'default' }}>
            <Box sx={{ width: 10, height: 10, borderRadius: '50%', flexShrink: 0,
                       bgcolor: session ? SOURCE_COLORS[provider.source] || '#66bb6a' : '#9e9e9e' }} />
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Typography variant="body2">
                <strong>{providerTitle(provider)}</strong>{' '}
                {session ? session.user_id : <em style={{ opacity: 0.7 }}>offline</em>}
              </Typography>
              <Typography variant="caption" title={providerTooltip(provider)} sx={{ opacity: 0.7, display: 'block', maxWidth: 320,
                                                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {providerCaption(provider)}
              </Typography>
            </Box>
            {session ? (
              <Button size="small" onClick={() => { signOut(session); }}>Sign out</Button>
            ) : (
              <Button size="small" variant="outlined" onClick={() => { setMenuAnchor(null); show(provider, 'ask'); }}>Sign in</Button>
            )}
          </MenuItem>
        ))}
      </Menu>

      <Dialog open={open} onClose={() => finish(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Sign in to {label}</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            {reason === 'ingest'
              ? `Sign in to add documents from ${label}. The same sign-in is used for search and AI chat.`
              : `${docs ? `${docs} document(s) from ${label} are in the stores. ` : `The stores may hold ${label} documents. `}Sign in to search and ask about the ones you may read.`}
          </DialogContentText>
          {picker ? (
            <TextField
              select fullWidth size="small" label="Server" sx={{ mb: 2 }}
              value={shownProvider ? providerKey(shownProvider) : ''}
              onChange={(e) => setDialogProvider(servers.find((p) => providerKey(p) === e.target.value) || null)}
              helperText="Sign in to each server you want answers from; the others' documents are left out"
            >
              {servers.map((p) => (
                <MenuItem key={providerKey(p)} value={providerKey(p)}>
                  {labelOf(p.source)}: {p.url}{p.documents != null ? ` (${p.documents} document${p.documents === 1 ? '' : 's'})` : ''}
                </MenuItem>
              ))}
            </TextField>
          ) : shownProvider?.url && !isKeySource(shownProvider.source) && (
            <Box sx={{ mb: 2, fontSize: '0.85rem', opacity: 0.8, wordBreak: 'break-all' }}>{shownProvider.url}</Box>
          )}
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          {isPopup ? (
            <DialogContentText variant="body2">
              Signs in at {label} in a new window (allow pop-ups for this site).
              {shownProvider?.source === 'microsoft' && ' One sign-in covers SharePoint and OneDrive.'}
              {shownProvider?.source === 'google' && ' One sign-in covers Google Drive and Cloud Storage.'}
            </DialogContentText>
          ) : (
            <>
              {isKeySource(shownProvider?.source) && (
                <DialogContentText variant="body2" sx={{ mb: 2 }}>
                  Your AWS access key is used once to start a session (12 hours by default); only that session is kept, in this browser tab.
                </DialogContentText>
              )}
              <TextField
                autoFocus fullWidth size="small" label={credentialLabels(shownProvider?.source)[0]} sx={{ mb: 2 }}
                value={username} onChange={(e) => setUsername(e.target.value)}
                autoComplete="off"
              />
              <TextField
                fullWidth size="small" label={credentialLabels(shownProvider?.source)[1]} type="password"
                value={password} onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && username.trim() && password) handleSignIn(); }}
                autoComplete="new-password"
              />
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleContinueWithout} disabled={busy}>{reason === 'ingest' ? 'Cancel' : 'Continue without'}</Button>
          {isPopup ? (
            <Button variant="contained" onClick={handlePopup} disabled={busy}>
              {busy ? `Waiting for ${label}…` : `Sign in with ${label}`}
            </Button>
          ) : (
            <Button variant="contained" onClick={handleSignIn} disabled={busy || !username.trim() || !password || !shownProvider}>
              Sign in
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </>
  );
};
