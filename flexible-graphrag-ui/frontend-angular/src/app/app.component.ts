import { Component, OnInit, Inject, ViewEncapsulation } from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { MatSlideToggleChange } from '@angular/material/slide-toggle';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
  encapsulation: ViewEncapsulation.None,
  standalone: false
})
export class AppComponent implements OnInit {
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
  configuredWebConfig: any = null;
  configuredWikipediaConfig: any = null;
  configuredYoutubeConfig: any = null;
  configuredCloudConfig: any = null;
  configuredEnterpriseConfig: any = null;
  configurationTimestamp = 0;
  
  // Theme management
  isDarkMode = false;
  isLightMode = true;

  constructor(@Inject(DOCUMENT) private document: Document) {}

  ngOnInit(): void {
    // Initialize theme from localStorage
    const savedTheme = localStorage.getItem('angular-theme-mode');
    this.isDarkMode = savedTheme === 'dark'; // Default to light mode if no saved theme
    this.isLightMode = !this.isDarkMode;
    this.applyTheme();
  }

  toggleTheme(event: MatSlideToggleChange): void {
    this.isLightMode = event.checked;
    this.isDarkMode = !event.checked;
    localStorage.setItem('angular-theme-mode', this.isDarkMode ? 'dark' : 'light');
    this.applyTheme();
  }

  toggleThemeSimple(): void {
    this.isLightMode = !this.isLightMode;
    this.isDarkMode = !this.isDarkMode;
    localStorage.setItem('angular-theme-mode', this.isDarkMode ? 'dark' : 'light');
    this.applyTheme();
  }

  private applyTheme(): void {
    const body = this.document.body;
    if (this.isDarkMode) {
      body.classList.add('dark-theme');
      body.classList.remove('light-theme');
    } else {
      body.classList.add('light-theme');
      body.classList.remove('dark-theme');
    }
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
    
    if (this.configuredDataSource === 'cmis' || this.configuredDataSource === 'alfresco') {
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
