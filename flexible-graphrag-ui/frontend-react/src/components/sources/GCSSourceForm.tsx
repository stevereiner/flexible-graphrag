import React, { useEffect, useMemo, useRef, useState } from 'react';
import { TextField, Box, Button } from '@mui/material';
import { FolderOpen as FolderOpenIcon } from '@mui/icons-material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { SourceBrowser } from '../../browser/SourceBrowser';
import { remoteProvider } from '../../browser/RemoteProvider';
import { BrowseItem } from '../../browser/types';

interface GCSSourceFormProps extends BaseSourceFormProps {
  bucketName: string;
  credentials: string;
  prefix?: string;
  pubsubSubscription?: string;
  onBucketNameChange: (bucketName: string) => void;
  onCredentialsChange: (credentials: string) => void;
  onPrefixChange?: (prefix: string) => void;
  onPubsubSubscriptionChange?: (subscription: string) => void;
}

export const GCSSourceForm: React.FC<GCSSourceFormProps> = ({
  currentTheme,
  bucketName,
  credentials,
  prefix: initialPrefix = '',
  pubsubSubscription: initialPubsubSubscription = '',
  onBucketNameChange,
  onCredentialsChange,
  onPrefixChange,
  onPubsubSubscriptionChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [prefix, setPrefix] = useState(initialPrefix);
  const [pubsubSubscription, setPubsubSubscription] = useState(initialPubsubSubscription);

  // Sync local state with props when they change
  useEffect(() => {
    setPrefix(initialPrefix);
  }, [initialPrefix]);

  useEffect(() => {
    setPubsubSubscription(initialPubsubSubscription);
  }, [initialPubsubSubscription]);

  const handlePrefixChange = (value: string) => {
    setPrefix(value);
    if (onPrefixChange) {
      onPrefixChange(value);
    }
  };

  const handlePubsubSubscriptionChange = (value: string) => {
    setPubsubSubscription(value);
    if (onPubsubSubscriptionChange) {
      onPubsubSubscriptionChange(value);
    }
  };

  const isValid = useMemo(() => {
    return bucketName.trim() !== '' && credentials.trim() !== '';
  }, [bucketName, credentials]);

  const config = useMemo(() => ({
    bucket_name: bucketName,
    credentials: credentials,
    prefix: prefix || undefined,
    pubsub_subscription: pubsubSubscription || undefined
  }), [bucketName, credentials, prefix, pubsubSubscription]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  // Browse the bucket with the credentials below (POST /api/browse)
  const [browseOpen, setBrowseOpen] = useState(false);
  const configRef = useRef(config);
  configRef.current = config;
  const provider = useMemo(() => remoteProvider('gcs', 'GCS bucket', () => configRef.current), []);

  // a folder's prefix ("docs/2024/"): the ingest reads a prefix as a folder
  const handleBrowsed = (items: BrowseItem[]) => {
    if (items.length) handlePrefixChange(items[0].path || items[0].id);
  };

  return (
    <BaseSourceForm
      title="Google Cloud Storage"
      description="Connect to Google Cloud Storage buckets"
    >
      <TextField
        fullWidth
        label="Bucket Name"
        required
        variant="outlined"
        value={bucketName}
        onChange={(e) => onBucketNameChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="my-gcs-bucket"
      />
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', mb: 2 }}>
        <TextField
          fullWidth
          label="Prefix/Path (Optional)"
          variant="outlined"
          value={prefix}
          onChange={(e) => handlePrefixChange(e.target.value)}
          size="small"
          placeholder="sample-docs/"
          helperText="Optional: folder path prefix (e.g., 'sample-docs/' for a specific folder)"
        />
        <Button
          variant="outlined"
          startIcon={<FolderOpenIcon />}
          disabled={!isValid}
          title={isValid ? 'Pick a folder in the bucket' : 'Fill in the bucket and the credentials first'}
          onClick={() => setBrowseOpen(true)}
          sx={{ whiteSpace: 'nowrap', minWidth: 'auto', height: 40 }}
        >
          Browse…
        </Button>
      </Box>
      <SourceBrowser
        open={browseOpen}
        provider={provider}
        title={`Pick a folder: gs://${bucketName}`}
        files={false}
        multiple={false}
        onClose={() => setBrowseOpen(false)}
        onSelect={handleBrowsed}
      />
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
        helperText="Paste your GCS service account JSON credentials (includes project_id)"
      />
      <TextField
        fullWidth
        label="Pub/Sub Subscription (Optional)"
        variant="outlined"
        value={pubsubSubscription}
        onChange={(e) => handlePubsubSubscriptionChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="gcs-notifications-sub"
        helperText="Pub/Sub subscription name for real-time change detection (leave empty for periodic polling)"
      />
    </BaseSourceForm>
  );
};
