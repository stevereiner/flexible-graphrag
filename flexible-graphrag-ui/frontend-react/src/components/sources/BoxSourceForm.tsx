import React, { useEffect, useMemo, useState } from 'react';
import { TextField, Box, Typography, FormControl, InputLabel, Select, MenuItem } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

type BoxAuthMode = 'developer_token' | 'ccg_user' | 'ccg_enterprise' | 'ccg_both';

interface BoxSourceFormProps extends BaseSourceFormProps {
  clientId: string;
  clientSecret: string;
  developerToken: string;
  userId: string;
  enterpriseId: string;
  onClientIdChange: (clientId: string) => void;
  onClientSecretChange: (clientSecret: string) => void;
  onDeveloperTokenChange: (developerToken: string) => void;
  onUserIdChange: (userId: string) => void;
  onEnterpriseIdChange: (enterpriseId: string) => void;
}

export const BoxSourceForm: React.FC<BoxSourceFormProps> = ({
  currentTheme,
  clientId,
  clientSecret,
  developerToken,
  userId,
  enterpriseId,
  onClientIdChange,
  onClientSecretChange,
  onDeveloperTokenChange,
  onUserIdChange,
  onEnterpriseIdChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [folderId, setFolderId] = useState('');
  const [authMode, setAuthMode] = useState<BoxAuthMode>('developer_token');

  const isValid = useMemo(() => {
    switch (authMode) {
      case 'developer_token':
        return developerToken.trim() !== '';
      case 'ccg_user':
        return clientId.trim() !== '' && clientSecret.trim() !== '' && userId.trim() !== '';
      case 'ccg_enterprise':
        return clientId.trim() !== '' && clientSecret.trim() !== '' && enterpriseId.trim() !== '';
      case 'ccg_both':
        return clientId.trim() !== '' && clientSecret.trim() !== '' && userId.trim() !== '' && enterpriseId.trim() !== '';
      default:
        return false;
    }
  }, [authMode, developerToken, clientId, clientSecret, userId, enterpriseId]);

  const config = useMemo(() => ({
    client_id: (authMode !== 'developer_token') ? clientId : undefined,
    client_secret: (authMode !== 'developer_token') ? clientSecret : undefined,
    developer_token: authMode === 'developer_token' ? developerToken : undefined,
    user_id: (authMode === 'ccg_user' || authMode === 'ccg_both') ? userId : undefined,
    enterprise_id: (authMode === 'ccg_enterprise' || authMode === 'ccg_both') ? enterpriseId : undefined,
    folder_id: folderId || undefined
  }), [authMode, clientId, clientSecret, developerToken, userId, enterpriseId, folderId]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Box Storage"
      description="Connect to Box with quick token or persistent app credentials"
    >
      <FormControl fullWidth size="small" sx={{ mb: 2 }}>
        <InputLabel>Authentication Type</InputLabel>
        <Select
          value={authMode}
          onChange={(e) => setAuthMode(e.target.value as BoxAuthMode)}
          label="Authentication Type"
        >
          <MenuItem value="developer_token">Developer Token</MenuItem>
          <MenuItem value="ccg_user">App Access (User)</MenuItem>
          <MenuItem value="ccg_enterprise">App Access (Enterprise)</MenuItem>
          <MenuItem value="ccg_both">App Access (User + Enterprise)</MenuItem>
        </Select>
      </FormControl>

      {authMode === 'developer_token' && (
        <TextField
          fullWidth
          label="Developer Token"
          variant="outlined"
          value={developerToken}
          onChange={(e) => onDeveloperTokenChange(e.target.value)}
          size="small"
          sx={{ mb: 2 }}
          type="password"
          helperText="Temporary token for testing (expires after 1 hour)"
        />
      )}

      {(authMode === 'ccg_user' || authMode === 'ccg_enterprise' || authMode === 'ccg_both') && (
        <>
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <TextField
              fullWidth
              label="App Client ID"
              variant="outlined"
              value={clientId}
              onChange={(e) => onClientIdChange(e.target.value)}
              size="small"
            />
            <TextField
              fullWidth
              label="App Client Secret"
              variant="outlined"
              value={clientSecret}
              onChange={(e) => onClientSecretChange(e.target.value)}
              size="small"
              type="password"
            />
          </Box>
          {(authMode === 'ccg_user' || authMode === 'ccg_both') && (
            <TextField
              fullWidth
              label="Box User ID"
              variant="outlined"
              value={userId}
              onChange={(e) => onUserIdChange(e.target.value)}
              size="small"
              sx={{ mb: 2 }}
              placeholder="12345678"
              helperText="Access files for a specific Box user"
            />
          )}
          {(authMode === 'ccg_enterprise' || authMode === 'ccg_both') && (
            <TextField
              fullWidth
              label="Box Enterprise ID"
              variant="outlined"
              value={enterpriseId}
              onChange={(e) => onEnterpriseIdChange(e.target.value)}
              size="small"
              sx={{ mb: 2 }}
              placeholder="987654321"
              helperText="Access files across your entire Box organization"
            />
          )}
        </>
      )}

      <TextField
        fullWidth
        label="Folder ID (Optional)"
        variant="outlined"
        value={folderId}
        onChange={(e) => setFolderId(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="0"
        helperText="Leave empty for root folder"
      />
    </BaseSourceForm>
  );
};
