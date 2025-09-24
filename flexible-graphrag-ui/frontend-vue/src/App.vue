<template>
  <v-app :theme="currentTheme">
    <v-app-bar app :color="isDarkMode ? 'grey-darken-3' : 'primary'" dark>
      <v-toolbar-title>Flexible GraphRAG (Vue)</v-toolbar-title>
      <v-spacer></v-spacer>
      <div class="d-flex align-center ga-3">
        <v-switch
          v-model="isLightMode"
          color="white"
          hide-details
          inset
        ></v-switch>
        <v-icon>{{ isDarkMode ? 'mdi-weather-night' : 'mdi-weather-sunny' }}</v-icon>
        <span class="text-white mr-2">{{ isDarkMode ? 'Dark' : 'Light' }}</span>
      </div>
    </v-app-bar>

    <v-main>
      <v-container class="py-8" fluid>
        <v-card elevation="3">
          <v-tabs 
            v-model="mainTab" 
            grow 
            color="primary"
            :bg-color="isDarkMode ? 'grey-darken-4' : 'grey-lighten-4'"
            slider-color="primary"
            class="custom-tabs">
            <v-tab value="sources">SOURCES</v-tab>
            <v-tab value="processing">PROCESSING</v-tab>
            <v-tab value="search">SEARCH</v-tab>
            <v-tab value="chat">CHAT</v-tab>
            <!-- <v-tab value="graph">Graph</v-tab> -->
          </v-tabs>

          <v-card-text>
            <v-window v-model="mainTab">
              <!-- Sources Tab -->
              <v-window-item value="sources">
                <sources-tab 
                  @configure-processing="onConfigureProcessing"
                  @sources-configured="onSourcesConfigured"
                />
              </v-window-item>

              <!-- Processing Tab -->
              <v-window-item value="processing">
                <processing-tab 
                  :has-configured-sources="hasConfiguredSources"
                  :configured-data-source="configuredDataSource"
                  :configured-files="configuredFiles"
                  :configured-folder-path="configuredFolderPath"
                  :configured-cmis-config="configuredCmisConfig"
                  :configured-alfresco-config="configuredAlfrescoConfig"
                  :configured-web-config="configuredWebConfig"
                  :configured-wikipedia-config="configuredWikipediaConfig"
                  :configured-youtube-config="configuredYoutubeConfig"
                  :configured-cloud-config="configuredCloudConfig"
                  :configured-enterprise-config="configuredEnterpriseConfig"
                  :configuration-timestamp="configurationTimestamp"
                  @go-to-sources="mainTab = 'sources'"
                  @files-removed="configuredFiles = $event"
                />
              </v-window-item>

              <!-- Search Tab -->
              <v-window-item value="search">
                <search-tab />
              </v-window-item>

              <!-- Chat Tab -->
              <v-window-item value="chat">
                <chat-tab />
              </v-window-item>

              <!-- Graph Tab (hidden for now) -->
              <!-- <v-window-item value="graph">
                <graph-tab />
              </v-window-item> -->
            </v-window>
          </v-card-text>
        </v-card>
      </v-container>
    </v-main>
  </v-app>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import SourcesTab from './components/SourcesTab.vue';
import ProcessingTab from './components/ProcessingTab.vue';
import SearchTab from './components/SearchTab.vue';
import ChatTab from './components/ChatTab.vue';

