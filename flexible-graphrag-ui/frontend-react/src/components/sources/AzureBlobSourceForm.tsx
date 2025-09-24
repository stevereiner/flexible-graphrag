import React, { useEffect, useMemo, useState } from 'react';
import { TextField } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface AzureBlobSourceFormProps extends BaseSourceFormProps {
  connectionString: string;
  containerName: string;
  blobName: string;
  accountName: string;
  accountKey: string;
  onConnectionStringChange: (connectionString: string) => void;
  onContainerNameChange: (containerName: string) => void;
  onBlobNameChange: (blobName: string) => void;
  onAccountNameChange: (accountName: string) => void;
  onAccountKeyChange: (accountKey: string) => void;
}

export const AzureBlobSourceForm: React.FC<AzureBlobSourceFormProps> = ({
  currentTheme,
  connectionString,
  containerName,
  blobName,
  accountName,
  accountKey,
  onConnectionStringChange,
  onContainerNameChange,
  onBlobNameChange,
  onAccountNameChange,
  onAccountKeyChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [prefix, setPrefix] = useState('');
  const [accountUrl, setAccountUrl] = useState('');

  const isValid = useMemo(() => {
    // Method 1 requires: account_url, container_name, account_name, account_key
    return accountUrl.trim() !== '' && 
           containerName.trim() !== '' && 
           accountName.trim() !== '' && 
           accountKey.trim() !== '';
  }, [accountUrl, containerName, accountName, accountKey]);

  const config = useMemo(() => ({
    // Method 1 (Account Key Authentication) fields
    container_name: containerName,
    account_url: accountUrl,
    blob: blobName || undefined,
    prefix: prefix || undefined,
    account_name: accountName,
    account_key: accountKey
  }), [containerName, accountUrl, blobName, prefix, accountName, accountKey]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Azure Blob Storage"
      description="Connect to Azure Blob Storage using Account Key Authentication (Method 1)"
    >
      <TextField
        fullWidth
        label="Account URL *"
        variant="outlined"
        value={accountUrl}
        onChange={(e) => setAccountUrl(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="https://mystorageaccount.blob.core.windows.net"
        helperText="Azure Storage account URL (required)"
        required
      />
      <TextField
        fullWidth
        label="Container Name *"
        variant="outlined"
        value={containerName}
        onChange={(e) => onContainerNameChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="my-container"
        required
      />
      <TextField
        fullWidth
        label="Blob (Optional)"
        variant="outlined"
        value={blobName}
        onChange={(e) => onBlobNameChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="specific-file.pdf"
        helperText="Optional: specific blob/file name"
      />
      <TextField
        fullWidth
        label="Prefix (Optional)"
        variant="outlined"
        value={prefix}
        onChange={(e) => setPrefix(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="documents/reports/"
        helperText="Optional: folder path prefix within container"
      />
      <TextField
        fullWidth
        label="Account Name *"
        variant="outlined"
        value={accountName}
        onChange={(e) => onAccountNameChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="mystorageaccount"
        helperText="Azure Storage account name (required)"
        required
      />
      <TextField
        fullWidth
        label="Account Key *"
        variant="outlined"
        value={accountKey}
        onChange={(e) => onAccountKeyChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        type="password"
        placeholder="account-key-here"
        helperText="Azure Storage account key (required)"
        required
      />
    </BaseSourceForm>
  );
};
