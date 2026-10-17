import React, { useEffect, useMemo, useState } from 'react';
import { TextField, Box, FormControl, InputLabel, Select, MenuItem, Button, Typography, FormControlLabel, Checkbox } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { AlfrescoSession, getAlfrescoSession, onAuthChange, openSignIn, signOut, validateSession } from '../../auth/sourceAuth';

type AuthMethod = 'basic' | 'ticket' | 'oauth2';

// Same Alfresco server? (an /alfresco suffix and trailing slashes don't matter)
const sameServer = (a: string, b: string) =>
  a.trim().replace(/\/+$/, '').replace(/\/alfresco$/i, '').toLowerCase() ===
  b.trim().replace(/\/+$/, '').replace(/\/alfresco$/i, '').toLowerCase();

interface AlfrescoSourceFormProps extends BaseSourceFormProps {
  // Single-object persistence (see NuxeoSourceForm): seeds on mount, emits full config on edit,
  // so state survives Sources<->Processing tab switches (the Sources TabPanel unmounts).
  value?: any;
  onChange?: (config: any) => void;
}

// Self-contained form: manages its own state and emits a complete Alfresco config object
// (matching the backend AlfrescoConfig model) with a basic / ticket / oauth2 auth switch.
export const AlfrescoSourceForm: React.FC<AlfrescoSourceFormProps> = ({
  value,
  onChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const defaultUrl = useMemo(
    () => import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080',
    []
  );
  // VITE_ALFRESCO_PATH, not VITE_PROCESS_FOLDER_PATH: the latter is the LOCAL
  // filesystem folder for the Process Folder feature (a Windows path),
  // so reusing it here put a Windows path in an Alfresco repository field and the
  // '/Shared/GraphRAG' fallback never applied.
  const defaultPath = useMemo(
    () => import.meta.env.VITE_ALFRESCO_PATH || '/Shared/GraphRAG',
    []
  );

  const [url, setUrl] = useState<string>(value?.url ?? defaultUrl);
  const [authMethod, setAuthMethod] = useState<AuthMethod>(value?.auth_method ?? 'basic');
  const [path, setPath] = useState<string>(value?.path ?? defaultPath);

  // Basic / ticket auth
  // No pre-filled credentials (they were admin/admin): sign in, or type a username/password
  const [username, setUsername] = useState<string>(value?.username ?? '');
  const [password, setPassword] = useState<string>(value?.password ?? '');

  // The Alfresco sign-in (header / dialog, planning/SOURCE-AUTH-LOGIN.md). When signed in to this
  // server, the ingest uses that session's ticket -- nobody types a ticket. "Use other
  // credentials" falls back to the fields below (e.g. a service account for Auto Sync, which
  // needs durable credentials, never a ticket).
  const [session, setSession] = useState<AlfrescoSession | null>(getAlfrescoSession());
  const [useOther, setUseOther] = useState<boolean>(false);
  useEffect(() => onAuthChange(() => setSession(getAlfrescoSession())), []);
  useEffect(() => { validateSession(true); }, []);  // a kept ticket may be dead by now
  const signedInHere = !!session && sameServer(session.url, url);
  const usingSignIn = signedInHere && !useOther;

  // OAuth2
  const [clientId, setClientId] = useState<string>(value?.oauth2?.client_id ?? '');
  const [clientSecret, setClientSecret] = useState<string>(value?.oauth2?.client_secret ?? '');
  const [tokenEndpoint, setTokenEndpoint] = useState<string>(value?.oauth2?.token_endpoint ?? '');
  const [scope, setScope] = useState<string>(value?.oauth2?.scope ?? '');
  const [accessToken, setAccessToken] = useState<string>(value?.oauth2?.access_token ?? '');
  const [refreshToken, setRefreshToken] = useState<string>(value?.oauth2?.refresh_token ?? '');

  const isValid = useMemo(() => {
    if (url.trim() === '' || path.trim() === '') return false;
    if (usingSignIn) return true;
    if (authMethod === 'oauth2') {
      return clientId.trim() !== '' && (accessToken.trim() !== '' || clientSecret.trim() !== '');
    }
    // basic or ticket
    return username.trim() !== '' && password.trim() !== '';
  }, [url, path, usingSignIn, authMethod, username, password, clientId, clientSecret, accessToken]);

  const config = useMemo(() => {
    if (usingSignIn && session) {
      return { url, path, auth_method: 'ticket', ticket: session.ticket };
    }
    const base: any = { url, auth_method: authMethod, path };
    if (authMethod === 'oauth2') {
      base.oauth2 = {
        client_id: clientId,
        client_secret: clientSecret || undefined,
        token_endpoint: tokenEndpoint || undefined,
        scope: scope || undefined,
        access_token: accessToken || undefined,
        refresh_token: refreshToken || undefined,
      };
    } else {
      base.username = username;
      base.password = password;
    }
    return base;
  }, [url, authMethod, path, usingSignIn, session, username, password, clientId, clientSecret, tokenEndpoint, scope, accessToken, refreshToken]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
    onChange?.(config);  // persist live config to App so it survives tab switches
  }, [isValid, config, onValidationChange, onConfigurationChange, onChange]);

  return (
    <BaseSourceForm
      title="Alfresco Repository"
      description="Connect to an Alfresco content management system"
    >
      <TextField
        fullWidth
        label="Alfresco Base URL"
        required
        variant="outlined"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder={`e.g., ${defaultUrl}`}
      />

      <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        {signedInHere ? (
          <>
            <Typography variant="body2">
              Signed in to Alfresco as <strong>{session!.user_id}</strong>
              {usingSignIn ? ' (used for this ingest)' : ''}
            </Typography>
            <Button size="small" onClick={() => { signOut(); }}>Sign out</Button>
            <FormControlLabel
              control={<Checkbox size="small" checked={useOther} onChange={(e) => setUseOther(e.target.checked)} />}
              label="Use other credentials (e.g. for Auto Sync)"
            />
          </>
        ) : (
          <>
            <Button
              variant="outlined" size="small"
              onClick={() => openSignIn({ source: 'alfresco', url, methods: ['basic'], documents: null }, 'ingest')}
            >
              Sign in to Alfresco
            </Button>
            <Typography variant="body2" color="text.secondary">or enter credentials below</Typography>
          </>
        )}
      </Box>

      {!usingSignIn && (
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <InputLabel>Authentication</InputLabel>
        <Select
          value={authMethod}
          label="Authentication"
          onChange={(e) => setAuthMethod(e.target.value as AuthMethod)}
        >
          <MenuItem value="basic">Basic (username / password)</MenuItem>
          <MenuItem value="ticket">Ticket (login ticket)</MenuItem>
          <MenuItem value="oauth2">OAuth2 (Bearer, via Identity Service)</MenuItem>
        </Select>
      </FormControl>
      )}

      {!usingSignIn && (authMethod === 'basic' || authMethod === 'ticket') && (
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <TextField
            fullWidth
            label="Username"
            required
            variant="outlined"
            // repository credentials, not a login to this page: keep the browser's password
            // manager from filling them with a saved localhost login
            autoComplete="off"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            size="small"
          />
          <TextField
            fullWidth
            label="Password"
            required
            type="password"
            variant="outlined"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            size="small"
          />
        </Box>
      )}

      {!usingSignIn && authMethod === 'oauth2' && (
        <Box sx={{ mb: 2 }}>
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <TextField
              fullWidth
              label="Client ID"
              required
              autoComplete="off"
              variant="outlined"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              size="small"
            />
            <TextField
              fullWidth
              label="Client Secret"
              required={accessToken.trim() === ''}
              helperText="Required unless an access token is given"
              type="password"
              autoComplete="new-password"
              variant="outlined"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              size="small"
            />
          </Box>
          <TextField
            fullWidth
            label="Token Endpoint (optional)"
            variant="outlined"
            value={tokenEndpoint}
            onChange={(e) => setTokenEndpoint(e.target.value)}
            size="small"
            sx={{ mb: 2 }}
            placeholder="e.g., https://<keycloak>/realms/alfresco/protocol/openid-connect/token"
          />
          <TextField
            fullWidth
            label="Scope (optional)"
            variant="outlined"
            value={scope}
            onChange={(e) => setScope(e.target.value)}
            size="small"
            sx={{ mb: 2 }}
          />
          <Box sx={{ display: 'flex', gap: 2 }}>
            <TextField
              fullWidth
              label="Access Token (optional)"
              type="password"
              autoComplete="new-password"
              variant="outlined"
              value={accessToken}
              onChange={(e) => setAccessToken(e.target.value)}
              size="small"
              helperText="Provide a pre-obtained token instead of client_credentials"
            />
            <TextField
              fullWidth
              label="Refresh Token (optional)"
              type="password"
              autoComplete="new-password"
              variant="outlined"
              value={refreshToken}
              onChange={(e) => setRefreshToken(e.target.value)}
              size="small"
            />
          </Box>
        </Box>
      )}

      <TextField
        fullWidth
        label="Path"
        required
        variant="outlined"
        value={path}
        onChange={(e) => setPath(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="e.g., /Shared/GraphRAG"
      />
    </BaseSourceForm>
  );
};
