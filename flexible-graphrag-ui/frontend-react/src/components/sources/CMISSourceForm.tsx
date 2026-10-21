import React, { useEffect, useMemo } from 'react';
import { TextField, Box } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';
import { SourceSignInSection, useSourceSession } from '../../auth/SourceSignInSection';

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
      <TextField
        fullWidth
        label="Folder Path"
        required
        variant="outlined"
        value={folderPath}
        onChange={(e) => onFolderPathChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="e.g., /Sites/example/documentLibrary"
      />
    </BaseSourceForm>
  );
};
