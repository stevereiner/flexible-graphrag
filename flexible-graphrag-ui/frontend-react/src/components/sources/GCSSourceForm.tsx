import React, { useEffect, useMemo, useState } from 'react';
import { TextField } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface GCSSourceFormProps extends BaseSourceFormProps {
  bucketName: string;
  projectId: string;
  credentials: string;
  onBucketNameChange: (bucketName: string) => void;
  onProjectIdChange: (projectId: string) => void;
  onCredentialsChange: (credentials: string) => void;
}

export const GCSSourceForm: React.FC<GCSSourceFormProps> = ({
  currentTheme,
  bucketName,
  projectId,
  credentials,
  onBucketNameChange,
  onProjectIdChange,
  onCredentialsChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [prefix, setPrefix] = useState('');
  const [folderName, setFolderName] = useState('');

  const isValid = useMemo(() => {
    return bucketName.trim() !== '' && projectId.trim() !== '' && credentials.trim() !== '';
  }, [bucketName, projectId, credentials]);

  const config = useMemo(() => ({
    bucket_name: bucketName,
    project_id: projectId,
    credentials: credentials,
    prefix: prefix || undefined,
    folder_name: folderName || undefined
  }), [bucketName, projectId, credentials, prefix, folderName]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Google Cloud Storage"
      description="Connect to Google Cloud Storage buckets"
    >
      <TextField
        fullWidth
        label="Project ID"
        variant="outlined"
        value={projectId}
        onChange={(e) => onProjectIdChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="my-gcp-project"
      />
      <TextField
        fullWidth
        label="Bucket Name"
        variant="outlined"
        value={bucketName}
        onChange={(e) => onBucketNameChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="my-gcs-bucket"
      />
      <TextField
        fullWidth
        label="Prefix/Path (Optional)"
        variant="outlined"
        value={prefix}
        onChange={(e) => setPrefix(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="documents/reports/"
        helperText="Optional: folder path prefix within bucket"
      />
      <TextField
        fullWidth
        label="Folder Name (Optional)"
        variant="outlined"
        value={folderName}
        onChange={(e) => setFolderName(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="my-folder"
        helperText="Optional: specific folder name within bucket"
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
        helperText="Paste your GCS service account JSON credentials"
      />
    </BaseSourceForm>
  );
};
