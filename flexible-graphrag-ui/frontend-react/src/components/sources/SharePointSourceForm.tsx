import React, { useEffect, useMemo, useRef, useState } from 'react';
import { TextField, Box, Button } from '@mui/material';
import { FolderOpen as FolderOpenIcon } from '@mui/icons-material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { SourceBrowser } from '../../browser/SourceBrowser';
import { remoteProvider } from '../../browser/RemoteProvider';
import { BrowseItem } from '../../browser/types';

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

  // Browse the site's document library with the credentials above (POST /api/browse)
  // (always offered: a backend that can't browse answers in the browser's error line)
  const [browseOpen, setBrowseOpen] = useState(false);
  const browsedId = useRef('');
  const configRef = useRef(config);
  configRef.current = config;
  const provider = useMemo(
    () => remoteProvider('sharepoint', 'SharePoint document library', () => configRef.current), []);

  const handleBrowsed = (items: BrowseItem[]) => {
    const folder = items[0];
    if (!folder) return;
    setFolderPath(folder.path || '');
    setFolderId(folder.id);
    browsedId.current = folder.id;
  };

  const handleFolderPathChange = (value: string) => {
    setFolderPath(value);
    // a typed path replaces a browsed folder: its id would win over the path (SharePointReader)
    if (browsedId.current && folderId === browsedId.current) {
      setFolderId('');
      browsedId.current = '';
    }
  };

  return (
    <BaseSourceForm
      title="Microsoft SharePoint"
      description="Connect to SharePoint sites using Azure app registration credentials"
    >
      <TextField
        fullWidth
        label="Site Name"
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
        label="Client ID"
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
          label="Client Secret"
          variant="outlined"
          value={clientSecret}
          onChange={(e) => onClientSecretChange(e.target.value)}
          size="small"
          type="password"
        autoComplete="new-password"
          required
        />
        <TextField
          fullWidth
          label="Tenant ID"
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
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', mb: 2 }}>
        <TextField
          fullWidth
          label="Folder Path (Optional)"
          variant="outlined"
          value={folderPath}
          onChange={(e) => handleFolderPathChange(e.target.value)}
          size="small"
          placeholder="Reports/2024"
          helperText="Optional: a folder in the site's document library (empty: the whole library)"
          autoComplete="off"
        />
        <Button
          variant="outlined"
          startIcon={<FolderOpenIcon />}
          disabled={!isValid}
          title={isValid ? "Pick a folder in the site's document library" : 'Fill in the site and the app credentials first'}
          onClick={() => setBrowseOpen(true)}
          sx={{ whiteSpace: 'nowrap', minWidth: 'auto', height: 40 }}
        >
          Browse…
        </Button>
      </Box>
      <SourceBrowser
        open={browseOpen}
        provider={provider}
        title={`Pick a folder: ${siteName || 'SharePoint'}`}
        files={false}
        multiple={false}
        onClose={() => setBrowseOpen(false)}
        onSelect={handleBrowsed}
      />
    </BaseSourceForm>
  );
};
