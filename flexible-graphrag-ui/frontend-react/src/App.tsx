import React, { useState, useEffect } from 'react';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import Container from '@mui/material/Container';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import Paper from '@mui/material/Paper';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import TabPanel from '@mui/lab/TabPanel';
import TabContext from '@mui/lab/TabContext';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import Switch from '@mui/material/Switch';
import FormControlLabel from '@mui/material/FormControlLabel';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import Alert from '@mui/material/Alert';

import { SourcesTab, ProcessingTab, SearchTab, ChatTab } from './components';
import { ChatMessage } from './types/api';

// Theme definitions
const lightTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
      light: '#e3f2fd',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#dc004e',
    },
    success: {
      main: '#4caf50',
    },
    background: {
      default: '#fafafa',
      paper: '#ffffff',
    },
    text: {
      primary: '#333333',
      secondary: '#555555',
    },
    divider: '#e0e0e0',
    action: {
      hover: '#f5f5f5',
    },
  },
});

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#1976d2',
      light: '#42a5f5',
      contrastText: '#ffffff',
    },
    secondary: {
      main: '#dc004e',
    },
    success: {
      main: '#4caf50',
    },
    background: {
      default: '#121212',
      paper: '#1e1e1e',
    },
    text: {
      primary: '#ffffff',
      secondary: '#cccccc',
    },
    divider: '#424242',
    action: {
      hover: '#2d2d2d',
    },
  },
});

