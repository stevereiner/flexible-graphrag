import { Component, EventEmitter, Output, inject, OnInit } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SourceAuthService } from '../../services/source-auth.service';
import { IngestSignalService } from '../../services/ingest-signal.service';
import { FlexibleGraphragConfigService } from '../../config.service';
import { isDesktopApp, isDesktopRemoteBackend } from '../../desktop/desktop-bridge';

@Component({
  selector: 'app-sources-tab',
  templateUrl: './sources-tab.html',
  styleUrls: ['./sources-tab.scss'],
  standalone: false
})
export class SourcesTabComponent implements OnInit {
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private readonly sourceAuth = inject(SourceAuthService);
  // An ingest started: the lists held here empty (the forms clear their own too). The configured
  // sources stay: they are the Processing tab's rows.
  private readonly ingestStarted = inject(IngestSignalService).started
    .pipe(takeUntilDestroyed()).subscribe(() => {
      this.selectedFiles = [];
      if (this.alfrescoFormValue?.nodeDetails) this.alfrescoFormValue = { ...this.alfrescoFormValue, nodeDetails: undefined };
      if (this.nuxeoFormValue?.nodeDetails) this.nuxeoFormValue = { ...this.nuxeoFormValue, nodeDetails: undefined };
    });
  @Output() configureProcessing = new EventEmitter<void>();
  @Output() sourcesConfigured = new EventEmitter<any>();

  /** Inside the desktop app: Local Files and Folders is offered (and is the default), unless the
   *  backend is on another machine (then File Upload is). */
  readonly desktop = isDesktopApp();

  // State
  dataSource = this.desktop && this.isSourceEnabled('filesystem') ? 'filesystem' : 'upload';

  /**
   * All selectable sources, in picker order. Used to fall back sensibly when the host has
   * narrowed the list and the current selection is not in it.
   */
  private static readonly ALL_SOURCES = [
    ...(isDesktopApp() ? ['filesystem'] : []),
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
    // the desktop app reads local files itself; File Upload only with a remote backend, which in
    // turn can't read this computer's files (no Local Files and Folders then)
    if (id === 'upload' && isDesktopApp() && !isDesktopRemoteBackend()) return false;
    if (id === 'filesystem' && isDesktopRemoteBackend()) return false;
    const enabled = this.fgConfig.enabledSources;
    return !enabled || enabled.includes(id);
  }
  folderPath = '/Shared/GraphRAG';
  selectedFiles: File[] = [];
  isFormValid = false;
  currentConfig: any = {};

  // CMIS state
  cmisUrl = `${this.fgConfig.cmisBaseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
  // CMIS credentials: no pre-filled credentials (were admin/admin)
  cmisUsername = '';
  cmisPassword = '';

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

    // Credentials typed into an Alfresco / Nuxeo / CMIS form also sign in for search / chat
    // (if not signed in to that server)
    this.sourceAuth.signInFromSourceConfig(this.dataSource, this.currentConfig);
    // Add source-specific configurations
    switch (this.dataSource) {
      case 'filesystem':
        // Local files and folders (desktop app): { paths, items }
        sourceConfig.filesystemConfig = this.currentConfig;
        break;
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