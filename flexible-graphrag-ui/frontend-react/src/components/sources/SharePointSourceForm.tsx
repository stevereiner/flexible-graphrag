import React, { useEffect, useMemo, useState } from 'react';
import { TextField, Box } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface SharePointSourceFormProps extends BaseSourceFormProps {
  siteName: string;
  clientId: string;
  clientSecret: string;
  tenantId: string;
  onSiteNameChange: (siteName: string) => void;  // Changed from onSiteUrlChange
  onClientIdChange: (clientId: string) => void;
  onClientSecretChange: (clientSecret: string) => void;
  onTenantIdChange: (tenantId: string) => void;
}

export const SharePointSourceForm: React.FC<SharePointSourceFormProps> = ({
  currentTheme,
  siteName,  // Changed from siteUrl to siteName
  clientId,
  clientSecret,
  tenantId,
  onSiteNameChange,  // Changed from onSiteUrlChange
  onClientIdChange,
  onClientSecretChange,
  onTenantIdChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [folderPath, setFolderPath] = useState('');
  const [folderId, setFolderId] = useState('');  // Changed from documentLibrary to folderId
  const [siteId, setSiteId] = useState('');  // Added for Sites.Selected permission

  const isValid = useMemo(() => {
    return siteName.trim() !== '' && clientId.trim() !== '' && clientSecret.trim() !== '' && tenantId.trim() !== '';
  }, [siteName, clientId, clientSecret, tenantId]);

  const config = useMemo(() => ({
    site_name: siteName,
    client_id: clientId,
    client_secret: clientSecret,
    tenant_id: tenantId,
    site_id: siteId || undefined,  // Added for Sites.Selected permission
    folder_path: folderPath || undefined,
    folder_id: folderId || undefined  // Changed from document_library to folder_id
  }), [siteName, clientId, clientSecret, tenantId, siteId, folderPath, folderId]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Microsoft SharePoint"
      description="Connect to SharePoint sites using Azure app registration credentials"
    >
      <TextField
        fullWidth
        label="Site Name *"
        variant="outlined"
        value={siteName}
        onChange={(e) => onSiteNameChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="sitename"
        helperText="SharePoint site name (not full URL, just the site name)"
        required
        autoComplete="off"
      />
      <TextField
        fullWidth
        label="Site ID (Optional)"
        variant="outlined"
        value={siteId}
        onChange={(e) => setSiteId(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="12345678-1234-1234-1234-123456789012"
        helperText="Optional: Site ID for Sites.Selected permission (recommended for security)"
        autoComplete="off"
      />
      <TextField
        fullWidth
        label="Client ID *"
        variant="outlined"
        value={clientId}
        onChange={(e) => onClientIdChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="12345678-1234-1234-1234-123456789012"
        required
      />
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
          placeholder="tenant-id"
          required
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
        placeholder="01BYE5RZ6QN6OWWLQZC5FK2GWWDURNZHIL"
        helperText="Optional: specific folder ID (replaces document library)"
        autoComplete="off"
      />
      <TextField
        fullWidth
        label="Folder Path (Optional)"
        variant="outlined"
        value={folderPath}
        onChange={(e) => setFolderPath(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="/Shared Documents/Reports"
        helperText="Optional: specific folder path within site"
        autoComplete="off"
      />
    </BaseSourceForm>
  );
};
