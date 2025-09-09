import React, { useState, useMemo, useCallback } from 'react';
import {
  Box,
  Typography,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import { Theme } from '@mui/material/styles';

interface SourcesTabProps {
  currentTheme: Theme;
  dataSource: string;
  selectedFiles: File[];
  folderPath: string;
  cmisUrl: string;
  cmisUsername: string;
  cmisPassword: string;
  alfrescoUrl: string;
  alfrescoUsername: string;
  alfrescoPassword: string;
  onDataSourceChange: (dataSource: string) => void;
  onSelectedFilesChange: (files: File[]) => void;
  onFolderPathChange: (folderPath: string) => void;
  onCmisUrlChange: (url: string) => void;
  onCmisUsernameChange: (username: string) => void;
  onCmisPasswordChange: (password: string) => void;
  onAlfrescoUrlChange: (url: string) => void;
  onAlfrescoUsernameChange: (username: string) => void;
  onAlfrescoPasswordChange: (password: string) => void;
  onConfigureProcessing: () => void;
  onSourcesConfigured: (data: {
    dataSource: string;
    files: File[];
    folderPath: string;
    cmisConfig?: any;
    alfrescoConfig?: any;
  }) => void;
}

export const SourcesTab: React.FC<SourcesTabProps> = ({ 
  currentTheme,
  dataSource,
  selectedFiles,
  folderPath,
  cmisUrl,
  cmisUsername,
  cmisPassword,
  alfrescoUrl,
  alfrescoUsername,
  alfrescoPassword,
  onDataSourceChange,
  onSelectedFilesChange,
  onFolderPathChange,
  onCmisUrlChange,
  onCmisUsernameChange,
  onCmisPasswordChange,
  onAlfrescoUrlChange,
  onAlfrescoUsernameChange,
  onAlfrescoPasswordChange,
  onConfigureProcessing, 
  onSourcesConfigured 
}) => {
  // Local state (only for UI-specific state that doesn't need persistence)
  const [isDragOver, setIsDragOver] = useState<boolean>(false);

  // Memoized placeholder values
  const cmisPlaceholder = useMemo(() => {
    const baseUrl = import.meta.env.VITE_CMIS_BASE_URL || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  }, []);

  const alfrescoPlaceholder = useMemo(() => {
    const baseUrl = import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco`;
  }, []);

  // Form validation
  const isFormValid = useCallback((): boolean => {
    switch (dataSource) {
      case 'upload':
        return selectedFiles.length > 0;
      case 'cmis':
        return folderPath.trim() !== '' && 
               cmisUrl.trim() !== '' && 
               cmisUsername.trim() !== '' && 
               cmisPassword.trim() !== '';
      case 'alfresco':
        return folderPath.trim() !== '' && 
               alfrescoUrl.trim() !== '' && 
               alfrescoUsername.trim() !== '' && 
               alfrescoPassword.trim() !== '';
      default:
        return false;
    }
  }, [dataSource, selectedFiles.length, folderPath, cmisUrl, cmisUsername, cmisPassword, alfrescoUrl, alfrescoUsername, alfrescoPassword]);

  // File size formatting
  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) {
      return bytes === 0 ? "0 B" : "1 KB";
    } else if (bytes < 1024 * 1024) {
      return `${Math.ceil(bytes / 1024)} KB`;
    } else {
      return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    }
  };

  // File handling
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files) {
      // Use requestAnimationFrame to defer processing and improve perceived performance
      requestAnimationFrame(() => {
        const fileArray = Array.from(files);
        onSelectedFilesChange(fileArray);
        // Clear the input value only after successful processing to allow re-selecting same files
        event.target.value = '';
      });
    }
  };

  const handleFileDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragOver(false);
    
    const files = event.dataTransfer.files;
    if (files) {
      // Use requestAnimationFrame for consistency with file dialog
      requestAnimationFrame(() => {
        const fileArray = Array.from(files);
        onSelectedFilesChange(fileArray);
      });
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  };

  const handleDragEnter = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragOver(true);
    
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  };

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX;
    const y = event.clientY;
    
    if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
      setIsDragOver(false);
    }
  };

  const removeFile = (index: number) => {
    onSelectedFilesChange(selectedFiles.filter((_, i) => i !== index));
  };

  const handleConfigureProcessing = () => {
    const configData = {
      dataSource,
      files: selectedFiles,
      folderPath,
      cmisConfig: dataSource === 'cmis' ? {
        url: cmisUrl,
        username: cmisUsername,
        password: cmisPassword,
        folder_path: folderPath
      } : undefined,
      alfrescoConfig: dataSource === 'alfresco' ? {
        url: alfrescoUrl,
        username: alfrescoUsername,
        password: alfrescoPassword,
        path: folderPath
      } : undefined
    };
    
    onSourcesConfigured(configData);
    onConfigureProcessing();
  };

  const renderDataSourceFields = () => {
    switch (dataSource) {
      case 'upload':
        return (
          <Box sx={{ mb: 2 }}>
            <Box
              sx={{
                border: isDragOver ? '2px solid #ffffff' : '2px dashed #ffffff',
                borderRadius: 2,
                p: 3,
                textAlign: 'center',
                cursor: 'pointer',
                backgroundColor: isDragOver ? '#000000' : '#1976d2', // Black on hover, blue default like Vue
                transition: 'all 0.2s ease-in-out',
              }}
              onDrop={handleFileDrop}
              onDragOver={handleDragOver}
              onDragEnter={handleDragEnter}
              onDragLeave={handleDragLeave}
              onClick={() => document.getElementById('file-input')?.click()}
            >
              <Typography variant="h6" gutterBottom sx={{ color: '#ffffff' }}>
                Drop files here or click to select
              </Typography>
              <Typography variant="body2" sx={{ color: '#ffffff' }}>
                Supports: PDF, DOCX, XLSX, PPTX, TXT, MD, HTML, CSV, PNG, JPG
              </Typography>
              <input
                id="file-input"
                type="file"
                multiple
                accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.html,.csv,.png,.jpg,.jpeg"
                onChange={handleFileSelect}
                aria-label="Select files to upload"
                style={{ display: 'none' }}
              />
            </Box>
            
            {selectedFiles.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Selected Files ({selectedFiles.length}):
                </Typography>
                {selectedFiles.map((file, index) => (
                  <Box key={index} sx={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'space-between',
                    p: 1,
                    border: `1px solid ${currentTheme.palette.divider}`,
                    borderRadius: 1,
                    mb: 1
                  }}>
                    <Box>
                      <Typography variant="body2">{file.name}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {formatFileSize(file.size)}
                      </Typography>
                    </Box>
                    <Button
                      size="small"
                      color="error"
                      onClick={() => removeFile(index)}
                    >
                      Remove
                    </Button>
                  </Box>
                ))}
              </Box>
            )}
          </Box>
        );
      
      case 'cmis':
        return (
          <>
            <TextField
              fullWidth
              label="CMIS Repository URL"
              variant="outlined"
              value={cmisUrl}
              onChange={(e) => onCmisUrlChange(e.target.value)}
              size="small"
              sx={{ mb: 2 }}
              placeholder={cmisPlaceholder}
            />
            <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
              <TextField
                fullWidth
                label="Username"
                variant="outlined"
                value={cmisUsername}
                onChange={(e) => onCmisUsernameChange(e.target.value)}
                size="small"
              />
              <TextField
                fullWidth
                label="Password"
                type="password"
                variant="outlined"
                value={cmisPassword}
                onChange={(e) => onCmisPasswordChange(e.target.value)}
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
          </>
        );
      
      case 'alfresco':
        return (
          <>
            <TextField
              fullWidth
              label="Alfresco Base URL"
              variant="outlined"
              value={alfrescoUrl}
              onChange={(e) => onAlfrescoUrlChange(e.target.value)}
              size="small"
              sx={{ mb: 2 }}
              placeholder={alfrescoPlaceholder}
            />
            <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
              <TextField
                fullWidth
                label="Username"
                variant="outlined"
                value={alfrescoUsername}
                onChange={(e) => onAlfrescoUsernameChange(e.target.value)}
                size="small"
              />
              <TextField
                fullWidth
                label="Password"
                type="password"
                variant="outlined"
                value={alfrescoPassword}
                onChange={(e) => onAlfrescoPasswordChange(e.target.value)}
                size="small"
              />
            </Box>
            <TextField
              fullWidth
              label="Path"
              variant="outlined"
              value={folderPath}
              onChange={(e) => onFolderPathChange(e.target.value)}
              size="small"
              sx={{ mb: 2 }}
              placeholder="e.g., /Sites/example/documentLibrary"
            />
          </>
        );
      
      default:
        return null;
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        Data Source Configuration
      </Typography>
      
      <FormControl fullWidth sx={{ mb: 2 }}>
        <InputLabel>Data Source</InputLabel>
        <Select
          value={dataSource}
          label="Data Source"
          onChange={(e) => onDataSourceChange(e.target.value)}
          size="small"
        >
          <MenuItem value="upload">File Upload</MenuItem>
          <MenuItem value="alfresco">Alfresco Repository</MenuItem>
          <MenuItem value="cmis">CMIS Repository</MenuItem>
        </Select>
      </FormControl>
      
      {renderDataSourceFields()}
      
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 2 }}>
        <Button
          variant="contained"
          onClick={handleConfigureProcessing}
          disabled={!isFormValid()}
          sx={{ minWidth: 200 }}
        >
          Configure Processing →
        </Button>
      </Box>
    </Box>
  );
};