export default defineComponent({
  name: 'App',
  components: {
    SourcesTab,
    ProcessingTab,
    SearchTab,
    ChatTab,
  },
  setup() {
    const mainTab = ref('sources');
    const hasConfiguredSources = ref(false);
    const configuredDataSource = ref('');
    const configuredFiles = ref<File[]>([]);

    // Theme management
    const getInitialTheme = () => {
      const saved = localStorage.getItem('vue-theme-mode');
      return saved ? saved === 'dark' : false; // Default to light mode for Vue
    };
    const isDarkMode = ref(getInitialTheme());

    const isLightMode = computed({
      get: () => !isDarkMode.value,
      set: (value) => {
        isDarkMode.value = !value;
      }
    });

    const currentTheme = computed(() => isDarkMode.value ? 'dark' : 'light');

    // Watch for theme changes and persist to localStorage
    watch(isDarkMode, (newValue) => {
      localStorage.setItem('vue-theme-mode', newValue ? 'dark' : 'light');
    }, { immediate: true });

    const onConfigureProcessing = () => {
      mainTab.value = 'processing';
    };

    const configuredFolderPath = ref('');
    const configuredCmisConfig = ref<any>(null);
    const configuredAlfrescoConfig = ref<any>(null);
    const configuredWebConfig = ref<any>(null);
    const configuredWikipediaConfig = ref<any>(null);
    const configuredYoutubeConfig = ref<any>(null);
    const configuredCloudConfig = ref<any>(null);
    const configuredEnterpriseConfig = ref<any>(null);
    const configurationTimestamp = ref(0);

    const onSourcesConfigured = (data: { 
      dataSource: string; 
      files: File[]; 
      folderPath?: string;
      cmisConfig?: any;
      alfrescoConfig?: any;
      webConfig?: any;
      wikipediaConfig?: any;
      youtubeConfig?: any;
      cloudConfig?: any;
      enterpriseConfig?: any;
    }) => {
      // Clear previous configuration to prevent filename conflicts
      hasConfiguredSources.value = false;
      configuredFiles.value = [];
      configuredFolderPath.value = '';
      configuredCmisConfig.value = null;
      configuredAlfrescoConfig.value = null;
      configuredWebConfig.value = null;
      configuredWikipediaConfig.value = null;
      configuredYoutubeConfig.value = null;
      configuredCloudConfig.value = null;
      configuredEnterpriseConfig.value = null;
      
      // Set new configuration
      hasConfiguredSources.value = true;
      configuredDataSource.value = data.dataSource;
      configuredFiles.value = data.files || []; // Handle empty files for web sources
      configuredFolderPath.value = data.folderPath || '';
      configuredCmisConfig.value = data.cmisConfig || null;
      configuredAlfrescoConfig.value = data.alfrescoConfig || null;
      configuredWebConfig.value = data.webConfig || null;
      configuredWikipediaConfig.value = data.wikipediaConfig || null;
      configuredYoutubeConfig.value = data.youtubeConfig || null;
      configuredCloudConfig.value = data.cloudConfig || null;
      configuredEnterpriseConfig.value = data.enterpriseConfig || null;
      configurationTimestamp.value = Date.now(); // Update timestamp every time sources are configured
      
      console.log('📁 Vue onSourcesConfigured (cleared previous state):', {
        dataSource: data.dataSource,
        folderPath: data.folderPath,
        filesCount: (data.files || []).length,
        hasWebConfig: !!data.webConfig,
        hasWikipediaConfig: !!data.wikipediaConfig,
        hasYoutubeConfig: !!data.youtubeConfig,
        hasCloudConfig: !!data.cloudConfig,
        hasEnterpriseConfig: !!data.enterpriseConfig
      });
    };

    return {
      mainTab,
      hasConfiguredSources,
      configuredDataSource,
      configuredFiles,
      configuredFolderPath,
      configuredCmisConfig,
      configuredAlfrescoConfig,
      configuredWebConfig,
      configuredWikipediaConfig,
      configuredYoutubeConfig,
      configuredCloudConfig,
      configuredEnterpriseConfig,
      configurationTimestamp,
      onConfigureProcessing,
      onSourcesConfigured,
      isDarkMode,
      isLightMode,
      currentTheme,
    };
  },
});
</script>

<style>
@import 'https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap';

.custom-tabs {
  border-bottom: 1px solid #e0e0e0;
}

.custom-tabs .v-tab {
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0.5px;
}

.custom-tabs .v-tab--selected {
  background-color: #1976d2;
  color: white !important;
}

.custom-tabs .v-tabs-slider {
  height: 3px;
}

/* Dark theme tab styling */
.v-theme--dark .custom-tabs .v-tab:not(.v-tab--selected) {
  color: #9e9e9e !important;
}

.v-theme--light .custom-tabs .v-tab:not(.v-tab--selected) {
  color: #666666 !important;
}
</style>