import React, { useEffect, useMemo } from 'react';
import { TextField, Box } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface AlfrescoSourceFormProps extends BaseSourceFormProps {
  url: string;
  username: string;
  password: string;
  path: string;
  onUrlChange: (url: string) => void;
  onUsernameChange: (username: string) => void;
  onPasswordChange: (password: string) => void;
  onPathChange: (path: string) => void;
}

export const AlfrescoSourceForm: React.FC<AlfrescoSourceFormProps> = ({
  currentTheme,
  url,
  username,
  password,
  path,
  onUrlChange,
  onUsernameChange,
  onPasswordChange,
  onPathChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const placeholder = useMemo(() => {
    const baseUrl = import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco`;
  }, []);

  const isValid = useMemo(() => {
    return path.trim() !== '' && 
           url.trim() !== '' && 
           username.trim() !== '' && 
           password.trim() !== '';
  }, [path, url, username, password]);

  const config = useMemo(() => ({
    url,
    username,
    password,
    path
  }), [url, username, password, path]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Alfresco Repository"
      description="Connect to an Alfresco content management system"
    >
      <TextField
        fullWidth
        label="Alfresco Base URL"
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
        label="Path"
        variant="outlined"
        value={path}
        onChange={(e) => onPathChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="e.g., /Sites/example/documentLibrary"
      />
    </BaseSourceForm>
  );
};
