import React, { useEffect, useMemo, useRef, useState } from 'react';
import { TextField, Box, Button } from '@mui/material';
import { FolderOpen as FolderOpenIcon } from '@mui/icons-material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { SourceBrowser } from '../../browser/SourceBrowser';
import { remoteProvider } from '../../browser/RemoteProvider';
import { BrowseItem } from '../../browser/types';

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

  // Browse the container with the account key above (POST /api/browse)
  const [browseOpen, setBrowseOpen] = useState(false);
  const configRef = useRef(config);
  configRef.current = config;
  const provider = useMemo(() => remoteProvider('azure_blob', 'Azure Blob container', () => configRef.current), []);

  // one folder (prefix "docs/reports/") or one blob (its full name): the ingest takes blob over prefix
  const handleBrowsed = (items: BrowseItem[]) => {
    if (!items.length) return;
    const picked = items[0].path || items[0].id;
    if (items[0].isDirectory) {
      setPrefix(picked);
      onBlobNameChange('');
    } else {
      onBlobNameChange(picked);
      setPrefix('');
    }
  };

  return (
    <BaseSourceForm
      title="Azure Blob Storage"
      description="Connect to Azure Blob Storage using Account Key Authentication (Method 1)"
    >
      <TextField
        fullWidth
        label="Account URL"
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
        label="Container Name"
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
        helperText="Optional: one blob's full name (e.g. docs/a.pdf); used instead of the prefix"
      />
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', mb: 2 }}>
        <TextField
          fullWidth
          label="Prefix (Optional)"
          variant="outlined"
          value={prefix}
          onChange={(e) => setPrefix(e.target.value)}
          size="small"
          placeholder="documents/reports/"
          helperText="Optional: folder path prefix within container"
        />
        <Button
          variant="outlined"
          startIcon={<FolderOpenIcon />}
          disabled={!isValid}
          title={isValid ? 'Pick a folder or a blob in the container' : 'Fill in the account URL, container, account name and key first'}
          onClick={() => setBrowseOpen(true)}
          sx={{ whiteSpace: 'nowrap', minWidth: 'auto', height: 40 }}
        >
          Browse…
        </Button>
      </Box>
      <SourceBrowser
        open={browseOpen}
        provider={provider}
        title={`Pick a folder or a file: ${containerName || 'Azure Blob'}`}
        multiple={false}
        onClose={() => setBrowseOpen(false)}
        onSelect={handleBrowsed}
      />
      <TextField
        fullWidth
        label="Account Name"
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
        label="Account Key"
        variant="outlined"
        value={accountKey}
        onChange={(e) => onAccountKeyChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        type="password"
        autoComplete="new-password"
        placeholder="account-key-here"
        helperText="Azure Storage account key (required)"
        required
      />
    </BaseSourceForm>
  );
};
