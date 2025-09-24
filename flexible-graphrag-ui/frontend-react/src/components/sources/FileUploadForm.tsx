import React, { useState, useEffect, useMemo } from 'react';
import { Box, Typography, Button } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface FileUploadFormProps extends BaseSourceFormProps {
  selectedFiles: File[];
  onSelectedFilesChange: (files: File[]) => void;
}

export const FileUploadForm: React.FC<FileUploadFormProps> = ({
  currentTheme,
  selectedFiles,
  onSelectedFilesChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const [isDragOver, setIsDragOver] = useState<boolean>(false);

  const isValid = useMemo(() => {
    return selectedFiles.length > 0;
  }, [selectedFiles.length]);

  const config = useMemo(() => ({
    files: selectedFiles
  }), [selectedFiles]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

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
      requestAnimationFrame(() => {
        const fileArray = Array.from(files);
        onSelectedFilesChange(fileArray);
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

  return (
    <BaseSourceForm
      title="File Upload"
      description="Upload documents directly from your computer"
    >
      <Box
        sx={{
          border: isDragOver ? '2px solid #ffffff' : '2px dashed #ffffff',
          borderRadius: 2,
          p: 3,
          textAlign: 'center',
          cursor: 'pointer',
          backgroundColor: isDragOver ? '#000000' : '#1976d2',
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
    </BaseSourceForm>
  );
};
