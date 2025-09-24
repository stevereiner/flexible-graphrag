import React, { useEffect, useMemo, useState } from 'react';
import { TextField, Box } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface S3SourceFormProps extends BaseSourceFormProps {
  accessKey: string;
  secretKey: string;
  onAccessKeyChange: (accessKey: string) => void;
  onSecretKeyChange: (secretKey: string) => void;
}

export const S3SourceForm: React.FC<S3SourceFormProps> = ({
  currentTheme,
  accessKey,
  secretKey,
  onAccessKeyChange,
  onSecretKeyChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [bucketName, setBucketName] = useState('');
  const [prefix, setPrefix] = useState('');

  const isValid = useMemo(() => {
    return bucketName.trim() !== '' && accessKey.trim() !== '' && secretKey.trim() !== '';
  }, [bucketName, accessKey, secretKey]);

  const config = useMemo(() => ({
    bucket_name: bucketName,  // Use modern bucket_name field
    prefix: prefix || undefined,
    access_key: accessKey,
    secret_key: secretKey
  }), [bucketName, prefix, accessKey, secretKey]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Amazon S3"
      description="Connect to Amazon S3 buckets using bucket name and credentials"
    >
      <TextField
        fullWidth
        label="Bucket Name *"
        variant="outlined"
        value={bucketName}
        onChange={(e) => setBucketName(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="my-bucket"
        helperText="S3 bucket name (required)"
        required
        autoComplete="off"
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
        autoComplete="off"
        inputProps={{
          autoComplete: 'off',
          'data-lpignore': 'true', // LastPass ignore
          'data-form-type': 'other' // Prevent autofill
        }}
      />
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          fullWidth
          label="Access Key *"
          variant="outlined"
          value={accessKey}
          onChange={(e) => onAccessKeyChange(e.target.value)}
          size="small"
          type="password"
          required
          autoComplete="off"
        />
        <TextField
          fullWidth
          label="Secret Key *"
          variant="outlined"
          value={secretKey}
          onChange={(e) => onSecretKeyChange(e.target.value)}
          size="small"
          type="password"
          required
          autoComplete="off"
        />
      </Box>
    </BaseSourceForm>
  );
};
