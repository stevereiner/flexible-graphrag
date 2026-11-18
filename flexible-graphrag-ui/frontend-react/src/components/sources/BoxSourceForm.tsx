import React, { useEffect, useMemo, useRef, useState } from 'react';
import { TextField, Box, Button, Chip, Typography, FormControl, InputLabel, Select, MenuItem } from '@mui/material';
import { FolderOpen as FolderOpenIcon } from '@mui/icons-material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { DeepCheckbox, deepValue } from './DeepCheckbox';
import { useUiDefaults } from '../../uiDefaults';
import { SourceBrowser } from '../../browser/SourceBrowser';
import { remoteProvider } from '../../browser/RemoteProvider';
import { BrowseItem } from '../../browser/types';
import { useOnIngestStarted } from '../../ingestSignal';

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
  // the browsed folder's name path, shown under its id (cleared when the id is typed)
  const [folderLabel, setFolderLabel] = useState('');
  // files picked in the browser (box_file_ids: the ingest then reads these instead of a folder)
  const [files, setFiles] = useState<BrowseItem[]>([]);
  // an ingest started: the picked files empty (the run's rows stay in Processing)
  useOnIngestStarted(() => setFiles([]));
  const [authMode, setAuthMode] = useState<BoxAuthMode>('ccg_user');
  // Deep: include subfolders (recursive). Unset: the backend's DEFAULT_RECURSIVE, else on (Box's
  // own default)
  const [ownDeep, setRecursive] = useState<boolean | undefined>(undefined);
  const recursive = deepValue(ownDeep, useUiDefaults().recursive, true);

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
    folder_id: folderId || undefined,
    box_file_ids: files.length ? files.map((f) => f.id) : undefined,
    recursive,
  }), [authMode, clientId, clientSecret, developerToken, userId, enterpriseId, folderId, files, recursive]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  // Browse Box with the credentials above (POST /api/browse)
  const [browseOpen, setBrowseOpen] = useState(false);
  const configRef = useRef(config);
  configRef.current = config;
  const provider = useMemo(() => remoteProvider('box', 'Box', () => configRef.current), []);

  // one folder (folder_id), or files (box_file_ids): the browser keeps the two apart
  const handleBrowsed = (items: BrowseItem[]) => {
    if (!items.length) return;
    if (items[0].isDirectory) {
      setFolderId(items[0].id);
      setFolderLabel(items[0].path || items[0].name);
      setFiles([]);
    } else {
      setFiles(items);
      setFolderId('');
      setFolderLabel('');
    }
  };

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
          <MenuItem value="ccg_user">App Access (User)</MenuItem>
          <MenuItem value="ccg_enterprise">App Access (Enterprise)</MenuItem>
          <MenuItem value="ccg_both">App Access (User + Enterprise)</MenuItem>
          <MenuItem value="developer_token">Developer Token (expires after 1 hour)</MenuItem>
        </Select>
      </FormControl>

      {authMode === 'developer_token' && (
        <TextField
          fullWidth
          label="Developer Token"
          required
          variant="outlined"
          value={developerToken}
          onChange={(e) => onDeveloperTokenChange(e.target.value)}
          size="small"
          sx={{ mb: 2 }}
          type="password"
        autoComplete="new-password"
          helperText="Temporary token for testing (expires after 1 hour)"
        />
      )}

      {(authMode === 'ccg_user' || authMode === 'ccg_enterprise' || authMode === 'ccg_both') && (
        <>
          <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
            <TextField
              fullWidth
              label="App Client ID"
              required
              variant="outlined"
              value={clientId}
              onChange={(e) => onClientIdChange(e.target.value)}
              size="small"
            />
            <TextField
              fullWidth
              label="App Client Secret"
              required
              variant="outlined"
              value={clientSecret}
              onChange={(e) => onClientSecretChange(e.target.value)}
              size="small"
              type="password"
        autoComplete="new-password"
            />
          </Box>
          {(authMode === 'ccg_user' || authMode === 'ccg_both') && (
            <TextField
              fullWidth
              label="Box User ID"
              required
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
              required
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

      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
        <TextField
          fullWidth
          label="Folder ID (Optional)"
          variant="outlined"
          value={folderId}
          onChange={(e) => {
            setFolderId(e.target.value);
            setFolderLabel('');
            if (e.target.value) setFiles([]);
          }}
          size="small"
          sx={{ mb: 2 }}
          placeholder="e.g., 123456789"
          helperText={folderLabel ? `Folder: ${folderLabel}` : 'Leave empty for the root folder (All Files, ID 0)'}
          disabled={files.length > 0}
        />
        <Button
          variant="outlined"
          startIcon={<FolderOpenIcon />}
          disabled={!isValid}
          title={isValid ? 'Pick a folder or files in Box' : 'Fill in the credentials first'}
          onClick={() => setBrowseOpen(true)}
          sx={{ whiteSpace: 'nowrap', minWidth: 'auto', height: 40 }}
        >
          Browse…
        </Button>
        <DeepCheckbox checked={recursive} onChange={setRecursive} />
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
      <SourceBrowser
        open={browseOpen}
        provider={provider}
        title="Pick a folder or files: Box"
        mixed={false}
        onClose={() => setBrowseOpen(false)}
        onSelect={handleBrowsed}
      />
    </BaseSourceForm>
  );
};
