import React, { useState, useCallback } from 'react';
import {
  Box,
  Typography,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material';
import { Theme } from '@mui/material/styles';
import {
  FileUploadForm,
  AlfrescoSourceForm,
  CMISSourceForm,
  WebSourceForm,
  WikipediaSourceForm,
  YouTubeSourceForm,
  S3SourceForm,
  GCSSourceForm,
  AzureBlobSourceForm,
  OneDriveSourceForm,
  SharePointSourceForm,
  BoxSourceForm,
  GoogleDriveSourceForm,
} from './sources';

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
  // Web sources
  webUrl: string;
  wikipediaUrl: string;
  youtubeUrl: string;
  // Cloud storage
  s3AccessKey: string;
  s3SecretKey: string;
  gcsBucketName: string;
  gcsProjectId: string;
  gcsCredentials: string;
  azureBlobConnectionString: string;
  azureBlobContainer: string;
  azureBlobName: string;
  azureBlobAccountName: string;
  azureBlobAccountKey: string;
  // Enterprise
  onedriveUserPrincipalName: string;
  onedriveClientId: string;
  onedriveClientSecret: string;
  onedriveTenantId: string;
  sharepointSiteName: string;  // Changed from sharepointSiteUrl to sharepointSiteName
  boxClientId: string;
  boxClientSecret: string;
  boxDeveloperToken: string;
  googleDriveCredentials: string;
  onDataSourceChange: (dataSource: string) => void;
  onSelectedFilesChange: (files: File[]) => void;
  onFolderPathChange: (folderPath: string) => void;
  onCmisUrlChange: (url: string) => void;
  onCmisUsernameChange: (username: string) => void;
  onCmisPasswordChange: (password: string) => void;
  onAlfrescoUrlChange: (url: string) => void;
  onAlfrescoUsernameChange: (username: string) => void;
  onAlfrescoPasswordChange: (password: string) => void;
  // Web sources handlers
  onWebUrlChange: (url: string) => void;
  onWikipediaUrlChange: (url: string) => void;
  onYoutubeUrlChange: (url: string) => void;
  // Cloud storage handlers
  onS3AccessKeyChange: (key: string) => void;
  onS3SecretKeyChange: (key: string) => void;
  onGcsBucketNameChange: (name: string) => void;
  onGcsProjectIdChange: (id: string) => void;
  onGcsCredentialsChange: (creds: string) => void;
  onAzureBlobConnectionStringChange: (conn: string) => void;
  onAzureBlobContainerChange: (container: string) => void;
  onAzureBlobNameChange: (name: string) => void;
  onAzureBlobAccountNameChange: (accountName: string) => void;
  onAzureBlobAccountKeyChange: (accountKey: string) => void;
  // Enterprise handlers
  onOnedriveUserPrincipalNameChange: (name: string) => void;
  onOnedriveClientIdChange: (id: string) => void;
  onOnedriveClientSecretChange: (secret: string) => void;
  onOnedriveTenantIdChange: (id: string) => void;
  onSharepointSiteNameChange: (name: string) => void;  // Changed from onSharepointSiteUrlChange
  onBoxClientIdChange: (id: string) => void;
  onBoxClientSecretChange: (secret: string) => void;
  onBoxDeveloperTokenChange: (token: string) => void;
  onGoogleDriveCredentialsChange: (creds: string) => void;
  onConfigureProcessing: () => void;
  onSourcesConfigured: (data: {
    dataSource: string;
    files: File[];
    folderPath: string;
    cmisConfig?: any;
    alfrescoConfig?: any;
    webConfig?: any;
    cloudConfig?: any;
    enterpriseConfig?: any;
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
  // Web sources
  webUrl,
  wikipediaUrl,
  youtubeUrl,
  // Cloud storage
  s3AccessKey,
  s3SecretKey,
  gcsBucketName,
  gcsProjectId,
  gcsCredentials,
  azureBlobConnectionString,
  azureBlobContainer,
  azureBlobName,
  azureBlobAccountName,
  azureBlobAccountKey,
  // Enterprise
  onedriveUserPrincipalName,
  onedriveClientId,
  onedriveClientSecret,
  onedriveTenantId,
  sharepointSiteName,  // Changed from sharepointSiteUrl
  boxClientId,
  boxClientSecret,
  boxDeveloperToken,
  googleDriveCredentials,
  onDataSourceChange,
  onSelectedFilesChange,
  onFolderPathChange,
  onCmisUrlChange,
  onCmisUsernameChange,
  onCmisPasswordChange,
  onAlfrescoUrlChange,
  onAlfrescoUsernameChange,
  onAlfrescoPasswordChange,
  // Web sources handlers
  onWebUrlChange,
  onWikipediaUrlChange,
  onYoutubeUrlChange,
  // Cloud storage handlers
  onS3AccessKeyChange,
  onS3SecretKeyChange,
  onGcsBucketNameChange,
  onGcsProjectIdChange,
  onGcsCredentialsChange,
  onAzureBlobConnectionStringChange,
  onAzureBlobContainerChange,
  onAzureBlobNameChange,
  onAzureBlobAccountNameChange,
  onAzureBlobAccountKeyChange,
  // Enterprise handlers
  onOnedriveUserPrincipalNameChange,
  onOnedriveClientIdChange,
  onOnedriveClientSecretChange,
  onOnedriveTenantIdChange,
  onSharepointSiteNameChange,  // Changed from onSharepointSiteUrlChange
  onBoxClientIdChange,
  onBoxClientSecretChange,
  onBoxDeveloperTokenChange,
  onGoogleDriveCredentialsChange,
  onConfigureProcessing, 
  onSourcesConfigured 
}) => {
  // Local state for form validation and configuration
  const [isFormValid, setIsFormValid] = useState<boolean>(false);
  const [currentConfig, setCurrentConfig] = useState<any>(null);

  // Handlers for modular components
  const handleValidationChange = useCallback((isValid: boolean) => {
    setIsFormValid(isValid);
  }, []);

  const handleConfigurationChange = useCallback((config: any) => {
    console.log('Configuration changed:', dataSource, config);
    setCurrentConfig(config);
  }, [dataSource]);


  const handleConfigureProcessing = () => {
    // Build configuration data based on current source and config
    console.log('Configure processing - dataSource:', dataSource, 'currentConfig:', currentConfig);
    const configData = {
      dataSource,
      files: dataSource === 'upload' ? selectedFiles : [],
      folderPath: ['cmis', 'alfresco'].includes(dataSource) ? folderPath : '',
      // Legacy configs for backward compatibility
      cmisConfig: dataSource === 'cmis' ? currentConfig : undefined,
      alfrescoConfig: dataSource === 'alfresco' ? currentConfig : undefined,
      // New modular configs  
      webConfig: dataSource === 'web' ? currentConfig : undefined,
      wikipediaConfig: dataSource === 'wikipedia' ? currentConfig : undefined,
      youtubeConfig: dataSource === 'youtube' ? currentConfig : undefined,
      cloudConfig: ['s3', 'gcs', 'azure_blob'].includes(dataSource) ? {
        type: dataSource,
        ...currentConfig
      } : undefined,
      enterpriseConfig: ['onedrive', 'sharepoint', 'box', 'google_drive'].includes(dataSource) ? {
        type: dataSource,
        ...currentConfig
      } : undefined
    };
    
    onSourcesConfigured(configData);
    onConfigureProcessing();
  };

  const renderDataSourceFields = () => {
    switch (dataSource) {
      case 'upload':
        return (
          <FileUploadForm
            currentTheme={currentTheme}
            selectedFiles={selectedFiles}
            onSelectedFilesChange={onSelectedFilesChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'cmis':
        return (
          <CMISSourceForm
            currentTheme={currentTheme}
            url={cmisUrl}
            username={cmisUsername}
            password={cmisPassword}
            folderPath={folderPath}
            onUrlChange={onCmisUrlChange}
            onUsernameChange={onCmisUsernameChange}
            onPasswordChange={onCmisPasswordChange}
            onFolderPathChange={onFolderPathChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'alfresco':
        return (
          <AlfrescoSourceForm
            currentTheme={currentTheme}
            url={alfrescoUrl}
            username={alfrescoUsername}
            password={alfrescoPassword}
            path={folderPath}
            onUrlChange={onAlfrescoUrlChange}
            onUsernameChange={onAlfrescoUsernameChange}
            onPasswordChange={onAlfrescoPasswordChange}
            onPathChange={onFolderPathChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'web':
        return (
          <WebSourceForm
            currentTheme={currentTheme}
            url={webUrl}
            onUrlChange={onWebUrlChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'wikipedia':
        return (
          <WikipediaSourceForm
            currentTheme={currentTheme}
            url={wikipediaUrl}
            onUrlChange={onWikipediaUrlChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'youtube':
        return (
          <YouTubeSourceForm
            currentTheme={currentTheme}
            url={youtubeUrl}
            onUrlChange={onYoutubeUrlChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 's3':
        return (
          <S3SourceForm
            currentTheme={currentTheme}
            accessKey={s3AccessKey}
            secretKey={s3SecretKey}
            onAccessKeyChange={onS3AccessKeyChange}
            onSecretKeyChange={onS3SecretKeyChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'gcs':
        return (
          <GCSSourceForm
            currentTheme={currentTheme}
            bucketName={gcsBucketName}
            projectId={gcsProjectId}
            credentials={gcsCredentials}
            onBucketNameChange={onGcsBucketNameChange}
            onProjectIdChange={onGcsProjectIdChange}
            onCredentialsChange={onGcsCredentialsChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'azure_blob':
        return (
          <AzureBlobSourceForm
            currentTheme={currentTheme}
            connectionString={azureBlobConnectionString}
            containerName={azureBlobContainer}
            blobName={azureBlobName}
            accountName={azureBlobAccountName}
            accountKey={azureBlobAccountKey}
            onConnectionStringChange={onAzureBlobConnectionStringChange}
            onContainerNameChange={onAzureBlobContainerChange}
            onBlobNameChange={onAzureBlobNameChange}
            onAccountNameChange={onAzureBlobAccountNameChange}
            onAccountKeyChange={onAzureBlobAccountKeyChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'onedrive':
        return (
          <OneDriveSourceForm
            currentTheme={currentTheme}
            userPrincipalName={onedriveUserPrincipalName}
            clientId={onedriveClientId}
            clientSecret={onedriveClientSecret}
            tenantId={onedriveTenantId}
            onUserPrincipalNameChange={onOnedriveUserPrincipalNameChange}
            onClientIdChange={onOnedriveClientIdChange}
            onClientSecretChange={onOnedriveClientSecretChange}
            onTenantIdChange={onOnedriveTenantIdChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'sharepoint':
        return (
          <SharePointSourceForm
            currentTheme={currentTheme}
            siteName={sharepointSiteName}  // Changed from siteUrl to siteName
            clientId={onedriveClientId}
            clientSecret={onedriveClientSecret}
            tenantId={onedriveTenantId}
            onSiteNameChange={onSharepointSiteNameChange}  // Changed from onSiteUrlChange
            onClientIdChange={onOnedriveClientIdChange}
            onClientSecretChange={onOnedriveClientSecretChange}
            onTenantIdChange={onOnedriveTenantIdChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'box':
        return (
          <BoxSourceForm
            currentTheme={currentTheme}
            clientId={boxClientId}
            clientSecret={boxClientSecret}
            developerToken={boxDeveloperToken}
            onClientIdChange={onBoxClientIdChange}
            onClientSecretChange={onBoxClientSecretChange}
            onDeveloperTokenChange={onBoxDeveloperTokenChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
        );
      
      case 'google_drive':
        return (
          <GoogleDriveSourceForm
            currentTheme={currentTheme}
            credentials={googleDriveCredentials}
            onCredentialsChange={onGoogleDriveCredentialsChange}
            onConfigurationChange={handleConfigurationChange}
            onValidationChange={handleValidationChange}
          />
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
      
      <FormControl sx={{ mb: 2, maxWidth: 400, width: '100%' }}>
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
          <MenuItem disabled>─── Web ───</MenuItem>
          <MenuItem value="web">Web Page</MenuItem>
          <MenuItem value="wikipedia">Wikipedia</MenuItem>
          <MenuItem value="youtube">YouTube</MenuItem>
          <MenuItem disabled>─── Cloud ───</MenuItem>
          <MenuItem value="google_drive">Google Drive</MenuItem>
          <MenuItem value="onedrive">Microsoft OneDrive</MenuItem>
          <MenuItem value="s3">Amazon S3</MenuItem>
          <MenuItem value="azure_blob">Azure Blob Storage</MenuItem>
          <MenuItem value="gcs">Google Cloud Storage</MenuItem>
          <MenuItem disabled>─── Enterprise ───</MenuItem>
          <MenuItem value="box">Box</MenuItem>
          <MenuItem value="sharepoint">SharePoint</MenuItem>
        </Select>
      </FormControl>
      
      {renderDataSourceFields()}
      
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', mt: 2 }}>
        <Button
          variant="contained"
          onClick={handleConfigureProcessing}
          disabled={!isFormValid}
          sx={{ minWidth: 200 }}
        >
          Configure Processing →
        </Button>
      </Box>
    </Box>
  );
};
