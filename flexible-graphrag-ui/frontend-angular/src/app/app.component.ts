import { Component, ViewEncapsulation, inject } from '@angular/core';
import { DesktopLocalService, GraphShowEvent, isDesktopApp } from '@flexible-graphrag/angular-ui';

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
  configuredFilesystemConfig: any = null;  // Local Files and Folders (desktop app)
  configurationTimestamp = 0;

  // Desktop app (flexible-graphrag-ui/desktop): the app shows once its backend answers
  readonly desktop = isDesktopApp();
  backendReady = !this.desktop;
  private readonly local = inject(DesktopLocalService);

  /** The backend answers: give it back the local folders added in the app (it keeps them in
   *  memory only), then show the app. */
  onBackendReady(): void {
    this.backendReady = true;
    this.local.syncLocalRoots().then((r) => {
      if (!r.ok) console.warn('Local folders not sent to the backend:', r.message);
    });
  }
  
  // Dark / light: the library's app-title-bar and FlexibleGraphragThemeService (set up when the
  // title bar is), styled by its styles/fg-theme.scss

  // Graph tab: what to show; "View graph" on other tabs sets it and switches there
  graph: GraphShowEvent | null = null;
  graphKey = 0;

  onShowGraph(event: GraphShowEvent): void {
    this.graph = event;
    this.graphKey++;
    this.selectedTabIndex = 4;
  }

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
    this.configuredFilesystemConfig = null;

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
    this.configuredFilesystemConfig = data.filesystemConfig || null;
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

  /** A local row removed on the Processing tab: out of this run's list and the form's picks. */
  removeLocalItem(index: number): void {
    const all = this.configuredFilesystemConfig?.items || [];
    const removed = all[index];
    this.configuredFilesystemConfig = DesktopLocalService.configOf(all.filter((_: any, i: number) => i !== index));
    // the form's own list (empty after an ingest started, or new picks): only that path leaves it
    if (removed) this.local.setItems(this.local.items.filter((i) => i.path !== removed.path));
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
