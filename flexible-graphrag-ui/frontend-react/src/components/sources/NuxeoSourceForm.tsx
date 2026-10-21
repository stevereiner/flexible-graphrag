import React, { useEffect, useMemo, useState } from 'react';
import { TextField, Box, FormControl, InputLabel, Select, MenuItem } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { SourceSignInSection, useSourceSession } from '../../auth/SourceSignInSection';
import { DeepCheckbox, deepValue } from './DeepCheckbox';
import { useUiDefaults } from '../../uiDefaults';

type AuthMethod = 'basic' | 'oauth2' | 'token';

interface NuxeoSourceFormProps extends BaseSourceFormProps {
  // Single-object persistence: seeds the form on mount and receives the full config on every
  // edit, so App can hold one object and the form's state survives Sources<->Processing tab
  // switches (the Sources TabPanel unmounts on switch).
  value?: any;
  onChange?: (config: any) => void;
}

// Self-contained form: manages its own state and emits a complete Nuxeo config
// object via onConfigurationChange (matching the backend NuxeoConfig model).
export const NuxeoSourceForm: React.FC<NuxeoSourceFormProps> = ({
  value,
  onChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const defaultUrl = useMemo(
    () => import.meta.env.VITE_NUXEO_BASE_URL || 'http://localhost:8081/nuxeo',
    []
  );
  // The browser cannot read the backend's .env, so NUXEO_PATH there has no
  // effect here -- set VITE_NUXEO_PATH at build time to point the dialog at
  // your own workspace.  Default is a workspace, not the folder above it.
  const defaultPath = useMemo(
    () => import.meta.env.VITE_NUXEO_PATH || '/default-domain/workspaces/GraphRAG',
    []
  );

  const [url, setUrl] = useState<string>(value?.url ?? defaultUrl);
  const [authMethod, setAuthMethod] = useState<AuthMethod>(value?.auth_method ?? 'basic');
  const [path, setPath] = useState<string>(value?.path ?? defaultPath);
  // Deep: include subfolders (recursive). Unset: the backend's DEFAULT_RECURSIVE, else off
  const [ownDeep, setRecursive] = useState<boolean | undefined>(value?.recursive);
  const recursive = deepValue(ownDeep, useUiDefaults().recursive, false);

  // Basic auth
  // no pre-filled credentials (were Administrator/Administrator)
  const [username, setUsername] = useState<string>(value?.username ?? '');
  const [password, setPassword] = useState<string>(value?.password ?? '');

  // The Nuxeo sign-in (header / dialog, planning/SOURCE-AUTH-LOGIN.md). When signed in to this
  // server, the ingest uses that session's token and the credential fields are hidden.
  const { session, useOther, setUseOther, usingSignIn, credential } = useSourceSession('nuxeo', url);

  // OAuth2
  const [clientId, setClientId] = useState<string>(value?.oauth2?.client_id ?? '');
  const [clientSecret, setClientSecret] = useState<string>(value?.oauth2?.client_secret ?? '');
  const [accessToken, setAccessToken] = useState<string>(value?.oauth2?.access_token ?? '');
  const [refreshToken, setRefreshToken] = useState<string>(value?.oauth2?.refresh_token ?? '');
  const [tokenEndpoint, setTokenEndpoint] = useState<string>(value?.oauth2?.token_endpoint ?? '');

  const isValid = useMemo(() => {
    if (url.trim() === '') return false;
    if (usingSignIn) return true;
    // basic and token both authenticate with username/password (token mode fetches a
    // Nuxeo auth token from them on the backend, like Alfresco ticket).
    if (authMethod === 'basic' || authMethod === 'token') {
      return username.trim() !== '' && password.trim() !== '';
    }
    // oauth2
    return clientId.trim() !== '' && (accessToken.trim() !== '' || clientSecret.trim() !== '');
  }, [url, usingSignIn, authMethod, username, password, clientId, clientSecret, accessToken]);

  const config = useMemo(() => {
    if (usingSignIn && credential) return { url, path, recursive, ...credential };
    const base: any = { url, auth_method: authMethod, path, recursive };
    // token mode sends username/password; the backend fetches the auth token from them.
    if (authMethod === 'basic' || authMethod === 'token') {
      base.username = username;
      base.password = password;
    } else {
      base.oauth2 = {
        client_id: clientId,
        client_secret: clientSecret || undefined,
        access_token: accessToken || undefined,
        refresh_token: refreshToken || undefined,
        token_endpoint: tokenEndpoint || undefined,
      };
    }
    return base;
  }, [url, authMethod, path, recursive, usingSignIn, credential, username, password, clientId, clientSecret, accessToken, refreshToken, tokenEndpoint]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
    onChange?.(config);  // persist live config to App so it survives tab switches
  }, [isValid, config, onValidationChange, onConfigurationChange, onChange]);

  return (
    <BaseSourceForm
      title="Nuxeo Repository"
      description="Connect to a Nuxeo content management system"
    >
      <TextField
        fullWidth
        label="Nuxeo Base URL"
        required
        variant="outlined"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="e.g., http://localhost:8081/nuxeo"
        helperText="Base repository URL (no /api/v1 suffix)"
      />

      <SourceSignInSection
        source="nuxeo" url={url} session={session} usingSignIn={usingSignIn}
        useOther={useOther} onUseOtherChange={setUseOther}
      />

      {!usingSignIn && (
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <InputLabel>Authentication</InputLabel>
        <Select
          value={authMethod}
          label="Authentication"
          onChange={(e) => setAuthMethod(e.target.value as AuthMethod)}
        >
          <MenuItem value="basic">Basic (username / password)</MenuItem>
          <MenuItem value="oauth2">OAuth2 (Bearer)</MenuItem>
          <MenuItem value="token">Token (X-Authentication-Token)</MenuItem>
        </Select>
      </FormControl>
      )}

      {!usingSignIn && (authMethod === 'basic' || authMethod === 'token') && (
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <TextField
            fullWidth
            autoComplete="off"
        label="Username"
        required
            variant="outlined"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            size="small"
          />
          <TextField
            fullWidth
            label="Password"
            required
            type="password"
        autoComplete="new-password"
            variant="outlined"
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
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <TextField
              fullWidth
              label="Access Token (optional)"
              type="password"
        autoComplete="new-password"
              variant="outlined"
              value={accessToken}
              onChange={(e) => setAccessToken(e.target.value)}
              size="small"
              helperText="Obtain out-of-band (authorization code + PKCE)"
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
          <TextField
            fullWidth
            label="Token Endpoint (optional)"
            variant="outlined"
            value={tokenEndpoint}
            onChange={(e) => setTokenEndpoint(e.target.value)}
            size="small"
            placeholder="defaults to <url>/oauth2/token"
          />
        </Box>
      )}

      <Box sx={{ display: 'flex', alignItems: 'flex-start' }}>
        <TextField
          fullWidth
          label="Path"
          required
          variant="outlined"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          size="small"
          sx={{ mb: 2 }}
          placeholder="e.g., /default-domain/workspaces/GraphRAG"
        />
        <DeepCheckbox checked={recursive} onChange={setRecursive} />
      </Box>
    </BaseSourceForm>
  );
};
