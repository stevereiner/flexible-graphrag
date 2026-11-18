import React, { useEffect, useMemo, useRef, useState } from 'react';
import { TextField, Box, Button, Chip, Typography } from '@mui/material';
import { FolderOpen as FolderOpenIcon } from '@mui/icons-material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { SourceBrowser } from '../../browser/SourceBrowser';
import { remoteProvider } from '../../browser/RemoteProvider';
import { BrowseItem } from '../../browser/types';
import { useOnIngestStarted } from '../../ingestSignal';

interface GoogleDriveSourceFormProps extends BaseSourceFormProps {
  credentials: string;
  onCredentialsChange: (credentials: string) => void;
}

export const GoogleDriveSourceForm: React.FC<GoogleDriveSourceFormProps> = ({
  currentTheme,
  credentials,
  onCredentialsChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [folderId, setFolderId] = useState<string>('');
  // the browsed folder's name path, shown under its id (cleared when the id is typed)
  const [folderLabel, setFolderLabel] = useState('');
  // files picked in the browser (file_ids: the ingest reads these when there is no folder id)
  const [files, setFiles] = useState<BrowseItem[]>([]);
  // an ingest started: the picked files empty (the run's rows stay in Processing)
  useOnIngestStarted(() => setFiles([]));

  // Browse needs the credentials; the ingest also needs a folder or files (the reader reads
  // nothing else: a service account has no "whole drive")
  const canBrowse = credentials.trim() !== '';
  const isValid = useMemo(
    () => canBrowse && (folderId.trim() !== '' || files.length > 0),
    [canBrowse, folderId, files]);

  const config = useMemo(() => ({
    credentials: credentials,
    folder_id: folderId || undefined,
    file_ids: files.length ? files.map((f) => f.id) : undefined,
  }), [credentials, folderId, files]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  // Browse what the service account can see (POST /api/browse)
  const [browseOpen, setBrowseOpen] = useState(false);
  const configRef = useRef(config);
  configRef.current = config;
  const provider = useMemo(() => remoteProvider('google_drive', 'Google Drive', () => configRef.current), []);

  // one folder (folder_id), or files (file_ids): the browser keeps the two apart (a folder id
  // would win over file ids in the ingest)
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
      title="Google Drive"
      description="Connect to Google Drive using service account credentials"
    >
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
        <TextField
          fullWidth
          label="Folder ID"
          required={files.length === 0}
          variant="outlined"
          value={folderId}
          onChange={(e) => {
            setFolderId(e.target.value);
            setFolderLabel('');
            if (e.target.value) setFiles([]);
          }}
          size="small"
          sx={{ mb: 2 }}
          placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
          helperText={folderLabel ? `Folder: ${folderLabel}` : 'A folder shared with the service account, or pick files with Browse…'}
          disabled={files.length > 0}
        />
        <Button
          variant="outlined"
          startIcon={<FolderOpenIcon />}
          disabled={!canBrowse}
          title={canBrowse ? 'Pick a folder or files in Google Drive' : 'Paste the service account credentials first'}
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
        label="Service Account Credentials (JSON)"
        required
        variant="outlined"
        value={credentials}
        onChange={(e) => onCredentialsChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        multiline
        rows={3}
        placeholder='{"type": "service_account", "project_id": "...", ...}'
        helperText="Paste your Google Drive service account JSON credentials"
      />
      <SourceBrowser
        open={browseOpen}
        provider={provider}
        title="Pick a folder or files: Google Drive"
        mixed={false}
        onClose={() => setBrowseOpen(false)}
        onSelect={handleBrowsed}
      />
    </BaseSourceForm>
  );
};
