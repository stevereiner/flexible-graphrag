import React, { useEffect, useMemo, useRef, useState } from 'react';
import { TextField, Box, Button, Chip, Typography } from '@mui/material';
import { FolderOpen as FolderOpenIcon } from '@mui/icons-material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { SourceBrowser } from '../../browser/SourceBrowser';
import { remoteProvider } from '../../browser/RemoteProvider';
import { BrowseItem } from '../../browser/types';
import { useOnIngestStarted } from '../../ingestSignal';

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
  // files picked in the browser (file_ids: the ingest then reads these instead of a folder)
  const [files, setFiles] = useState<BrowseItem[]>([]);
  // an ingest started: the picked files empty (the run's rows stay in Processing)
  useOnIngestStarted(() => setFiles([]));

  const isValid = useMemo(() => {
    return userPrincipalName.trim() !== '' && clientId.trim() !== '' && clientSecret.trim() !== '' && tenantId.trim() !== '';
  }, [userPrincipalName, clientId, clientSecret, tenantId]);

  const config = useMemo(() => ({
    user_principal_name: userPrincipalName,
    client_id: clientId,
    client_secret: clientSecret,
    tenant_id: tenantId,
    folder_path: folderPath || undefined,
    folder_id: folderId || undefined,
    file_ids: files.length ? files.map((f) => f.id) : undefined,
  }), [userPrincipalName, clientId, clientSecret, tenantId, folderPath, folderId, files]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  // Browse the user's OneDrive with the credentials above (POST /api/browse)
  const [browseOpen, setBrowseOpen] = useState(false);
  const configRef = useRef(config);
  configRef.current = config;
  const provider = useMemo(() => remoteProvider('onedrive', 'OneDrive', () => configRef.current), []);

  // one folder (folder_path), or files (file_ids): the browser keeps the two apart
  const handleBrowsed = (items: BrowseItem[]) => {
    if (!items.length) return;
    if (items[0].isDirectory) {
      setFolderPath(items[0].path || '');
      setFiles([]);
    } else {
      setFiles(items);
      setFolderPath('');
    }
  };

  return (
    <BaseSourceForm
      title="Microsoft OneDrive"
      description="Connect to OneDrive using Azure app registration credentials"
    >
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          fullWidth
          label="User Principal Name"
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
          label="Client ID"
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
          placeholder="common or tenant-id"
          required
        />
      </Box>
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', mb: 2 }}>
        <TextField
          fullWidth
          label="Folder Path (Optional)"
          variant="outlined"
          value={folderPath}
          onChange={(e) => { setFolderPath(e.target.value); if (e.target.value) setFiles([]); }}
          size="small"
          placeholder="Documents/Reports"
          helperText="Optional: a folder in the user's OneDrive (empty: the whole drive)"
          disabled={files.length > 0}
        />
        <Button
          variant="outlined"
          startIcon={<FolderOpenIcon />}
          disabled={!isValid}
          title={isValid ? "Pick a folder or files in the user's OneDrive" : 'Fill in the user and the app credentials first'}
          onClick={() => setBrowseOpen(true)}
          sx={{ whiteSpace: 'nowrap', minWidth: 'auto', height: 40 }}
        >
          Browse…
        </Button>
      </Box>
      {files.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" sx={{ display: 'block', mb: 0.5, opacity: 0.8 }}>
            {files.length === 1 ? '1 file picked' : `${files.length} files picked`}: the ingest reads these instead of a folder
          </Typography>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
            {files.map((f) => (
              <Chip
                key={f.id}
                size="small"
                label={f.path || f.name}
                onDelete={() => setFiles((prev) => prev.filter((p) => p.id !== f.id))}
              />
            ))}
            <Button size="small" onClick={() => setFiles([])}>Clear</Button>
          </Box>
        </Box>
      )}
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
      <SourceBrowser
        open={browseOpen}
        provider={provider}
        title={`Pick a folder or files: ${userPrincipalName || 'OneDrive'}`}
        mixed={false}
        onClose={() => setBrowseOpen(false)}
        onSelect={handleBrowsed}
      />
    </BaseSourceForm>
  );
};
