import React, { useEffect, useMemo } from 'react';
import { TextField, Box } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

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

  const isValid = useMemo(() => {
    return folderPath.trim() !== '' && 
           url.trim() !== '' && 
           username.trim() !== '' && 
           password.trim() !== '';
  }, [folderPath, url, username, password]);

  const config = useMemo(() => ({
    url,
    username,
    password,
    folder_path: folderPath
  }), [url, username, password, folderPath]);

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
        variant="outlined"
        value={url}
        onChange={(e) => onUrlChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder={placeholder}
      />
      <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
        <TextField
          fullWidth
          label="Username"
          variant="outlined"
          value={username}
          onChange={(e) => onUsernameChange(e.target.value)}
          size="small"
        />
        <TextField
          fullWidth
          label="Password"
          type="password"
          variant="outlined"
          value={password}
          onChange={(e) => onPasswordChange(e.target.value)}
          size="small"
        />
      </Box>
      <TextField
        fullWidth
        label="Folder Path"
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
