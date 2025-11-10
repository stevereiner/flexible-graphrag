import React, { useEffect, useMemo, useState } from 'react';
import { TextField } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface GCSSourceFormProps extends BaseSourceFormProps {
  bucketName: string;
  credentials: string;
  onBucketNameChange: (bucketName: string) => void;
  onCredentialsChange: (credentials: string) => void;
}

export const GCSSourceForm: React.FC<GCSSourceFormProps> = ({
  currentTheme,
  bucketName,
  credentials,
  onBucketNameChange,
  onCredentialsChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [prefix, setPrefix] = useState('');

  const isValid = useMemo(() => {
    return bucketName.trim() !== '' && credentials.trim() !== '';
  }, [bucketName, credentials]);

  const config = useMemo(() => ({
    bucket_name: bucketName,
    credentials: credentials,
    prefix: prefix || undefined
  }), [bucketName, credentials, prefix]);

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
        placeholder="sample-docs/"
        helperText="Optional: folder path prefix (e.g., 'sample-docs/' for a specific folder)"
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
