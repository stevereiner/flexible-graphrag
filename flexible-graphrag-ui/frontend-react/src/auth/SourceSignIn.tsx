import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent, DialogContentText,
  DialogTitle, MenuItem, TextField, Tooltip,
} from '@mui/material';
import axios from 'axios';
import {
  AuthProvider, AlfrescoSession, SignInReason, continueWithout, getAlfrescoSession, getRequirements,
  onAuthChange, registerSignInDialog, signIn, signOut,
} from './sourceAuth';

// Alfresco sign-in for search / AI chat (planning/SOURCE-AUTH-LOGIN.md). Renders the header
// control and hosts the dialog that sourceAuth.openSignIn() opens before a question when the
// stores hold Alfresco documents. Not used in kg-spaces-aca, which passes ACA's own ticket.
export const SourceSignIn: React.FC = () => {
  const [session, setSession] = useState<AlfrescoSession | null>(getAlfrescoSession());
  const [provider, setProvider] = useState<AuthProvider | null>(null);  // header: needed at all?
  // every Alfresco server with documents in the stores -- the dialog lets the user pick one
  const [providers, setProviders] = useState<AuthProvider[]>([]);
  const [open, setOpen] = useState(false);
  const [dialogProvider, setDialogProvider] = useState<AuthProvider | null>(null);
  const [reason, setReason] = useState<SignInReason>('ask');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const resolver = useRef<((signedIn: boolean) => void) | null>(null);

  useEffect(() => onAuthChange(() => setSession(getAlfrescoSession())), []);

  useEffect(() => {
    getRequirements().then((req) => {
      const alf = req.providers.filter((p) => p.source === 'alfresco');
      setProviders(alf);
      setProvider(alf[0] || null);
    });
  }, [session]);

  const finish = useCallback((signedIn: boolean) => {
    setOpen(false);
    setPassword('');
    setError('');
    resolver.current?.(signedIn);
    resolver.current = null;
  }, []);

  useEffect(() => registerSignInDialog((p, why) => {
    resolver.current?.(false);  // a dialog already open is superseded
    setDialogProvider(p);
    setReason(why);
    setOpen(true);
    if (why === 'ask') {  // refresh the server list for the picker
      getRequirements(true).then((req) => setProviders(req.providers.filter((x) => x.source === 'alfresco')));
    }
    return new Promise<boolean>((resolve) => { resolver.current = resolve; });
  }), []);

  const handleSignIn = async () => {
    setBusy(true);
    setError('');
    try {
      await signIn(username.trim(), password, dialogProvider?.url || provider?.url);
      finish(true);
    } catch (err) {
      setError(axios.isAxiosError(err) ? err.response?.data?.detail || 'Sign-in failed' : 'Sign-in failed');
    } finally {
      setBusy(false);
    }
  };

  const handleContinueWithout = () => {
    if (reason === 'ask') continueWithout();  // only questions remember "without"
    finish(false);
  };

  const shownProvider = dialogProvider || provider;
  const docs = shownProvider?.documents;

  return (
    <>
      {session ? (
        <Tooltip title={`Signed in to Alfresco at ${session.url}`}>
          <Chip
            label={`Alfresco: ${session.user_id}`}
            onDelete={() => { signOut(); }}
            color="default"
            sx={{ mr: 1, bgcolor: 'rgba(255,255,255,0.15)', color: 'inherit' }}
          />
        </Tooltip>
      ) : provider ? (
        <Button color="inherit" size="small" sx={{ mr: 1 }} onClick={() => { setDialogProvider(provider); setReason('ask'); setOpen(true); }}>
          Sign in to Alfresco
        </Button>
      ) : null}

      <Dialog open={open} onClose={() => finish(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Sign in to Alfresco</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            {reason === 'ingest'
              ? 'Sign in to add documents from Alfresco. The same sign-in is used for search and AI chat.'
              : `${docs ? `${docs} document(s) from Alfresco are in the stores. ` : 'The stores may hold Alfresco documents. '}Sign in to search and ask about the ones you may read.`}
          </DialogContentText>
          {reason === 'ask' && providers.length > 1 ? (
            <TextField
              select fullWidth size="small" label="Alfresco server" sx={{ mb: 2 }}
              value={shownProvider?.url || ''}
              onChange={(e) => setDialogProvider(providers.find((p) => p.url === e.target.value) || null)}
              helperText="One Alfresco sign-in at a time: documents from the other server(s) are left out"
            >
              {providers.map((p) => (
                <MenuItem key={p.url} value={p.url}>
                  {p.url}{p.documents != null ? ` (${p.documents} document${p.documents === 1 ? '' : 's'})` : ''}
                </MenuItem>
              ))}
            </TextField>
          ) : shownProvider?.url && (
            <Box sx={{ mb: 2, fontSize: '0.85rem', opacity: 0.8 }}>{shownProvider.url}</Box>
          )}
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <TextField
            autoFocus fullWidth size="small" label="Username" sx={{ mb: 2 }}
            value={username} onChange={(e) => setUsername(e.target.value)}
            autoComplete="off"
          />
          <TextField
            fullWidth size="small" label="Password" type="password"
            value={password} onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && username.trim() && password) handleSignIn(); }}
            autoComplete="new-password"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={handleContinueWithout} disabled={busy}>{reason === 'ingest' ? 'Cancel' : 'Continue without'}</Button>
          <Button variant="contained" onClick={handleSignIn} disabled={busy || !username.trim() || !password}>
            Sign in
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};
