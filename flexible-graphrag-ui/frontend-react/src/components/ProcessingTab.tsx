import React, { useState, useCallback, useEffect } from 'react';
import {
  Box,
  Typography,
  Button,
  LinearProgress,
  Paper,
  CircularProgress,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Checkbox,
  IconButton,
  Chip,
  Alert,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import CloseIcon from '@mui/icons-material/Close';
import { Theme } from '@mui/material/styles';
import axios from 'axios';
import { 
  IngestRequest, 
  AsyncProcessingResponse, 
  ProcessingStatusResponse,
  FileDisplayInfo 
} from '../types/api';

interface ProcessingTabProps {
  currentTheme: Theme;
  isDarkMode: boolean;
  hasConfiguredSources: boolean;
  configuredDataSource: string;
  configuredFiles: File[];
  folderPath: string;
  cmisConfig?: any;
  alfrescoConfig?: any;
  selectedFileIndices: Set<number>;
  repositoryItemsHidden: boolean;
  // Persistent processing state
  isProcessing: boolean;
  processingStatus: string;
  processingProgress: number;
  currentProcessingId: string | null;
  statusData: any;
  lastStatusData: any;
  onGoToSources: () => void;
  onRemoveProcessingFile: (index: number) => void;
  onRemoveSelectedFiles: () => void;
  onSelectAllFiles: (checked: boolean, totalFiles: number) => void;
  onSelectFile: (index: number, checked: boolean) => void;
  onConfiguredFilesChange: (files: File[]) => void;
  onProcessingStateChange: (isProcessing: boolean) => void;
  onProcessingStatusChange: (status: string) => void;
  onProcessingProgressChange: (progress: number) => void;
  onCurrentProcessingIdChange: (id: string | null) => void;
  onStatusDataChange: (data: any) => void;
  onLastStatusDataChange: (data: any) => void;
  successMessage: string;
  onSuccessMessage: (message: string) => void;
  onError: (message: string) => void;
}

export const ProcessingTab: React.FC<ProcessingTabProps> = ({
  currentTheme,
  isDarkMode,
  hasConfiguredSources,
  configuredDataSource,
  configuredFiles,
  folderPath,
  cmisConfig,
  alfrescoConfig,
  selectedFileIndices,
  repositoryItemsHidden,
  isProcessing,
  processingStatus,
  processingProgress,
  currentProcessingId,
  statusData,
  lastStatusData,
  onGoToSources,
  onRemoveProcessingFile,
  onRemoveSelectedFiles,
  onSelectAllFiles,
  onSelectFile,
  onConfiguredFilesChange,
  onProcessingStateChange,
  onProcessingStatusChange,
  onProcessingProgressChange,
  onCurrentProcessingIdChange,
  onStatusDataChange,
  onLastStatusDataChange,
  successMessage,
  onSuccessMessage,
  onError,
}) => {
  // Local UI state (only for state that doesn't need persistence)
  // Processing state now comes from props for persistence

  // File upload state
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [isUploading, setIsUploading] = useState<boolean>(false);

  // Debug state
  const [showDebugPanel, setShowDebugPanel] = useState<boolean>(false);

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

  // Phase display name
  const getPhaseDisplayName = (phase: string): string => {
    const phaseNames: { [key: string]: string } = {
      'ready': 'Ready',
      'waiting': 'Waiting',
      'docling': 'Converting',
      'chunking': 'Chunking',
      'kg_extraction': 'Extracting Graph',
      'indexing': 'Indexing',
      'completed': 'Completed',
      'error': 'Error'
    };
    return phaseNames[phase] || phase;
  };

  // Generate file entries for display based on data source type
  const getDisplayFiles = (): FileDisplayInfo[] => {
    if (!hasConfiguredSources) return [];
    
    if (configuredDataSource === 'upload') {
      return configuredFiles.map(file => ({
        name: file.name,
        size: file.size,
        type: 'file' as const
      }));
    } else if (configuredDataSource === 'cmis' || configuredDataSource === 'alfresco') {
      // If repository items are explicitly hidden, show nothing
      if (repositoryItemsHidden) {
        return [];
      }
      
      // Only use individual files from status data if we're currently processing
      // or if the processing was for the current repository configuration
      const individualFiles = (isProcessing || currentProcessingId) ? 
        (statusData?.individual_files || lastStatusData?.individual_files || []) : [];
      
      if (individualFiles.length > 0) {
        return individualFiles.map((file: any, index: number) => {
          // Show full path instead of extracting just filename
          const displayName = file.filename || `File ${index + 1}`;
          
          return {
            name: displayName, // Use full path as display name
            size: 0, // Repository files don't have size info
            type: 'repository-file' as const
          };
        });
      }
      // Default to repository path when no individual files yet - show full path
      return [{
        name: folderPath || 'Repository Path',
        size: 0,
        type: 'repository' as const
      }];
    }
    return [];
  };

  // Get file progress data
  const getFileProgressData = (filename: string) => {
    // For repository path placeholder, use overall progress
    const folderName = folderPath.split(/[/\\]/).pop() || folderPath;
    if (filename === folderName || filename === folderPath) {
      return {
        status: isProcessing ? 'processing' : (processingProgress === 100 ? 'completed' : 'ready'),
        progress: processingProgress,
        phase: isProcessing ? 'processing' : (processingProgress === 100 ? 'completed' : 'ready')
      };
    }
    
    const files = statusData?.individual_files || lastStatusData?.individual_files || [];
    
    if (import.meta.env.DEV && files.length > 0) {
      console.log('🔍 Looking for progress data for:', filename);
      console.log('📋 Available progress files:', files.map((f: any) => f.filename));
      console.log('📁 Current display files:', getDisplayFiles().map(f => f.name));
    }
    
    let match = files.find((file: any) => file.filename === filename);
    if (!match) {
      match = files.find((file: any) => {
        const fileBasename = file.filename?.split(/[/\\]/).pop();
        return fileBasename === filename;
      });
    }
    if (!match) {
      match = files.find((file: any) => 
        file.filename?.includes(filename) || filename.includes(file.filename)
      );
    }
    
    if (import.meta.env.DEV) {
      console.log('✅ Progress match for', filename, ':', match ? `Found (${match.progress}% - ${match.phase})` : 'NOT FOUND');
    }
    
    return match;
  };

  // Polling function for processing status
  const pollProcessingStatus = useCallback(async (processingId: string) => {
    try {
      const response = await axios.get<ProcessingStatusResponse>(`/api/processing-status/${processingId}`);
      const status = response.data;
      
      onProcessingStatusChange(status.message);
      onProcessingProgressChange(status.progress);
      onStatusDataChange(status);
      onLastStatusDataChange(status);
      
      console.log('Processing status data:', status);
      localStorage.setItem('lastProcessingStatus', JSON.stringify(status));
      
      if (status.status === 'completed') {
        console.log('FINAL STATUS (COMPLETED):', JSON.stringify(status, null, 2));
        console.log('Individual files data:', status.individual_files);
        onProcessingStateChange(false);
        onProcessingStatusChange(status.message || 'Processing completed');
        onProcessingProgressChange(100); // Keep at 100% to show completion
        onCurrentProcessingIdChange(null);
        onSuccessMessage(status.message || 'Documents ingested successfully!');
      } else if (status.status === 'failed') {
        onProcessingStateChange(false);
        onProcessingStatusChange('');
        onProcessingProgressChange(0);
        onCurrentProcessingIdChange(null);
        onError(status.error || 'Processing failed');
      } else if (status.status === 'cancelled') {
        onProcessingStateChange(false);
        onProcessingStatusChange('Processing cancelled');
        onProcessingProgressChange(0); // 0% for cancelled
        onCurrentProcessingIdChange(null);
        onSuccessMessage('Processing cancelled successfully');
      } else if (status.status === 'started' || status.status === 'processing') {
        setTimeout(() => pollProcessingStatus(processingId), 2000);
      }
    } catch (err) {
      console.error('Error checking processing status:', err);
      onError('Error checking processing status');
      onProcessingStateChange(false);
      onCurrentProcessingIdChange(null);
    }
  }, []);

  // Cancel processing
  const cancelProcessing = async (): Promise<void> => {
    if (!currentProcessingId) return;
    
    try {
      const response = await axios.post(`/api/cancel-processing/${currentProcessingId}`, {});
      
      if (response.data.success) {
        // Success will be handled by the polling status check
      } else {
        onError('Failed to cancel processing');
      }
    } catch (err) {
      console.error('Error cancelling processing:', err);
      const errorMessage = axios.isAxiosError(err)
        ? err.response?.data?.detail || err.response?.data?.error || 'Error cancelling processing'
        : 'An unknown error occurred';
      onError(errorMessage);
    }
  };

  // Upload files (for upload data source)
  const uploadFiles = async (): Promise<string[]> => {
    if (configuredFiles.length === 0) return [];
    
    setIsUploading(true);
    setUploadProgress(0);
    
    try {
      const formData = new FormData();
      configuredFiles.forEach(file => {
        formData.append('files', file);
      });
      
      const response = await axios.post('/api/upload', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setUploadProgress(progress);
          }
        },
      });
      
      if (response.data.success) {
        if (response.data.skipped && response.data.skipped.length > 0) {
          const skippedInfo = response.data.skipped
            .map((file: any) => `${file.filename}: ${file.reason}`)
            .join('\n');
          onError(`Some files were skipped:\n${skippedInfo}`);
        }
        
        // Update configured files with the saved filenames for progress matching
        const uploadedFiles = response.data.files.map((uploadedFile: any) => {
          // Find the original file and create a new file object with the saved filename
          const originalFile = configuredFiles.find((f: File) => f.name === uploadedFile.filename);
          if (originalFile) {
            // Create a new File object with the saved filename
            return new File([originalFile], uploadedFile.saved_as, { type: originalFile.type });
          }
          return originalFile;
        }).filter(Boolean);
        
        // Update the parent's configured files
        onConfiguredFilesChange(uploadedFiles);
        
        return response.data.files.map((file: any) => file.path);
      } else {
        throw new Error('Upload failed');
      }
    } finally {
      setIsUploading(false);
      setUploadProgress(0);
    }
  };

  // Process documents
  const processDocuments = async (): Promise<void> => {
    if (!hasFilesToProcess() || isProcessing) return;
    
    try {
      onProcessingStateChange(true);
      onStatusDataChange(null);
      onLastStatusDataChange(null);
      
      const request: IngestRequest = {
        data_source: configuredDataSource
      };

      if (configuredDataSource === 'upload') {
        const uploadedPaths = await uploadFiles();
        request.paths = uploadedPaths;
        request.data_source = 'filesystem';
      } else if (configuredDataSource === 'cmis') {
        request.paths = [folderPath];
        request.cmis_config = cmisConfig;
      } else if (configuredDataSource === 'alfresco') {
        request.paths = [folderPath];
        request.alfresco_config = alfrescoConfig;
      }

      const response = await axios.post<AsyncProcessingResponse>('/api/ingest', request);
      
      if (response.data.status === 'started') {
        onProcessingStatusChange(response.data.message);
        onProcessingProgressChange(0);
        onCurrentProcessingIdChange(response.data.processing_id);
        onSuccessMessage(`Processing started: ${response.data.estimated_time || 'Please wait...'}`);
        setTimeout(() => pollProcessingStatus(response.data.processing_id), 2000);
      } else if (response.data.status === 'completed') {
        onProcessingStateChange(false);
        onProcessingStatusChange('Processing completed');
        onProcessingProgressChange(100); // Keep at 100% to show completion
        onSuccessMessage('Documents ingested successfully!');
      } else if (response.data.status === 'failed') {
        onProcessingStateChange(false);
        onError(response.data.error || 'Processing failed');
      }
    } catch (err) {
      console.error('Error processing documents:', err);
      const errorMessage = axios.isAxiosError(err)
        ? err.response?.data?.detail || err.response?.data?.error || 'Error processing documents'
        : 'An unknown error occurred';
      onError(errorMessage);
      onProcessingStateChange(false);
      onCurrentProcessingIdChange(null);
    }
  };

  // Check if there are files ready to process
  const hasFilesToProcess = (): boolean => {
    if (!hasConfiguredSources) return false;
    
    if (configuredDataSource === 'upload') {
      return selectedFileIndices.size > 0 && configuredFiles.length > 0;
    } else {
      const displayFiles = getDisplayFiles();
      return displayFiles.length === 0 || selectedFileIndices.size > 0;
    }
  };

  // File table management - now using prop handlers
  const handleSelectAllFiles = (checked: boolean) => {
    onSelectAllFiles(checked, getDisplayFiles().length);
  };

  const handleSelectFile = (index: number, checked: boolean) => {
    onSelectFile(index, checked);
  };

  const removeSelectedFiles = () => {
    onRemoveSelectedFiles();
  };

  const removeProcessingFile = (index: number) => {
    onRemoveProcessingFile(index);
  };

  // Auto-select repository files when they are discovered from processing status
  useEffect(() => {
    if (configuredDataSource === 'cmis' || configuredDataSource === 'alfresco') {
      const displayFiles = getDisplayFiles();
      // Auto-select all files (both repository path and individual files when discovered)
      const newSelection = new Set<number>();
      displayFiles.forEach((_, index) => newSelection.add(index));
      
      // Only update if selection has actually changed
      const currentSelection = Array.from(selectedFileIndices).sort();
      const newSelectionArray = Array.from(newSelection).sort();
      const hasChanged = currentSelection.length !== newSelectionArray.length || 
                        currentSelection.some((val, idx) => val !== newSelectionArray[idx]);
      
      if (hasChanged) {
        // Update selection by calling the individual select handlers
        // First clear all selections
        const currentFiles = getDisplayFiles();
        for (let i = 0; i < currentFiles.length; i++) {
          if (selectedFileIndices.has(i) && !newSelection.has(i)) {
            onSelectFile(i, false);
          }
        }
        // Then add new selections
        for (const index of newSelection) {
          if (!selectedFileIndices.has(index)) {
            onSelectFile(index, true);
          }
        }
      }
    }
  }, [statusData, lastStatusData, configuredDataSource, selectedFileIndices, onSelectFile]);

  // Note: File selection is now handled by parent component

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>
        File Processing
      </Typography>
      
      {/* Show prompt only when not configured */}
      {!hasConfiguredSources && (
        <Paper sx={{ 
          p: 3, 
          mb: 3, 
          textAlign: 'center', 
          bgcolor: isDarkMode ? '#2d2d2d' : currentTheme.palette.primary.light, 
          border: `1px solid ${currentTheme.palette.primary.main}` 
        }}>
          <Typography variant="h6" sx={{ color: currentTheme.palette.text.primary, fontWeight: 600 }} gutterBottom>
            No Data Source Configured
          </Typography>
          <Typography variant="body2" sx={{ color: currentTheme.palette.text.secondary, mb: 2 }}>
            Please go to the Sources tab to configure your data source first.
          </Typography>
          <Button
            variant="outlined"
            onClick={onGoToSources}
            color="primary"
          >
            ← Go to Sources
          </Button>
        </Paper>
      )}
      
      {/* File Table - Show for all configured sources */}
      {hasConfiguredSources && (
        <TableContainer component={Paper} sx={{ mb: 3 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell padding="checkbox" sx={{ width: 50 }}>
                  <Checkbox
                    indeterminate={selectedFileIndices.size > 0 && selectedFileIndices.size < getDisplayFiles().length}
                    checked={getDisplayFiles().length > 0 && selectedFileIndices.size === getDisplayFiles().length}
                    onChange={(e) => handleSelectAllFiles(e.target.checked)}
                  />
                </TableCell>
                <TableCell sx={{ width: 200 }}>Filename</TableCell>
                <TableCell sx={{ width: 100 }}>File Size</TableCell>
                <TableCell sx={{ minWidth: 400 }}>Progress</TableCell>
                <TableCell sx={{ width: 50 }}></TableCell>
                <TableCell sx={{ width: 100 }}>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {getDisplayFiles().map((file, index) => {
                const progressData = getFileProgressData(file.name);
                const isSelected = selectedFileIndices.has(index);
                
                return (
                  <TableRow key={index} selected={isSelected}>
                    <TableCell padding="checkbox">
                      <Checkbox
                        checked={isSelected}
                        onChange={(e) => handleSelectFile(index, e.target.checked)}
                      />
                    </TableCell>
                    <TableCell sx={{ width: '30%' }}>
                      <Typography 
                        variant="body2" 
                        title={file.name}
                        sx={{ 
                          wordBreak: 'break-all', 
                          lineHeight: 1.2,
                          whiteSpace: 'normal'
                        }}
                      >
                        {file.name}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">
                        {file.size > 0 ? formatFileSize(file.size) : 
                         file.type === 'path' ? 'Folder' : 
                         file.type === 'repository' ? 'Repository' : '-'}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                        <Box sx={{ flex: 1, mr: 1 }}>
                          <Box
                            sx={{
                              width: '100%',
                              height: 8,
                              borderRadius: 4,
                              backgroundColor: currentTheme.palette.action.hover,
                              position: 'relative',
                              overflow: 'hidden'
                            }}
                          >
                            <Box
                              sx={{
                                width: `${Math.max(progressData?.progress || 0, 2)}%`,
                                height: '100%',
                                backgroundColor: currentTheme.palette.primary.main,
                                borderRadius: 4,
                                transition: 'width 0.3s ease'
                              }}
                            />
                          </Box>
                        </Box>
                        <Typography variant="caption" sx={{ flex: 'none', whiteSpace: 'nowrap', color: currentTheme.palette.text.primary }}>
                          {progressData?.progress || 0}% - {getPhaseDisplayName(progressData?.phase || 'ready')}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <IconButton
                        size="small"
                        onClick={() => removeProcessingFile(index)}
                        color="error"
                      >
                        <CloseIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={progressData?.status || 'ready'}
                        size="small"
                        color={
                          progressData?.status === 'completed' ? 'success' :
                          progressData?.status === 'failed' ? 'error' :
                          progressData?.status === 'processing' ? 'primary' : 'default'
                        }
                      />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      
      {/* Upload Progress */}
      {isUploading && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="body2" gutterBottom>
            Uploading files... {uploadProgress}%
          </Typography>
          <LinearProgress variant="determinate" value={uploadProgress} />
        </Box>
      )}
      
      {/* Processing Status */}
      {isProcessing && (
        <Box sx={{ mb: 2 }}>
          <Box display="flex" alignItems="center" justifyContent="space-between" mb={2}>
            <Box display="flex" alignItems="center">
              <CircularProgress size={20} sx={{ mr: 1 }} />
              <Typography variant="body2">
                {processingStatus || 'Processing documents...'}
              </Typography>
            </Box>
            <Button 
              variant="outlined" 
              color="error" 
              size="small" 
              onClick={cancelProcessing}
              disabled={!currentProcessingId}
            >
              Cancel
            </Button>
          </Box>
          
          <Box sx={{ mb: 2 }}>
            <LinearProgress 
              variant="determinate" 
              value={processingProgress} 
              sx={{ mb: 1 }} 
            />
            <Typography variant="caption" color="text.secondary">
              Overall Progress: {processingProgress}% complete
              {statusData?.estimated_time_remaining && (
                <span> • Est. time remaining: {statusData.estimated_time_remaining}</span>
              )}
            </Typography>
          </Box>
        </Box>
      )}
      
      {/* Action Buttons */}
      <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
        <Button
          variant="contained"
          onClick={processDocuments}
          disabled={!hasConfiguredSources || isProcessing || !hasFilesToProcess()}
          sx={{ minWidth: 200 }}
        >
          {isProcessing ? 'Processing...' : 
           !hasConfiguredSources ? 'Configure Sources First' :
           !hasFilesToProcess() ? 'Select Files to Process' :
           'Start Processing'}
        </Button>
        
        {selectedFileIndices.size > 0 && getDisplayFiles().length > 0 && (
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteIcon />}
            onClick={removeSelectedFiles}
          >
            Remove Selected ({selectedFileIndices.size})
          </Button>
        )}
        
        {/* Debug toggle */}
        <Button
          variant="text"
          size="small"
          onDoubleClick={() => setShowDebugPanel(!showDebugPanel)}
          sx={{ 
            minWidth: 'auto', 
            color: 'transparent',
            '&:hover': { color: currentTheme.palette.text.secondary }
          }}
          title="Double-click to toggle debug panel"
        >
          🔧
        </Button>
      </Box>
      
      {/* Success Message */}
      {successMessage && (
        <Alert severity="success" sx={{ mt: 2 }}>
          {successMessage}
        </Alert>
      )}
      
      {/* Debug Panel */}
      {showDebugPanel && (statusData || isProcessing || lastStatusData) && (
        <Box sx={{ 
          mt: 2, 
          p: 2, 
          bgcolor: isDarkMode ? '#2d3748' : '#f5f5f5', 
          border: `1px solid ${currentTheme.palette.divider}`,
          borderRadius: 1,
          fontSize: '0.8rem', 
          fontFamily: 'monospace',
          color: currentTheme.palette.text.primary
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <strong>Debug Status Data {!statusData && lastStatusData ? '(LAST STATUS)' : '(CURRENT)'}:</strong>
            <button 
              onClick={() => {
                const saved = localStorage.getItem('lastProcessingStatus');
                if (saved) {
                  const parsed = JSON.parse(saved);
                  onLastStatusDataChange(parsed);
                  console.log('Retrieved from localStorage:', parsed);
                } else {
                  console.log('No saved status found in localStorage');
                }
              }}
              style={{ 
                fontSize: '0.7rem', 
                padding: '2px 6px', 
                backgroundColor: currentTheme.palette.action.hover, 
                color: currentTheme.palette.text.primary, 
                border: `1px solid ${currentTheme.palette.divider}`,
                borderRadius: '3px',
                cursor: 'pointer'
              }}
            >
              Load Last
            </button>
          </div>
          <pre style={{ 
            fontSize: '0.7rem', 
            margin: '4px 0', 
            backgroundColor: isDarkMode ? '#1a202c' : '#ffffff',
            color: currentTheme.palette.text.primary,
            padding: '8px',
            borderRadius: '4px',
            overflow: 'auto',
            maxHeight: '200px'
          }}>
            {JSON.stringify(statusData || lastStatusData, null, 2)}
          </pre>
        </Box>
      )}

    </Box>
  );
};
