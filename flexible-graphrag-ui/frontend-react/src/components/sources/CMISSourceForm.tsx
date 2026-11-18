import React, { useEffect, useMemo, useRef, useState } from 'react';
import { TextField, Box, Button } from '@mui/material';
import { FolderOpen as FolderOpenIcon } from '@mui/icons-material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { SourceSignInSection, useSourceSession } from '../../auth/SourceSignInSection';
import { SourceBrowser } from '../../browser/SourceBrowser';
import { remoteProvider } from '../../browser/RemoteProvider';
import { BrowseItem } from '../../browser/types';

interface CMISSourceFormProps extends BaseSourceFormProps {
  url: string;
  username: string;
  password: string;
  folderPath: string;
  onUrlChange: (url: string) => void;
  onUsernameChange: (username: string) => void;
  onPasswordChange: (password: string) => void;
  onFolderPathChange: (folderPath: string) => void;
}

export const CMISSourceForm: React.FC<CMISSourceFormProps> = ({
  currentTheme,
  url,
  username,
  password,
  folderPath,
  onUrlChange,
  onUsernameChange,
  onPasswordChange,
  onFolderPathChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const placeholder = useMemo(() => {
    const baseUrl = import.meta.env.VITE_CMIS_BASE_URL || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  }, []);

  // The CMIS sign-in (header / dialog): for an Alfresco or Nuxeo CMIS server it holds that
  // vendor's ticket / token, which the ingest then uses instead of a password.
  const { session, useOther, setUseOther, usingSignIn, credential } = useSourceSession('cmis', url);

  const isValid = useMemo(() => {
    if (folderPath.trim() === '' || url.trim() === '') return false;
    if (usingSignIn) return true;
    return username.trim() !== '' && password.trim() !== '';
  }, [folderPath, url, usingSignIn, username, password]);

  const config = useMemo(() => (
    usingSignIn && credential
      ? { url, folder_path: folderPath, ...credential }
      : { url, username, password, folder_path: folderPath }
  ), [url, usingSignIn, credential, username, password, folderPath]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  // Browse the repository as the ingest signs in (POST /api/browse): needs the URL and a sign-in,
  // not yet a folder path
  const canBrowse = url.trim() !== '' && (usingSignIn || (username.trim() !== '' && password.trim() !== ''));
  const [browseOpen, setBrowseOpen] = useState(false);
  const configRef = useRef(config);
  configRef.current = config;
  const provider = useMemo(() => remoteProvider('cmis', 'CMIS repository', () => configRef.current), []);

  // one folder, or one document: folder_path takes either
  const handleBrowsed = (items: BrowseItem[]) => {
    if (items.length) onFolderPathChange(items[0].path || `/${items[0].name}`);
  };

  return (
    <BaseSourceForm
      title="CMIS Repository"
      description="Connect to any CMIS-compliant content management system"
    >
      <TextField
        fullWidth
        label="CMIS Repository URL"
        required
        variant="outlined"
        value={url}
        onChange={(e) => onUrlChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder={placeholder}
      />
      <SourceSignInSection
        source="cmis" url={url} session={session} usingSignIn={usingSignIn}
        useOther={useOther} onUseOtherChange={setUseOther}
      />
      {!usingSignIn && (
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          fullWidth
          autoComplete="off"
        label="Username"
        required
          variant="outlined"
          value={username}
          onChange={(e) => onUsernameChange(e.target.value)}
          size="small"
        />
        <TextField
          fullWidth
          label="Password"
          required
          type="password"
        autoComplete="new-password"
          variant="outlined"
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          size="small"
        />
      </Box>
      )}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start', mb: 2 }}>
        <TextField
          fullWidth
          label="Folder Path"
          required
          variant="outlined"
          value={folderPath}
          onChange={(e) => onFolderPathChange(e.target.value)}
          size="small"
          placeholder="e.g., /Sites/example/documentLibrary"
          helperText="A folder (all its subfolders are read), or one document's path"
        />
        <Button
          variant="outlined"
          startIcon={<FolderOpenIcon />}
          disabled={!canBrowse}
          title={canBrowse ? 'Pick a folder or a document in the repository' : 'Fill in the URL and sign in (or a username and password) first'}
          onClick={() => setBrowseOpen(true)}
          sx={{ whiteSpace: 'nowrap', minWidth: 'auto', height: 40 }}
        >
          Browse…
        </Button>
      </Box>
      <SourceBrowser
        open={browseOpen}
        provider={provider}
        title="Pick a folder or a document: CMIS"
        multiple={false}
        onClose={() => setBrowseOpen(false)}
        onSelect={handleBrowsed}
      />
    </BaseSourceForm>
  );
};
