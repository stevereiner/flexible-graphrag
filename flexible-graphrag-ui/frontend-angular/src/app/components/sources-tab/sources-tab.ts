import { Component, EventEmitter, Output } from '@angular/core';
import { environment } from '../../../environments/environment';

@Component({
  selector: 'app-sources-tab',
  templateUrl: './sources-tab.html',
  styleUrls: ['./sources-tab.scss'],
  standalone: false
})
export class SourcesTabComponent {
  @Output() configureProcessing = new EventEmitter<void>();
  @Output() sourcesConfigured = new EventEmitter<any>();

  // State
  dataSource = 'upload';
  folderPath = '/Shared/GraphRAG';
  selectedFiles: File[] = [];
  isFormValid = false;
  currentConfig: any = {};

  // CMIS state
  cmisUrl = `${environment.cmisBaseUrl || 'http://localhost:8080'}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  cmisUsername = 'admin';
  cmisPassword = 'admin';

  // Alfresco state
  alfrescoUrl = `${environment.alfrescoBaseUrl || 'http://localhost:8080'}/alfresco`;
  alfrescoUsername = 'admin';
  alfrescoPassword = 'admin';

  // Web sources state
  webUrl = '';
  wikipediaUrl = '';
  wikipediaLanguage = 'en';
  wikipediaMaxDocs = 5;
  youtubeUrl = '';

  // Cloud storage state
  s3AccessKey = '';
  s3SecretKey = '';
  gcsBucketName = '';
  gcsProjectId = '';
  gcsCredentials = '';
  azureBlobConnectionString = '';
  azureBlobContainer = '';
  azureBlobName = '';
  azureBlobAccountName = '';
  azureBlobAccountKey = '';

  // Enterprise state
  onedriveUserPrincipalName = '';
  onedriveClientId = '';
  onedriveClientSecret = '';
  onedriveTenantId = '';
  sharepointSiteName = '';
  boxClientId = '';
  boxClientSecret = '';
  boxDeveloperToken = '';
  googleDriveCredentials = '';

  // Computed properties
  get cmisPlaceholder(): string {
    const baseUrl = environment.cmisBaseUrl || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  }

  get alfrescoPlaceholder(): string {
    const baseUrl = environment.alfrescoBaseUrl || 'http://localhost:8080';
    return `e.g., ${baseUrl}/alfresco`;
  }


  // Methods
  onDataSourceChange(): void {
    // Clear state when data source changes
    this.selectedFiles = [];
    this.currentConfig = {};
    this.isFormValid = false;
  }

  onConfigurationChange(config: any): void {
    this.currentConfig = config;
    console.log('📝 Angular onConfigurationChange:', {
      dataSource: this.dataSource,
      config: config,
      currentConfig: this.currentConfig
    });
  }

  onValidationChange(valid: any): void {
    // Handle the validation change from child components
    this.isFormValid = Boolean(valid);
  }

  onConfigureProcessing(): void {
    // Build configuration object based on data source
    const sourceConfig: any = {
      dataSource: this.dataSource,
      files: this.selectedFiles,
      folderPath: this.folderPath,
    };

    // Add source-specific configurations
    switch (this.dataSource) {
      case 'cmis':
        sourceConfig.cmisConfig = this.currentConfig;
        break;
      case 'alfresco':
        sourceConfig.alfrescoConfig = this.currentConfig;
        break;
      case 'web':
        sourceConfig.webConfig = this.currentConfig;
        break;
      case 'wikipedia':
        sourceConfig.wikipediaConfig = this.currentConfig;
        break;
      case 'youtube':
        sourceConfig.youtubeConfig = this.currentConfig;
        break;
      case 's3':
      case 'gcs':
      case 'azure_blob':
        sourceConfig.cloudConfig = this.currentConfig;
        break;
      case 'onedrive':
      case 'sharepoint':
      case 'box':
      case 'google_drive':
        sourceConfig.enterpriseConfig = this.currentConfig;
        break;
    }

    console.log('🚀 Angular onConfigureProcessing:', {
      dataSource: this.dataSource,
      currentConfig: this.currentConfig,
      sourceConfig: sourceConfig,
      isFormValid: this.isFormValid
    });

    this.sourcesConfigured.emit(sourceConfig);
    this.configureProcessing.emit();
  }
}