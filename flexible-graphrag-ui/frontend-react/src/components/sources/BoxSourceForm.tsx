import React, { useEffect, useMemo, useState } from 'react';
import { TextField, Box, Typography } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface BoxSourceFormProps extends BaseSourceFormProps {
  clientId: string;
  clientSecret: string;
  developerToken: string;
  onClientIdChange: (clientId: string) => void;
  onClientSecretChange: (clientSecret: string) => void;
  onDeveloperTokenChange: (developerToken: string) => void;
}

export const BoxSourceForm: React.FC<BoxSourceFormProps> = ({
  currentTheme,
  clientId,
  clientSecret,
  developerToken,
  onClientIdChange,
  onClientSecretChange,
  onDeveloperTokenChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [folderId, setFolderId] = useState('');

  const isValid = useMemo(() => {
    return (developerToken.trim() !== '') || (clientId.trim() !== '' && clientSecret.trim() !== '');
  }, [developerToken, clientId, clientSecret]);

  const config = useMemo(() => ({
    client_id: clientId || undefined,
    client_secret: clientSecret || undefined,
    developer_token: developerToken || undefined,
    folder_id: folderId || undefined
  }), [clientId, clientSecret, developerToken, folderId]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Box Storage"
      description="Connect to Box cloud storage using Developer Token or Client Credentials"
    >
      <Typography variant="body2" sx={{ mb: 2, color: 'text.secondary' }}>
        Use either Developer Token (short-lived) or Client Credentials (long-lived):
      </Typography>
      <TextField
        fullWidth
        label="Developer Token (Optional)"
        variant="outlined"
        value={developerToken}
        onChange={(e) => onDeveloperTokenChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        type="password"
        helperText="Short-lived token from Box Developer Console"
      />
      <Typography variant="body2" sx={{ mb: 1, color: 'text.secondary' }}>
        OR Client Credentials:
      </Typography>
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          fullWidth
          label="Client ID"
          variant="outlined"
          value={clientId}
          onChange={(e) => onClientIdChange(e.target.value)}
          size="small"
        />
        <TextField
          fullWidth
          label="Client Secret"
          variant="outlined"
          value={clientSecret}
          onChange={(e) => onClientSecretChange(e.target.value)}
          size="small"
          type="password"
        />
      </Box>
      <TextField
        fullWidth
        label="Folder ID (Optional)"
        variant="outlined"
        value={folderId}
        onChange={(e) => setFolderId(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="123456789"
        helperText="Optional: specific Box folder ID to access"
      />
    </BaseSourceForm>
  );
};
