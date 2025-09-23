import React, { useEffect, useMemo, useState } from 'react';
import { TextField, Box } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface OneDriveSourceFormProps extends BaseSourceFormProps {
  userPrincipalName: string;
  clientId: string;
  clientSecret: string;
  tenantId: string;
  onUserPrincipalNameChange: (userPrincipalName: string) => void;
  onClientIdChange: (clientId: string) => void;
  onClientSecretChange: (clientSecret: string) => void;
  onTenantIdChange: (tenantId: string) => void;
}

export const OneDriveSourceForm: React.FC<OneDriveSourceFormProps> = ({
  currentTheme: _currentTheme,
  userPrincipalName,
  clientId,
  clientSecret,
  tenantId,
  onUserPrincipalNameChange,
  onClientIdChange,
  onClientSecretChange,
  onTenantIdChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [folderPath, setFolderPath] = useState('');
  const [folderId, setFolderId] = useState('');

  const isValid = useMemo(() => {
    return userPrincipalName.trim() !== '' && clientId.trim() !== '' && clientSecret.trim() !== '' && tenantId.trim() !== '';
  }, [userPrincipalName, clientId, clientSecret, tenantId]);

  const config = useMemo(() => ({
    user_principal_name: userPrincipalName,
    client_id: clientId,
    client_secret: clientSecret,
    tenant_id: tenantId,
    folder_path: folderPath || undefined,
    folder_id: folderId || undefined
  }), [userPrincipalName, clientId, clientSecret, tenantId, folderPath, folderId]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Microsoft OneDrive"
      description="Connect to OneDrive using Azure app registration credentials"
    >
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          fullWidth
          label="User Principal Name *"
          variant="outlined"
          value={userPrincipalName}
          onChange={(e) => onUserPrincipalNameChange(e.target.value)}
          size="small"
          placeholder="user@domain.com"
          helperText="User principal name (email)"
          required
        />
        <TextField
          fullWidth
          label="Client ID *"
          variant="outlined"
          value={clientId}
          onChange={(e) => onClientIdChange(e.target.value)}
          size="small"
          placeholder="12345678-1234-1234-1234-123456789012"
          required
        />
      </Box>
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          fullWidth
          label="Client Secret *"
          variant="outlined"
          value={clientSecret}
          onChange={(e) => onClientSecretChange(e.target.value)}
          size="small"
          type="password"
          required
        />
        <TextField
          fullWidth
          label="Tenant ID *"
          variant="outlined"
          value={tenantId}
          onChange={(e) => onTenantIdChange(e.target.value)}
          size="small"
          placeholder="common or tenant-id"
          required
        />
      </Box>
      <TextField
        fullWidth
        label="Folder Path (Optional)"
        variant="outlined"
        value={folderPath}
        onChange={(e) => setFolderPath(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="/Documents/Reports"
        helperText="Optional: specific folder path in OneDrive"
      />
      <TextField
        fullWidth
        label="Folder ID (Optional)"
        variant="outlined"
        value={folderId}
        onChange={(e) => setFolderId(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="01BYE5RZ6QN6OWWLQZC5FK2GWWDURNZHIL"
        helperText="Optional: specific OneDrive folder ID"
      />
    </BaseSourceForm>
  );
};
