import React, { useEffect, useMemo, useState } from 'react';
import { TextField } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

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

  const isValid = useMemo(() => {
    return credentials.trim() !== '';
  }, [credentials]);

  const config = useMemo(() => ({
    credentials: credentials,
    folder_id: folderId || undefined
  }), [credentials, folderId]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Google Drive"
      description="Connect to Google Drive using service account credentials"
    >
      <TextField
        fullWidth
        label="Folder ID (Optional)"
        variant="outlined"
        value={folderId}
        onChange={(e) => setFolderId(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        helperText="Optional: Google Drive folder ID to process specific folder. Leave empty to process all accessible files."
      />
      <TextField
        fullWidth
        label="Service Account Credentials (JSON)"
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
    </BaseSourceForm>
  );
};
