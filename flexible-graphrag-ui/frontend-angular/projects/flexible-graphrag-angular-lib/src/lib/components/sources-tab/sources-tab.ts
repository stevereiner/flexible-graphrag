import { Component, EventEmitter, Output, inject, OnInit } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';

@Component({
  selector: 'app-sources-tab',
  templateUrl: './sources-tab.html',
  styleUrls: ['./sources-tab.scss'],
  standalone: false
})
export class SourcesTabComponent implements OnInit {
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  @Output() configureProcessing = new EventEmitter<void>();
  @Output() sourcesConfigured = new EventEmitter<any>();

  // State
  dataSource = 'upload';

  /**
   * All selectable sources, in picker order. Used to fall back sensibly when the host has
   * narrowed the list and the current selection is not in it.
   */
  private static readonly ALL_SOURCES = [
    'upload', 'alfresco', 'nuxeo', 'cmis', 'web', 'wikipedia', 'youtube',
    'google_drive', 'onedrive', 's3', 'azure_blob', 'gcs', 'box', 'sharepoint'
  ];

  /**
   * Whether the host offers this data source. A host that knows its own repository can hide
   * the corresponding form -- an ACA extension hides Alfresco, because ACA's own document
   * list is the picker there and, unlike this tab's single path field, it can express a
   * multi-select that mixes files and folders.
   */
  ngOnInit(): void {
    if (!this.isSourceEnabled(this.dataSource)) {
      const first = SourcesTabComponent.ALL_SOURCES.find((s) => this.isSourceEnabled(s));
      if (first) {
        this.dataSource = first;
        this.onDataSourceChange();
      }
    }
  }

  isSourceEnabled(id: string): boolean {
    const enabled = this.fgConfig.enabledSources;
    return !enabled || enabled.includes(id);
  }
  folderPath = '/Shared/GraphRAG';
  selectedFiles: File[] = [];
  isFormValid = false;
  currentConfig: any = {};

  // CMIS state
  cmisUrl = `${this.fgConfig.cmisBaseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  cmisUsername = 'admin';
  cmisPassword = 'admin';

  // Single-object form state for the self-contained Nuxeo/Alfresco forms (persists across tabs).
  nuxeoFormValue: any = {};
  alfrescoFormValue: any = {};

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
  boxUserId = '';
  boxEnterpriseId = '';
  googleDriveCredentials = '';

  // Computed properties
  get cmisPlaceholder(): string {
    const baseUrl = this.fgConfig.cmisBaseUrl;
    return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
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
        sourceConfig.folderPath = this.currentConfig?.path || '';
        break;
      case 'nuxeo':
        sourceConfig.nuxeoConfig = this.currentConfig;
        sourceConfig.folderPath = this.currentConfig?.path || '';
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