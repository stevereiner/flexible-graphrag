import { Component, ViewEncapsulation } from '@angular/core';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  encapsulation: ViewEncapsulation.None,
  standalone: false
})
export class AppComponent {
  title = 'Flexible GraphRAG (Angular)';
  selectedTabIndex = 0;
  hasConfiguredSources = false;
  configuredDataSource = '';
  configuredFiles: File[] = [];
  configuredFolderPath = '';
  repositoryItemsHidden = false;
  
  // New configuration types for modular sources
  configuredCmisConfig: any = null;
  configuredAlfrescoConfig: any = null;
  configuredNuxeoConfig: any = null;
  configuredWebConfig: any = null;
  configuredWikipediaConfig: any = null;
  configuredYoutubeConfig: any = null;
  configuredCloudConfig: any = null;
  configuredEnterpriseConfig: any = null;
  configurationTimestamp = 0;
  
  // Dark / light: the library's app-title-bar and FlexibleGraphragThemeService (set up when the
  // title bar is), styled by its styles/fg-theme.scss

  onConfigureProcessing(): void {
    this.selectedTabIndex = 1; // Switch to Processing tab
  }

  onSourcesConfigured(data: any): void {
    // Clear previous configuration to prevent filename conflicts
    this.hasConfiguredSources = false;
    this.configuredFiles = [];
    this.configuredFolderPath = '';
    this.repositoryItemsHidden = false;
    
    // Clear all configuration types
    this.configuredCmisConfig = null;
    this.configuredAlfrescoConfig = null;
    this.configuredNuxeoConfig = null;
    this.configuredWebConfig = null;
    this.configuredWikipediaConfig = null;
    this.configuredYoutubeConfig = null;
    this.configuredCloudConfig = null;
    this.configuredEnterpriseConfig = null;
    
    // Set new configuration
    this.hasConfiguredSources = true;
    this.configuredDataSource = data.dataSource;
    this.configuredFiles = data.files || []; // Handle empty files for web sources
    this.configuredFolderPath = data.folderPath || '';
    
    // Set new configuration types
    this.configuredCmisConfig = data.cmisConfig || null;
    this.configuredAlfrescoConfig = data.alfrescoConfig || null;
    this.configuredNuxeoConfig = data.nuxeoConfig || null;
    this.configuredWebConfig = data.webConfig || null;
    this.configuredWikipediaConfig = data.wikipediaConfig || null;
    this.configuredYoutubeConfig = data.youtubeConfig || null;
    this.configuredCloudConfig = data.cloudConfig || null;
    this.configuredEnterpriseConfig = data.enterpriseConfig || null;
    this.configurationTimestamp = Date.now();
    
    console.log('📁 Angular onSourcesConfigured (cleared previous state):', {
      dataSource: data.dataSource,
      folderPath: data.folderPath,
      configuredFolderPath: this.configuredFolderPath,
      filesCount: this.configuredFiles.length,
      hasWebConfig: !!this.configuredWebConfig,
      hasWikipediaConfig: !!this.configuredWikipediaConfig,
      hasYoutubeConfig: !!this.configuredYoutubeConfig,
      hasCloudConfig: !!this.configuredCloudConfig,
      hasEnterpriseConfig: !!this.configuredEnterpriseConfig
    });
  }

  removeRepositoryFile(index: number): void {
    console.log('🗑️ removeRepositoryFile called for index:', index);
    
    if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco' || this.configuredDataSource === 'nuxeo') {
      // For repository files, hide the items
      this.repositoryItemsHidden = true;
    }
  }

  removeUploadFile(index: number): void {
    console.log('🗑️ removeUploadFile called for index:', index);
    
    if (this.configuredDataSource === 'upload') {
      // Remove from configured files array
      this.configuredFiles = this.configuredFiles.filter((_, i) => i !== index);
      
      // If no files left, reset configuration
      if (this.configuredFiles.length === 0) {
        this.hasConfiguredSources = false;
        this.configuredDataSource = '';
      }
    }
  }
}