const App: React.FC = () => {
  // Theme state
  const [isDarkMode, setIsDarkMode] = useState<boolean>(() => {
    const saved = localStorage.getItem('theme-mode');
    return saved ? saved === 'dark' : true; // Default to dark mode like current
  });

  // Update localStorage when theme changes
  useEffect(() => {
    localStorage.setItem('theme-mode', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  const currentTheme = isDarkMode ? darkTheme : lightTheme;

  // Main tab state
  const [mainTab, setMainTab] = useState<string>('sources');
  
  // Global error state
  const [error, setError] = useState<string>('');

  // Sources configuration state
  const [dataSource, setDataSource] = useState<string>('upload');
  const [hasConfiguredSources, setHasConfiguredSources] = useState<boolean>(false);
  const [configuredDataSource, setConfiguredDataSource] = useState<string>('');
  const [configuredFiles, setConfiguredFiles] = useState<File[]>([]);
  const [folderPath, setFolderPath] = useState<string>('');
  const [cmisConfig, setCmisConfig] = useState<any>(null);
  const [alfrescoConfig, setAlfrescoConfig] = useState<any>(null);
  
  // File selection state for processing tab
  const [selectedFileIndices, setSelectedFileIndices] = useState<Set<number>>(new Set());
  const [repositoryItemsHidden, setRepositoryItemsHidden] = useState(false);
  
  // Success message state
  const [successMessage, setSuccessMessage] = useState<string>('');

  // PERSISTENT STATE - Sources Tab (prevents data loss on tab navigation)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [sourcesfolderPath, setSourcesFolderPath] = useState<string>(import.meta.env.VITE_PROCESS_FOLDER_PATH || '/Shared/GraphRAG');
  const [cmisUrl, setCmisUrl] = useState<string>(`${import.meta.env.VITE_CMIS_BASE_URL || 'http://localhost:8080'}/alfresco/api/-default-/public/cmis/versions/1.1/atom`);
  const [cmisUsername, setCmisUsername] = useState<string>('admin');
  const [cmisPassword, setCmisPassword] = useState<string>('admin');
  const [alfrescoUrl, setAlfrescoUrl] = useState<string>(`${import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080'}/alfresco`);
  const [alfrescoUsername, setAlfrescoUsername] = useState<string>('admin');
  const [alfrescoPassword, setAlfrescoPassword] = useState<string>('admin');
  
  // PERSISTENT STATE - Web Sources
  const [webUrl, setWebUrl] = useState<string>('');
  const [wikipediaUrl, setWikipediaUrl] = useState<string>('');
  const [youtubeUrl, setYoutubeUrl] = useState<string>('');
  
  // PERSISTENT STATE - Cloud Storage
  const [s3AccessKey, setS3AccessKey] = useState<string>('');
  const [s3SecretKey, setS3SecretKey] = useState<string>('');
  const [gcsBucketName, setGcsBucketName] = useState<string>('');
  const [gcsCredentials, setGcsCredentials] = useState<string>('');
  const [azureBlobConnectionString, setAzureBlobConnectionString] = useState<string>('');
  const [azureBlobContainer, setAzureBlobContainer] = useState<string>('');
  const [azureBlobName, setAzureBlobName] = useState<string>('');
  const [azureBlobAccountName, setAzureBlobAccountName] = useState<string>('');
  const [azureBlobAccountKey, setAzureBlobAccountKey] = useState<string>('');
  
  // PERSISTENT STATE - Enterprise Sources
  const [onedriveUserPrincipalName, setOnedriveUserPrincipalName] = useState<string>('');
  const [onedriveClientId, setOnedriveClientId] = useState<string>('');
  const [onedriveClientSecret, setOnedriveClientSecret] = useState<string>('');
  const [onedriveTenantId, setOnedriveTenantId] = useState<string>('');
  const [sharepointSiteName, setSharepointSiteName] = useState<string>('');  // Changed from sharepointSiteUrl
  const [boxClientId, setBoxClientId] = useState<string>('');
  const [boxClientSecret, setBoxClientSecret] = useState<string>('');
  const [boxDeveloperToken, setBoxDeveloperToken] = useState<string>('');
  const [boxUserId, setBoxUserId] = useState<string>('');
  const [boxEnterpriseId, setBoxEnterpriseId] = useState<string>('');
  const [googleDriveCredentials, setGoogleDriveCredentials] = useState<string>('');

  // PERSISTENT STATE - New Data Source Configs
  const [webConfig, setWebConfig] = useState<any>(null);
  const [wikipediaConfig, setWikipediaConfig] = useState<any>(null);
  const [youtubeConfig, setYoutubeConfig] = useState<any>(null);
  const [cloudConfig, setCloudConfig] = useState<any>(null);
  const [enterpriseConfig, setEnterpriseConfig] = useState<any>(null);

  // PERSISTENT STATE - Processing Tab (prevents loss of processing info)
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [processingStatus, setProcessingStatus] = useState<string>('');
  const [processingProgress, setProcessingProgress] = useState<number>(0);
  const [currentProcessingId, setCurrentProcessingId] = useState<string | null>(null);
  const [statusData, setStatusData] = useState<any>(null);
  const [lastStatusData, setLastStatusData] = useState<any>(null);

  // PERSISTENT STATE - Search Tab (prevents loss of search data)
  const [searchActiveTab, setSearchActiveTab] = useState<string>('search');
  const [searchQuestion, setSearchQuestion] = useState<string>('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [qaAnswer, setQaAnswer] = useState<string>('');
  const [hasSearched, setHasSearched] = useState<boolean>(false);
  const [lastSearchQuery, setLastSearchQuery] = useState<string>('');
  const [isQuerying, setIsQuerying] = useState<boolean>(false);

  // PERSISTENT STATE - Chat Tab (prevents loss of conversation history)
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState<string>('');
  const [isChatQuerying, setIsChatQuerying] = useState<boolean>(false);

  // Clear messages when data source changes (CRITICAL - was missing!)
  useEffect(() => {
    setError('');
    setSuccessMessage('');
    setHasConfiguredSources(false); // Reset configuration flag when data source changes
    setConfiguredDataSource(''); // Reset configured data source
    setConfiguredFiles([]); // Reset configured files
    setSelectedFileIndices(new Set()); // Reset file selections
    setSelectedFiles([]); // Clear selected files when switching data sources
    
    // Clear processing status and progress when switching data sources
    setIsProcessing(false);
    setProcessingStatus('');
    setProcessingProgress(0);
    setCurrentProcessingId(null);
    setStatusData(null);
    setLastStatusData(null);
    
    // Note: Preserve form field values (cmisUrl, credentials, etc.) so users don't have to retype
  }, [dataSource]);

  // Handle data source change
  const handleDataSourceChange = (newDataSource: string) => {
    setDataSource(newDataSource);
  };

  // Handle sources configuration
  const handleSourcesConfigured = (data: {
    dataSource: string;
    files: File[];
    folderPath: string;
    cmisConfig?: any;
    alfrescoConfig?: any;
    webConfig?: any;
    wikipediaConfig?: any;
    youtubeConfig?: any;
    cloudConfig?: any;
    enterpriseConfig?: any;
  }) => {
    setDataSource(data.dataSource); // Update the data source
    setHasConfiguredSources(true);
    setConfiguredDataSource(data.dataSource);
    setConfiguredFiles(data.files);
    setFolderPath(data.folderPath);
    setCmisConfig(data.cmisConfig);
    setAlfrescoConfig(data.alfrescoConfig);
    // Store new configurations
    setWebConfig(data.webConfig);
    setWikipediaConfig(data.wikipediaConfig);
    setYoutubeConfig(data.youtubeConfig);
    setCloudConfig(data.cloudConfig);
    setEnterpriseConfig(data.enterpriseConfig);
    setRepositoryItemsHidden(false); // Reset hidden flag when sources are reconfigured
    setError(''); // Clear any previous errors
    
    // Auto-select files for processing
    if (data.dataSource === 'upload') {
      // For upload files, auto-select all configured files
      setSelectedFileIndices(new Set(data.files.map((_, index) => index)));
    } else {
      // For filesystem/CMIS/Alfresco, auto-select the single entry
      setSelectedFileIndices(new Set([0]));
    }
  };

  // Handle tab navigation
  const handleConfigureProcessing = () => {
    setMainTab('processing');
  };

  const handleGoToSources = () => {
    setMainTab('sources');
  };

  // Clear error when changing tabs
  const handleTabChange = (_: any, newValue: string) => {
    setMainTab(newValue);
    setError('');
  };

  // File removal functions
  const removeProcessingFile = (index: number) => {
    console.log('🗑️ removeProcessingFile called:', { index, configuredDataSource, statusData: statusData?.individual_files?.length });
    
    if (configuredDataSource === 'upload') {
      // Remove from configured files
      setConfiguredFiles(prev => prev.filter((_, i) => i !== index));
      // Update selected indices - remove the index and shift down higher indices
      const newSelected = new Set<number>();
      selectedFileIndices.forEach(i => {
        if (i < index) {
          newSelected.add(i);
        } else if (i > index) {
          newSelected.add(i - 1);
        }
        // Skip i === index (the removed file)
      });
      setSelectedFileIndices(newSelected);
    } else if (configuredDataSource === 'cmis' || configuredDataSource === 'alfresco') {
      console.log('🗂️ Repository file removal:', { 
        hasIndividualFiles: statusData?.individual_files?.length > 0,
        individualFilesCount: statusData?.individual_files?.length,
        index 
      });
      
      // For repository items, remove from display by manipulating statusData
      if (statusData?.individual_files && statusData.individual_files.length > 0) {
        console.log('📁 Removing from individual_files array');
        // If we have individual files, remove from that array
        const updatedFiles = [...statusData.individual_files];
        updatedFiles.splice(index, 1);
        console.log('📁 Updated files:', updatedFiles.length);
        setStatusData({
          ...statusData,
          individual_files: updatedFiles
        });
      } else {
        console.log('📁 Hiding repository items (repository path)');
        // If it's the initial repository path, hide repository items
        setRepositoryItemsHidden(true);
      }
      
      // Also update lastStatusData if it exists
      if (lastStatusData?.individual_files && lastStatusData.individual_files.length > 0) {
        const updatedFiles = [...lastStatusData.individual_files];
        updatedFiles.splice(index, 1);
        setLastStatusData({
          ...lastStatusData,
          individual_files: updatedFiles
        });
      }
      
      // Update selected indices
      const newSelected = new Set<number>();
      selectedFileIndices.forEach(i => {
        if (i < index) {
          newSelected.add(i);
        } else if (i > index) {
          newSelected.add(i - 1);
        }
      });
      setSelectedFileIndices(newSelected);
    }
  };

  const removeSelectedFiles = () => {
    if (configuredDataSource === 'upload') {
      // For upload files, remove from the configured files array
      const indicesToRemove = Array.from(selectedFileIndices).sort((a, b) => b - a);
      let newFiles = [...configuredFiles];
      indicesToRemove.forEach(index => {
        newFiles.splice(index, 1);
      });
      setConfiguredFiles(newFiles);
    } else {
      // For filesystem/CMIS/Alfresco, "removing" means unconfiguring the source
      setHasConfiguredSources(false);
      setConfiguredDataSource('');
      setConfiguredFiles([]);
    }
    setSelectedFileIndices(new Set());
  };

  // File selection management
  const handleSelectAllFiles = (checked: boolean, totalFiles: number) => {
    if (checked) {
      setSelectedFileIndices(new Set(Array.from({ length: totalFiles }, (_, index) => index)));
    } else {
      setSelectedFileIndices(new Set());
    }
  };

  const handleSelectFile = (index: number, checked: boolean) => {
    const newSelected = new Set(selectedFileIndices);
    if (checked) {
      newSelected.add(index);
    } else {
      newSelected.delete(index);
    }
    setSelectedFileIndices(newSelected);
  };

  return (
    <ThemeProvider theme={currentTheme}>
      <CssBaseline />
      <AppBar position="static" color="primary">
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            Flexible GraphRAG (React)
          </Typography>
          <FormControlLabel
            control={
              <Switch
                checked={!isDarkMode}
                onChange={(e) => setIsDarkMode(!e.target.checked)}
                color="default"
              />
            }
            label={
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                {isDarkMode ? <DarkModeIcon /> : <LightModeIcon />}
                {isDarkMode ? 'Dark' : 'Light'}
              </Box>
            }
          />
        </Toolbar>
      </AppBar>

      <Container maxWidth={false} sx={{ py: 4, px: 2 }}>
        <Paper sx={{ mb: 4 }} elevation={3}>
          <TabContext value={mainTab}>
            <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
              <Tabs 
                value={mainTab} 
                onChange={handleTabChange}
                variant="fullWidth"
                sx={{
                  '& .MuiTab-root': {
                    fontWeight: 500,
                    textTransform: 'none',
                    letterSpacing: '0.5px',
                  },
                  '& .MuiTab-root.Mui-selected': {
                    backgroundColor: currentTheme.palette.primary.main,
                    color: 'white !important',
                  },
                  '& .MuiTabs-indicator': {
                    height: 3,
                    backgroundColor: currentTheme.palette.primary.main,
                  },
                }}
              >
                <Tab label="SOURCES" value="sources" />
                <Tab label="PROCESSING" value="processing" />
                <Tab label="SEARCH" value="search" />
                <Tab label="CHAT" value="chat" />
                {/* <Tab label="GRAPH" value="graph" /> */}
              </Tabs>
            </Box>
            
            <TabPanel value="sources" sx={{ p: 0 }}>
              <SourcesTab
                currentTheme={currentTheme}
                dataSource={dataSource}
                selectedFiles={selectedFiles}
                folderPath={sourcesfolderPath}
                cmisUrl={cmisUrl}
                cmisUsername={cmisUsername}
                cmisPassword={cmisPassword}
                alfrescoUrl={alfrescoUrl}
                alfrescoUsername={alfrescoUsername}
                alfrescoPassword={alfrescoPassword}
                // Web sources
                webUrl={webUrl}
                wikipediaUrl={wikipediaUrl}
                youtubeUrl={youtubeUrl}
                // Cloud storage
                s3AccessKey={s3AccessKey}
                s3SecretKey={s3SecretKey}
                gcsBucketName={gcsBucketName}
                gcsCredentials={gcsCredentials}
                azureBlobConnectionString={azureBlobConnectionString}
                azureBlobContainer={azureBlobContainer}
                azureBlobName={azureBlobName}
                azureBlobAccountName={azureBlobAccountName}
                azureBlobAccountKey={azureBlobAccountKey}
                // Enterprise
                onedriveUserPrincipalName={onedriveUserPrincipalName}
                onedriveClientId={onedriveClientId}
                onedriveClientSecret={onedriveClientSecret}
                onedriveTenantId={onedriveTenantId}
                sharepointSiteName={sharepointSiteName}  // Changed from sharepointSiteUrl
                boxClientId={boxClientId}
                boxClientSecret={boxClientSecret}
                boxDeveloperToken={boxDeveloperToken}
                boxUserId={boxUserId}
                boxEnterpriseId={boxEnterpriseId}
                googleDriveCredentials={googleDriveCredentials}
                onDataSourceChange={handleDataSourceChange}
                onSelectedFilesChange={setSelectedFiles}
                onFolderPathChange={setSourcesFolderPath}
                onCmisUrlChange={setCmisUrl}
                onCmisUsernameChange={setCmisUsername}
                onCmisPasswordChange={setCmisPassword}
                onAlfrescoUrlChange={setAlfrescoUrl}
                onAlfrescoUsernameChange={setAlfrescoUsername}
                onAlfrescoPasswordChange={setAlfrescoPassword}
                // Web sources handlers
                onWebUrlChange={setWebUrl}
                onWikipediaUrlChange={setWikipediaUrl}
                onYoutubeUrlChange={setYoutubeUrl}
                // Cloud storage handlers
                onS3AccessKeyChange={setS3AccessKey}
                onS3SecretKeyChange={setS3SecretKey}
                onGcsBucketNameChange={setGcsBucketName}
                onGcsCredentialsChange={setGcsCredentials}
                onAzureBlobConnectionStringChange={setAzureBlobConnectionString}
                onAzureBlobContainerChange={setAzureBlobContainer}
                onAzureBlobNameChange={setAzureBlobName}
                onAzureBlobAccountNameChange={setAzureBlobAccountName}
                onAzureBlobAccountKeyChange={setAzureBlobAccountKey}
                // Enterprise handlers
                onOnedriveUserPrincipalNameChange={setOnedriveUserPrincipalName}
                onOnedriveClientIdChange={setOnedriveClientId}
                onOnedriveClientSecretChange={setOnedriveClientSecret}
                onOnedriveTenantIdChange={setOnedriveTenantId}
                onSharepointSiteNameChange={setSharepointSiteName}  // Changed from onSharepointSiteUrlChange
                onBoxClientIdChange={setBoxClientId}
                onBoxClientSecretChange={setBoxClientSecret}
                onBoxDeveloperTokenChange={setBoxDeveloperToken}
                onBoxUserIdChange={setBoxUserId}
                onBoxEnterpriseIdChange={setBoxEnterpriseId}
                onGoogleDriveCredentialsChange={setGoogleDriveCredentials}
                onConfigureProcessing={handleConfigureProcessing}
                onSourcesConfigured={handleSourcesConfigured}
              />
            </TabPanel>
            
            <TabPanel value="processing" sx={{ p: 0 }}>
              <ProcessingTab
                currentTheme={currentTheme}
                isDarkMode={isDarkMode}
                hasConfiguredSources={hasConfiguredSources}
                configuredDataSource={configuredDataSource}
                configuredFiles={configuredFiles}
                folderPath={folderPath}
                cmisConfig={cmisConfig}
                alfrescoConfig={alfrescoConfig}
                webConfig={webConfig}
                wikipediaConfig={wikipediaConfig}
                youtubeConfig={youtubeConfig}
                cloudConfig={cloudConfig}
                enterpriseConfig={enterpriseConfig}
                selectedFileIndices={selectedFileIndices}
                repositoryItemsHidden={repositoryItemsHidden}
                isProcessing={isProcessing}
                processingStatus={processingStatus}
                processingProgress={processingProgress}
                currentProcessingId={currentProcessingId}
                statusData={statusData}
                lastStatusData={lastStatusData}
                onGoToSources={handleGoToSources}
                onRemoveProcessingFile={removeProcessingFile}
                onRemoveSelectedFiles={removeSelectedFiles}
                onSelectAllFiles={handleSelectAllFiles}
                onSelectFile={handleSelectFile}
                onConfiguredFilesChange={setConfiguredFiles}
                onProcessingStateChange={setIsProcessing}
                onProcessingStatusChange={setProcessingStatus}
                onProcessingProgressChange={setProcessingProgress}
                onCurrentProcessingIdChange={setCurrentProcessingId}
                onStatusDataChange={setStatusData}
                onLastStatusDataChange={setLastStatusData}
                successMessage={successMessage}
                onSuccessMessage={setSuccessMessage}
                onError={setError}
              />
            </TabPanel>
            
            <TabPanel value="search" sx={{ p: 0 }}>
              <SearchTab 
                currentTheme={currentTheme}
                activeTab={searchActiveTab}
                question={searchQuestion}
                searchResults={searchResults}
                qaAnswer={qaAnswer}
                hasSearched={hasSearched}
                lastSearchQuery={lastSearchQuery}
                isQuerying={isQuerying}
                onActiveTabChange={setSearchActiveTab}
                onQuestionChange={setSearchQuestion}
                onSearchResultsChange={setSearchResults}
                onQaAnswerChange={setQaAnswer}
                onHasSearchedChange={setHasSearched}
                onLastSearchQueryChange={setLastSearchQuery}
                onIsQueryingChange={setIsQuerying}
              />
            </TabPanel>
            
            <TabPanel value="chat" sx={{ p: 0 }}>
              <ChatTab 
                currentTheme={currentTheme} 
                isDarkMode={isDarkMode}
                chatMessages={chatMessages}
                chatInput={chatInput}
                isQuerying={isChatQuerying}
                onChatMessagesChange={setChatMessages}
                onChatInputChange={setChatInput}
                onIsQueryingChange={setIsChatQuerying}
              />
            </TabPanel>
            
            {/* <TabPanel value="graph" sx={{ p: 0 }}>
              {renderGraphTab()}
            </TabPanel> */}
          </TabContext>
        </Paper>
        
        {error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {error}
          </Alert>
        )}
        

      </Container>
    </ThemeProvider>
  );
};

export default App;
