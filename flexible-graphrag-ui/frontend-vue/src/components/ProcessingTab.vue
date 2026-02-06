<template>
  <div class="pa-4">
    <!-- Header with Checkboxes -->
    <div class="d-flex justify-space-between align-center mb-4">
      <h2>File Processing</h2>
      <div class="d-flex flex-column gap-2">
        <v-checkbox
          v-model="skipGraph"
          label="Skip graph (search + vector only)"
          :disabled="isProcessing"
          color="primary"
          hide-details
          density="compact"
        ></v-checkbox>
        <!-- Only show Enable Sync for datasources that support auto-sync -->
        <!-- Hidden for: upload, cmis, webpage, wikipedia, youtube -->
        <v-checkbox
          v-if="configuredDataSource !== 'upload' && 
                configuredDataSource !== 'cmis' && 
                configuredDataSource !== 'web' && 
                configuredDataSource !== 'wikipedia' && 
                configuredDataSource !== 'youtube'"
          v-model="enableSync"
          label="Enable auto change sync"
          :disabled="isProcessing"
          color="primary"
          hide-details
          density="compact"
        ></v-checkbox>
      </div>
    </div>

    <!-- No Sources Configured Message -->
    <v-card
      v-if="!hasConfiguredSources"
      class="pa-6 mb-4 text-center"
      color="blue-lighten-5"
      variant="outlined"
    >
      <h3 class="mb-2" :style="{ color: $vuetify.theme.current.dark ? '#ffffff' : '#000000' }">No Data Source Configured</h3>
      <p class="mb-4" :style="{ color: $vuetify.theme.current.dark ? '#ffffff' : '#000000' }">Please go to the Sources tab to configure your data source first.</p>
      <v-btn
        color="primary"
        variant="outlined"
        @click="$emit('go-to-sources')"
      >
        ← Go to Sources
      </v-btn>
    </v-card>

    <!-- File Processing Table -->
    <v-card v-if="hasConfiguredSources" class="mb-4" variant="outlined">
      <v-data-table
        v-model="selectedItems"
        :headers="tableHeaders"
        :items="displayFiles"
        item-value="index"
        show-select
        class="elevation-0"
        density="compact"
        :items-per-page="-1"
        hide-default-footer
        disable-pagination
        :footer-props="{ 'items-per-page-options': [] }"
        :hide-default-header="false"
        :show-current-page="false"
      >
        <!-- Filename column -->
        <template #item.name="{ item }">
          <div :title="item.name" style="word-break: break-all; line-height: 1.2;">
            {{ item.name }}
          </div>
        </template>

        <!-- File Size column -->
        <template #item.size="{ item }">
          <span class="text-caption">
            {{ item.size > 0 ? formatFileSize(item.size) : 
               item.type === 'repository' ? 'Repository' : '-' }}
          </span>
        </template>

        <!-- Progress column -->
        <template #item.progress="{ item }">
          <div class="d-flex align-center" style="width: 100%;">
            <div style="flex: 1; margin-right: 8px;">
              <v-progress-linear
                :model-value="Math.max(getFileProgress(item.name) || 0, 2)"
                color="primary"
                height="10"
                rounded
              ></v-progress-linear>
            </div>
            <span class="text-caption" style="flex: none; white-space: nowrap;">
              {{ getFileProgress(item.name) }}% - {{ getFilePhase(item.name) }}
            </span>
          </div>
          <!-- Debug info - toggle with debug panel -->
          <div v-if="showDebugPanel" class="text-xs" style="color: #666; font-size: 10px;">
            Display: {{ item.name }} | Original: {{ item.originalFilename }} | Type: {{ item.type }}
            <br>Progress: {{ getFileProgress(item.name) }} | Phase: {{ getFilePhase(item.name) }} | Status: {{ getFileStatus(item.name) }}
          </div>
        </template>

        <!-- Remove column -->
        <template #item.remove="{ item }">
          <div class="text-center">
            <v-btn
              icon="mdi-close"
              size="small"
              variant="text"
              color="error"
              @click="removeFile(item.index)"
            >
            </v-btn>
          </div>
        </template>

        <!-- Status column -->
        <template #item.status="{ item }">
          <v-chip
            :color="getStatusColor(getFileStatus(item.name))"
            size="small"
            variant="flat"
          >
            {{ getFileStatus(item.name) }}
          </v-chip>
        </template>
      </v-data-table>
    </v-card>

    <!-- Upload Progress -->
    <v-card v-if="isUploading" class="pa-4 mb-4" color="blue-lighten-5">
      <p class="mb-2">Uploading files... {{ uploadProgress }}%</p>
      <v-progress-linear
        :model-value="uploadProgress"
        color="primary"
      ></v-progress-linear>
    </v-card>

    <!-- Processing Status -->
    <v-card v-if="isProcessing" class="pa-4 mb-4" :color="$vuetify.theme.current.dark ? 'grey-darken-3' : 'blue-lighten-5'">
      <div class="d-flex align-center justify-space-between mb-2">
        <div class="d-flex align-center">
          <v-progress-circular
            v-if="isProcessing"
            indeterminate
            size="20"
            width="2"
            color="primary"
            class="mr-2"
          ></v-progress-circular>
          <v-icon
            v-else-if="processingProgress === 100"
            color="success"
            size="20"
            class="mr-2"
          >
            mdi-check-circle
          </v-icon>
          <span :style="{ color: $vuetify.theme.current.dark ? '#ffffff' : 'inherit' }">{{ processingStatus || 'Processing documents...' }}</span>
        </div>
        <v-btn
          v-if="isProcessing"
          color="error"
          variant="outlined"
          size="small"
          :disabled="!currentProcessingId"
          @click="cancelProcessing"
        >
          Cancel
        </v-btn>
        <v-btn
          v-else
          icon="mdi-close"
          size="small"
          variant="text"
          @click="processingStatus = ''; processingProgress = 0"
        >
        </v-btn>
      </div>
      
      <div class="mb-2">
        <v-progress-linear
          :model-value="processingProgress"
          color="primary"
          class="mb-1"
        ></v-progress-linear>
        <p class="text-caption text-medium-emphasis">
          Overall Progress: {{ processingProgress }}% complete
          <span v-if="statusData?.estimated_time_remaining">
            • Est. time remaining: {{ statusData.estimated_time_remaining }}
          </span>
        </p>
      </div>
    </v-card>

    <!-- Action Buttons -->
    <div class="d-flex align-center ga-4">
      <v-btn
        color="primary"
        size="large"
        :disabled="!canStartProcessing"
        @click="startProcessing"
      >
        {{ getProcessingButtonText }}
      </v-btn>

      <v-btn
        v-if="selectedItems.length > 0 && displayFiles.length > 0"
        color="error"
        variant="outlined"
        prepend-icon="mdi-delete"
        @click="removeSelectedFiles"
      >
        REMOVE SELECTED ({{ selectedItems.length }})
      </v-btn>

      <!-- Debug toggle -->
      <v-btn
        variant="text"
        size="small"
        style="min-width: auto; color: transparent;"
        title="Double-click to toggle debug panel"
        @dblclick="showDebugPanel = !showDebugPanel"
      >
        🔧
      </v-btn>
    </div>

    <!-- Debug Panel -->
    <v-card
      v-if="showDebugPanel && (statusData || isProcessing || lastStatusData)"
      class="pa-4 mt-4"
      color="grey-darken-4"
      theme="dark"
    >
      <div class="d-flex justify-space-between align-center mb-2">
        <strong>Debug Status Data {{ !statusData && lastStatusData ? '(LAST STATUS)' : '(CURRENT)' }}:</strong>
        <v-btn
          size="small"
          variant="outlined"
          @click="loadLastStatus"
        >
          Load Last
        </v-btn>
      </div>
      <pre class="text-caption" style="background-color: #1a1a1a; padding: 8px; border-radius: 4px; overflow: auto; max-height: 200px;">{{ JSON.stringify(statusData || lastStatusData, null, 2) }}</pre>
    </v-card>

    <!-- Success Message -->
    <v-alert
      v-if="successMessage"
      type="success"
      class="mt-4"
      closable
      @click:close="successMessage = ''"
    >
      {{ successMessage }}
    </v-alert>

    <!-- Error Message -->
    <v-alert
      v-if="error"
      type="error"
      class="mt-4"
      closable
      @click:close="error = ''"
    >
      {{ error }}
    </v-alert>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import axios from 'axios';

interface ProcessingStatusResponse {
  processing_id: string;
  status: 'started' | 'processing' | 'completed' | 'failed' | 'cancelled';
  message: string;
  progress: number;
  started_at: string;
  updated_at: string;
  error?: string;
  individual_files?: Array<{
    filename: string;
    status: string;
    progress: number;
    phase: string;
    message?: string;
    error?: string;
    started_at?: string;
    completed_at?: string;
  }>;
  current_file?: string;
  current_phase?: string;
  files_completed?: number;
  total_files?: number;
  estimated_time_remaining?: string;
}

export default defineComponent({
  name: 'ProcessingTab',
  props: {
    hasConfiguredSources: {
      type: Boolean,
      required: true,
    },
    configuredDataSource: {
      type: String,
      required: true,
    },
    configuredFiles: {
      type: Array as () => File[],
      required: true,
    },
    configuredFolderPath: {
      type: String,
      default: '',
    },
    configuredCmisConfig: {
      type: Object,
      default: null,
    },
    configuredAlfrescoConfig: {
      type: Object,
      default: null,
    },
    configuredWebConfig: {
      type: Object,
      default: null,
    },
    configuredWikipediaConfig: {
      type: Object,
      default: null,
    },
    configuredYoutubeConfig: {
      type: Object,
      default: null,
    },
    configuredCloudConfig: {
      type: Object,
      default: null,
    },
    configuredEnterpriseConfig: {
      type: Object,
      default: null,
    },
    configurationTimestamp: {
      type: Number,
      default: 0,
    },
  },
  emits: ['go-to-sources', 'files-removed'],
  setup(props, { emit }) {
    // State
    const selectedItems = ref<number[]>([]);
    const isProcessing = ref(false);
    const isUploading = ref(false);
    const uploadProgress = ref(0);
    const processingProgress = ref(0);
    const processingStatus = ref('');
    const currentProcessingId = ref<string | null>(null);
    const statusData = ref<ProcessingStatusResponse | null>(null);
    const lastStatusData = ref<ProcessingStatusResponse | null>(null);
    const showDebugPanel = ref(false);
    const successMessage = ref('');
    const error = ref('');
    const skipGraph = ref(false);  // Per-ingest flag to skip knowledge graph extraction
    const enableSync = ref(false); // Enable incremental sync monitoring for this datasource
    const repositoryItemsHidden = ref(false); // Track when repository items are explicitly hidden
    const sourcesReconfiguredFlag = ref(0); // Counter to force repository items to show when reconfigured

    // Table headers
    const tableHeaders = [
      { title: 'Filename', key: 'name', width: '30%' }, // Use percentage for flexible but controlled width
      { title: 'File Size', key: 'size', width: '80px' },
      { title: 'Progress', key: 'progress', width: '45%', sortable: false }, // Maintain good progress bar width
      { title: '', key: 'remove', width: '50px', sortable: false, align: 'center' },
      { title: 'Status', key: 'status', width: '100px' },
    ] as const;

    // Computed
    const displayFiles = computed(() => {
      if (!props.hasConfiguredSources) return [];
      
      if (props.configuredDataSource === 'upload') {
        return props.configuredFiles.map((file, index) => ({
          index,
          name: file.name,
          originalFilename: file.name, // For upload files, name and originalFilename are the same
          size: file.size,
          type: 'file',
        }));
      } else if (props.configuredDataSource === 'cmis' || props.configuredDataSource === 'alfresco') {
        // If repository items are explicitly hidden AND sources haven't been freshly reconfigured, show nothing
        if (repositoryItemsHidden.value && sourcesReconfiguredFlag.value === 0) {
          console.log('Repository items hidden - returning empty array:', {
            repositoryItemsHidden: repositoryItemsHidden.value,
            sourcesReconfiguredFlag: sourcesReconfiguredFlag.value
          });
          return [];
        }
        
        console.log('Repository items should be visible:', {
          repositoryItemsHidden: repositoryItemsHidden.value,
          sourcesReconfiguredFlag: sourcesReconfiguredFlag.value
        });
        
        // Only use individual files from status data if we're currently processing
        // or if the processing was for the current repository configuration
        const individualFiles = (isProcessing.value || currentProcessingId.value) ? 
          (statusData.value?.individual_files || lastStatusData.value?.individual_files || []) : [];
        if (individualFiles.length > 0) {
          return individualFiles.map((file: any, index: number) => {
            const originalFilename = file.filename || `File ${index + 1}`;
            // Show full path instead of extracting just filename
            const displayName = originalFilename;
            
            return {
              index,
              name: displayName, // Use full path as display name
              originalFilename, // Keep original filename for progress matching
              size: 0, // Repository files don't have size info
              type: 'repository-file',
            };
          });
        }
        // Default to repository path when no individual files yet - show full path
        const displayName = props.configuredFolderPath || 'Repository Path';
        
        const repositoryFile = {
          index: 0,
          name: displayName,
          originalFilename: props.configuredFolderPath || 'Repository Path', // Use configured path as original filename
          size: 0,
          type: 'repository',
        };
        console.log('Creating repository file object:', repositoryFile);
        return [repositoryFile];
      } else if (['web', 'wikipedia', 'youtube', 's3', 'gcs', 'azure_blob', 'onedrive', 'sharepoint', 'box', 'google_drive'].includes(props.configuredDataSource)) {
        // Handle web sources and cloud sources
        // Use the actual configuration values that the backend uses for progress tracking
        const getDisplayName = () => {
          switch (props.configuredDataSource) {
            case 'web': 
              return props.configuredWebConfig?.url || 'Web Page';
            case 'wikipedia': 
              return props.configuredWikipediaConfig?.query || props.configuredWikipediaConfig?.url || 'Wikipedia Article';
            case 'youtube': 
              return props.configuredYoutubeConfig?.url || 'YouTube Video';
            case 's3': {
              const bucket = props.configuredCloudConfig?.bucket_name || props.configuredCloudConfig?.bucket || 'bucket';
              const prefix = props.configuredCloudConfig?.prefix || '';
              return prefix ? `s3://${bucket}/${prefix}` : `s3://${bucket}`;
            }
            case 'gcs': 
              return `GCS: ${props.configuredCloudConfig?.bucket_name || 'bucket'}`;
            case 'azure_blob': 
              return `Azure: ${props.configuredCloudConfig?.container_name || 'container'}`;
            case 'onedrive': 
              return `OneDrive: ${props.configuredEnterpriseConfig?.user_principal_name || 'user'}`;
            case 'sharepoint': 
              return `SharePoint: ${props.configuredEnterpriseConfig?.site_name || 'site'}`;
            case 'box': 
              return 'Box Storage';
            case 'google_drive': 
              return 'Google Drive';
            default: 
              return 'Data Source';
          }
        };
        
        const displayName = getDisplayName();
        
        // Check for individual files from status data (like CMIS/Alfresco)
        const individualFiles = (isProcessing.value || currentProcessingId.value) ? 
          (statusData.value?.individual_files || lastStatusData.value?.individual_files || []) : [];
        
        // If we have individual_files data, show it (this shows the single source entry with progress)
        if (individualFiles.length > 0) {
          return individualFiles.map((file: any, index: number) => {
            // Use the filename from status (should be the bucket/source path)
            const fileName = file.filename || displayName;
            
            return {
              index,
              name: fileName,
              originalFilename: fileName, // Use same name for progress matching
              size: 0,
              type: 'source',
            };
          });
        }
        
        // Default to source path when no individual files yet
        return [{
          index: 0,
          name: displayName,
          originalFilename: displayName, // Use same name for progress matching
          size: 0,
          type: 'source',
        }];
      }
      return [];
    });

    const canStartProcessing = computed(() => {
      return props.hasConfiguredSources && selectedItems.value.length > 0 && !isProcessing.value;
    });

    const getProcessingButtonText = computed(() => {
      if (isProcessing.value) return 'PROCESSING...';
      if (!props.hasConfiguredSources) return 'CONFIGURE SOURCES FIRST';
      if (selectedItems.value.length === 0) return 'SELECT FILES TO PROCESS';
      return 'START PROCESSING';
    });

    // Methods
    const formatFileSize = (bytes: number): string => {
      if (bytes < 1024) {
        return bytes === 0 ? "0 B" : "1 KB";
      } else if (bytes < 1024 * 1024) {
        return `${Math.ceil(bytes / 1024)} KB`;
      } else {
        return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
      }
    };

    const getFileProgressData = (filename: string) => {
      // For repository path placeholder, use overall progress
      const folderName = props.configuredFolderPath.split(/[/\\]/).pop() || props.configuredFolderPath;
      if (filename === folderName || filename === props.configuredFolderPath || filename === 'Repository Path') {
        return {
          status: isProcessing.value ? 'processing' : (processingProgress.value === 100 ? 'completed' : 'ready'),
          progress: processingProgress.value,
          phase: isProcessing.value ? 'processing' : (processingProgress.value === 100 ? 'completed' : 'ready')
        };
      }

      // For web sources (web, wikipedia, youtube, cloud, enterprise), use overall progress when no individual files
      if (['web', 'wikipedia', 'youtube', 's3', 'gcs', 'azure_blob', 'onedrive', 'sharepoint', 'box', 'google_drive'].includes(props.configuredDataSource)) {
        const files = statusData.value?.individual_files || lastStatusData.value?.individual_files || [];
        
        // If no individual files yet, use overall progress for web sources
        if (files.length === 0) {
          return {
            status: isProcessing.value ? 'processing' : (processingProgress.value === 100 ? 'completed' : 'ready'),
            progress: processingProgress.value,
            phase: isProcessing.value ? 'processing' : (processingProgress.value === 100 ? 'completed' : 'ready')
          };
        }
      }

      const files = statusData.value?.individual_files || lastStatusData.value?.individual_files || [];
      
      // Debug: Log during processing to see what files we have
      if (isProcessing.value) {
        console.log('🔍 Looking for progress data for:', filename);
        console.log('📁 Available files count:', files.length);
        console.log('📁 Data source:', props.configuredDataSource);
        console.log('📁 Display files:', displayFiles.value.map(f => ({ name: f.name, originalFilename: f.originalFilename })));
        if (files.length > 0) {
          console.log('📁 Available files:', files.map(f => ({ name: f.filename, progress: f.progress, status: f.status })));
        } else {
          console.log('📁 No individual files in statusData yet');
        }
      }
      
      // Try exact match first
      let match = files.find((file: any) => file.filename === filename);
      if (match) {
        if (isProcessing.value) console.log('✅ Exact match found:', match);
        return match;
      }
      
      // Try matching just the basename if full path doesn't match
      match = files.find((file: any) => {
        const fileBasename = file.filename?.split(/[/\\]/).pop();
        return fileBasename === filename;
      });
      if (match) {
        if (isProcessing.value) console.log('✅ Basename match found:', match);
        return match;
      }
      
      // Try matching if our filename is contained in the stored filename
      match = files.find((file: any) => 
        file.filename?.includes(filename) || filename.includes(file.filename)
      );
      if (match) {
        if (isProcessing.value) console.log('✅ Partial match found:', match);
        return match;
      }
      
      if (isProcessing.value) {
        console.log('❌ No match found for:', filename);
      }
      
      // If no match found but processing is completed, return completed status
      if (!match && !isProcessing.value && processingProgress.value === 100) {
        return {
          status: 'completed',
          progress: 100,
          phase: 'completed'
        };
      }
      
      return match;
    };

    const getFileProgress = (filename: string): number => {
      // Use the enhanced getFileProgressData function which handles all source types
      const progressData = getFileProgressData(filename);
      if (progressData) {
        return progressData.progress || 0;
      }
      
      // Fallback for any unhandled cases
      return 0;
    };

    const getFilePhase = (filename: string): string => {
      // Use the enhanced getFileProgressData function which handles all source types
      const progressData = getFileProgressData(filename);
      if (progressData) {
        const phase = progressData.phase || 'ready';
        const phaseNames: { [key: string]: string } = {
          'ready': 'Ready',
          'waiting': 'Waiting',
          'docling': 'Converting',
          'chunking': 'Chunking',
          'kg_extraction': 'Extracting Graph',
          'indexing': 'Indexing',
          'processing': 'Processing',
          'completed': 'Completed',
          'error': 'Error'
        };
        return phaseNames[phase] || phase;
      }
      
      // Fallback for any unhandled cases
      return 'Ready';
    };

    const getFileStatus = (filename: string): string => {
      // Use the enhanced getFileProgressData function which handles all source types
      const progressData = getFileProgressData(filename);
      if (progressData) {
        return progressData.status || 'ready';
      }
      
      // Fallback for any unhandled cases
      return 'ready';
    };

    const getStatusColor = (status: string): string => {
      switch (status) {
        case 'completed': return 'success';
        case 'failed': return 'error';
        case 'processing': return 'primary';
        default: return 'default';
      }
    };

    const removeFile = (index: number) => {
      if (props.configuredDataSource === 'upload') {
        // Remove from configured files
        const newFiles = [...props.configuredFiles];
        newFiles.splice(index, 1);
        // Emit event to parent to update configured files
        emit('files-removed', newFiles);
        
        // Update selected indices - remove the index and shift down higher indices
        const newSelected = selectedItems.value
          .filter(i => i !== index)
          .map(i => i > index ? i - 1 : i);
        selectedItems.value = newSelected;
      } else if (props.configuredDataSource === 'cmis' || props.configuredDataSource === 'alfresco') {
        // For repository items, remove from display
        if (statusData.value?.individual_files && statusData.value.individual_files.length > 0) {
          // If we have individual files, remove from that array
          const updatedFiles = [...statusData.value.individual_files];
          updatedFiles.splice(index, 1);
          statusData.value = {
            ...statusData.value,
            individual_files: updatedFiles
          };
        } else {
          // If it's the initial repository path, hide it
          repositoryItemsHidden.value = true;
          sourcesReconfiguredFlag.value = 0; // Reset counter to allow hiding
        }
        
        if (lastStatusData.value?.individual_files && lastStatusData.value.individual_files.length > 0) {
          const updatedFiles = [...lastStatusData.value.individual_files];
          updatedFiles.splice(index, 1);
          lastStatusData.value = {
            ...lastStatusData.value,
            individual_files: updatedFiles
          };
        } else if (lastStatusData.value) {
          lastStatusData.value = {
            ...lastStatusData.value,
            individual_files: []
          };
        }
        
        // Update selected indices - remove the index and shift down higher indices
        const newSelected = selectedItems.value
          .filter(i => i !== index)
          .map(i => i > index ? i - 1 : i);
        selectedItems.value = newSelected;
      }
    };

    const removeSelectedFiles = () => {
      console.log('Remove selected files:', selectedItems.value);
      
      if (props.configuredDataSource === 'upload') {
        // For upload files, remove from the configured files array
        const indicesToRemove = [...selectedItems.value].sort((a, b) => b - a);
        const newFiles = [...props.configuredFiles];
        indicesToRemove.forEach(index => {
          newFiles.splice(index, 1);
        });
        // Emit event to parent to update configured files
        emit('files-removed', newFiles);
      } else if (props.configuredDataSource === 'cmis' || props.configuredDataSource === 'alfresco') {
        // For repository items, remove from display
        if (statusData.value?.individual_files && statusData.value.individual_files.length > 0) {
          // If we have individual files, remove selected ones
          const indicesToRemove = [...selectedItems.value].sort((a, b) => b - a);
          const updatedFiles = [...statusData.value.individual_files];
          indicesToRemove.forEach(index => {
            updatedFiles.splice(index, 1);
          });
          statusData.value = {
            ...statusData.value,
            individual_files: updatedFiles
          };
        } else {
          // If it's the initial repository path and all are selected, hide all
          repositoryItemsHidden.value = true;
          sourcesReconfiguredFlag.value = 0; // Reset counter to allow hiding
        }
        
        if (lastStatusData.value?.individual_files && lastStatusData.value.individual_files.length > 0) {
          const indicesToRemove = [...selectedItems.value].sort((a, b) => b - a);
          const updatedFiles = [...lastStatusData.value.individual_files];
          indicesToRemove.forEach(index => {
            updatedFiles.splice(index, 1);
          });
          lastStatusData.value = {
            ...lastStatusData.value,
            individual_files: updatedFiles
          };
        } else if (lastStatusData.value) {
          lastStatusData.value = {
            ...lastStatusData.value,
            individual_files: []
          };
        }
      }
      
      // Clear selection
      selectedItems.value = [];
    };

    const pollProcessingStatus = async (processingId: string) => {
      try {
        const response = await axios.get<ProcessingStatusResponse>(`/api/processing-status/${processingId}`);
        const status = response.data;
        
        processingStatus.value = status.message;
        processingProgress.value = status.progress;
        statusData.value = status;
        lastStatusData.value = status;
        
        console.log('📊 Processing status update:', {
          progress: status.progress,
          individualFilesCount: status.individual_files?.length || 0,
          individualFiles: status.individual_files?.map(f => ({ 
            filename: f.filename, 
            progress: f.progress, 
            status: f.status 
          })) || []
        });
        localStorage.setItem('lastProcessingStatus', JSON.stringify(status));
        
        if (status.status === 'completed') {
          isProcessing.value = false;
          processingStatus.value = status.message || 'Processing completed';
          processingProgress.value = 100; // Keep at 100% to show completion
          currentProcessingId.value = null;
          successMessage.value = status.message || 'Documents ingested successfully!';
        } else if (status.status === 'failed') {
          isProcessing.value = false;
          processingStatus.value = '';
          processingProgress.value = 0;
          currentProcessingId.value = null;
          error.value = status.error || 'Processing failed';
        } else if (status.status === 'cancelled') {
          isProcessing.value = false;
          processingStatus.value = 'Processing cancelled';
          processingProgress.value = 0; // 0% for cancelled
          currentProcessingId.value = null;
          successMessage.value = 'Processing cancelled successfully';
        } else if (status.status === 'started' || status.status === 'processing') {
          setTimeout(() => pollProcessingStatus(processingId), 2000);
        }
      } catch (err) {
        console.error('Error checking processing status:', err);
        error.value = 'Error checking processing status';
        isProcessing.value = false;
        currentProcessingId.value = null;
      }
    };

    const cancelProcessing = async () => {
      if (!currentProcessingId.value) return;
      
      try {
        const response = await axios.post(`/api/cancel-processing/${currentProcessingId.value}`, {});
        
        if (!response.data.success) {
          error.value = 'Failed to cancel processing';
        }
      } catch (err) {
        console.error('Error cancelling processing:', err);
        error.value = 'Error cancelling processing';
      }
    };

    const startProcessing = async () => {
      if (!canStartProcessing.value) return;
      
      try {
        isProcessing.value = true;
        error.value = '';
        successMessage.value = '';
        statusData.value = null;
        lastStatusData.value = null;
        
        const request: any = {
          data_source: props.configuredDataSource
        };

        // Add skip_graph flag if checked
        if (skipGraph.value) {
          request.skip_graph = true;
          console.log('✓ skip_graph flag set to true - Knowledge graph extraction will be skipped');
        }
        
        // Add enable_sync flag if checked
        if (enableSync.value) {
          request.enable_sync = true;
          console.log('✓ enable_sync flag set to true - Incremental updates will be enabled');
        }

        if (props.configuredDataSource === 'upload') {
          // For upload, we need to upload files first, then use their paths
          const uploadedPaths = await uploadFiles();
          request.paths = uploadedPaths;
          request.data_source = 'filesystem'; // Use filesystem processing for uploaded files
        } else if (props.configuredDataSource === 'cmis') {
          request.paths = [props.configuredFolderPath || '/Shared/GraphRAG']; // Use configured path
          request.cmis_config = {
            url: 'http://localhost:8080/alfresco/api/-default-/public/cmis/versions/1.1/atom',
            username: 'admin',
            password: 'admin',
            folder_path: props.configuredFolderPath || '/Shared/GraphRAG'
          };
        } else if (props.configuredDataSource === 'alfresco') {
          request.paths = [props.configuredFolderPath || '/Shared/GraphRAG']; // Use configured path
          request.alfresco_config = {
            url: 'http://localhost:8080/alfresco',
            username: 'admin',
            password: 'admin',
            path: props.configuredFolderPath || '/Shared/GraphRAG'
          };
        } else if (props.configuredDataSource === 'web') {
          request.web_config = props.configuredWebConfig;
        } else if (props.configuredDataSource === 'wikipedia') {
          request.wikipedia_config = props.configuredWikipediaConfig;
        } else if (props.configuredDataSource === 'youtube') {
          request.youtube_config = props.configuredYoutubeConfig;
        } else if (['s3', 'gcs', 'azure_blob'].includes(props.configuredDataSource)) {
          // Cloud storage sources - strip the 'type' field before sending
          const { type, ...cleanConfig } = props.configuredCloudConfig || {};
          if (props.configuredDataSource === 's3') {
            request.s3_config = cleanConfig;
          } else if (props.configuredDataSource === 'gcs') {
            request.gcs_config = cleanConfig;
          } else if (props.configuredDataSource === 'azure_blob') {
            request.azure_blob_config = cleanConfig;
          }
        } else if (['onedrive', 'sharepoint', 'box', 'google_drive'].includes(props.configuredDataSource)) {
          // Enterprise sources - strip the 'type' field before sending
          const { type, ...cleanConfig } = props.configuredEnterpriseConfig || {};
          if (props.configuredDataSource === 'onedrive') {
            request.onedrive_config = cleanConfig;
          } else if (props.configuredDataSource === 'sharepoint') {
            request.sharepoint_config = cleanConfig;
          } else if (props.configuredDataSource === 'box') {
            request.box_config = cleanConfig;
          } else if (props.configuredDataSource === 'google_drive') {
            request.google_drive_config = cleanConfig;
          }
        }

        const response = await axios.post('/api/ingest', request);
        
        // Handle async processing response
        if (response.data.status === 'started') {
          processingStatus.value = response.data.message;
          processingProgress.value = 0;
          currentProcessingId.value = response.data.processing_id;
          successMessage.value = `Processing started: ${response.data.estimated_time || 'Please wait...'}`;
          // Start polling for status
          setTimeout(() => pollProcessingStatus(response.data.processing_id), 2000);
        } else if (response.data.status === 'completed') {
          isProcessing.value = false;
          processingStatus.value = 'Processing completed';
          processingProgress.value = 100; // Keep at 100% to show completion
          successMessage.value = 'Documents ingested successfully!';
        } else if (response.data.status === 'failed') {
          isProcessing.value = false;
          error.value = response.data.error || 'Processing failed';
        }
        
      } catch (err: any) {
        console.error('Error processing documents:', err);
        const errorMessage = err?.response?.data?.detail || err?.response?.data?.error || 'Error processing documents';
        error.value = errorMessage;
        isProcessing.value = false;
        currentProcessingId.value = null;
      }
    };

    const uploadFiles = async (): Promise<string[]> => {
      if (props.configuredFiles.length === 0) return [];
      
      isUploading.value = true;
      uploadProgress.value = 0;
      
      try {
        const formData = new FormData();
        props.configuredFiles.forEach(file => {
          formData.append('files', file);
        });
        
        const response = await axios.post('/api/upload', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
          onUploadProgress: (progressEvent) => {
            if (progressEvent.total) {
              const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              uploadProgress.value = progress;
            }
          },
        });
        
        if (response.data.success) {
          // Show information about skipped files if any
          if (response.data.skipped && response.data.skipped.length > 0) {
            const skippedInfo = response.data.skipped
              .map((file: any) => `${file.filename}: ${file.reason}`)
              .join('\n');
            error.value = `Some files were skipped:\n${skippedInfo}`;
          }
          
          return response.data.files.map((file: any) => file.path);
        } else {
          throw new Error('Upload failed');
        }
      } finally {
        isUploading.value = false;
        uploadProgress.value = 0;
      }
    };

    const loadLastStatus = () => {
      const saved = localStorage.getItem('lastProcessingStatus');
      if (saved) {
        const parsed = JSON.parse(saved);
        lastStatusData.value = parsed;
        console.log('Retrieved from localStorage:', parsed);
      } else {
        console.log('No saved status found in localStorage');
      }
    };

    // Auto-select all files when configured files change or when repository files are discovered
    watch(() => props.configuredFiles, () => {
      if (props.configuredDataSource === 'upload') {
        // Clear old processing messages when reconfiguring upload files
        successMessage.value = '';
        error.value = '';
        
        selectedItems.value = props.configuredFiles.map((_, index) => index);
      }
    }, { immediate: true });

    // Watch for repository configuration changes (CMIS/Alfresco) based on timestamp
    watch(() => props.configurationTimestamp, (newTimestamp, oldTimestamp) => {
      if (newTimestamp > 0 && newTimestamp !== oldTimestamp && 
          (props.configuredDataSource === 'cmis' || props.configuredDataSource === 'alfresco')) {
        // Clear old processing messages when reconfiguring
        successMessage.value = '';
        error.value = '';
        
        // Reset hidden flag and increment reconfigured counter when repository sources are reconfigured
        repositoryItemsHidden.value = false;
        sourcesReconfiguredFlag.value++;
        
        // Auto-select repository files after configuration
        setTimeout(() => {
          const currentFiles = displayFiles.value;
          selectedItems.value = currentFiles.map((_, index) => index);
          console.log('Auto-selected repository files after configuration:', selectedItems.value, 'for', currentFiles.length, 'files');
        }, 100); // Small delay to ensure displayFiles is updated
        
        console.log('Repository configuration timestamp changed, resetting flags:', {
          repositoryItemsHidden: repositoryItemsHidden.value,
          sourcesReconfiguredFlag: sourcesReconfiguredFlag.value,
          newTimestamp,
          oldTimestamp
        });
      }
    });

    // Watch for web source configuration changes based on timestamp
    watch(() => props.configurationTimestamp, (newTimestamp, oldTimestamp) => {
      if (newTimestamp > 0 && newTimestamp !== oldTimestamp && 
          ['web', 'wikipedia', 'youtube', 's3', 'gcs', 'azure_blob', 'onedrive', 'sharepoint', 'box', 'google_drive'].includes(props.configuredDataSource)) {
        // Clear old processing messages when reconfiguring
        successMessage.value = '';
        error.value = '';
        
        // Auto-select web source items after configuration
        setTimeout(() => {
          const currentFiles = displayFiles.value;
          selectedItems.value = currentFiles.map((_, index) => index);
          console.log('Auto-selected web source items after configuration:', selectedItems.value, 'for', currentFiles.length, 'items');
        }, 100); // Small delay to ensure displayFiles is updated
        
        console.log('Web source configuration timestamp changed:', {
          dataSource: props.configuredDataSource,
          newTimestamp,
          oldTimestamp
        });
      }
    });

    // Auto-select files when they are discovered from processing status or configuration
    watch(() => displayFiles.value, (newFiles, oldFiles) => {
      if (props.configuredDataSource === 'cmis' || props.configuredDataSource === 'alfresco') {
        console.log('Repository displayFiles changed:', newFiles.length, 'files');
        selectedItems.value = newFiles.map((_, index) => index);
        console.log('Auto-selected repository items:', selectedItems.value);
      } else if (['web', 'wikipedia', 'youtube', 's3', 'gcs', 'azure_blob', 'onedrive', 'sharepoint', 'box', 'google_drive'].includes(props.configuredDataSource)) {
        console.log('Web source displayFiles changed:', newFiles.length, 'items');
        selectedItems.value = newFiles.map((_, index) => index);
        console.log('Auto-selected web source items:', selectedItems.value);
      }
    }, { immediate: true });

    // Clear processing state when data source changes
    watch(() => props.configuredDataSource, () => {
      isProcessing.value = false;
      processingStatus.value = '';
      processingProgress.value = 0;
      currentProcessingId.value = null;
      statusData.value = null;
      lastStatusData.value = null;
      selectedItems.value = [];
      repositoryItemsHidden.value = false; // Reset hidden flag
      sourcesReconfiguredFlag.value = 0; // Reset reconfigured counter
      successMessage.value = ''; // Clear success message (green panel)
      error.value = ''; // Clear error message (red panel)
      // Note: This ensures clean state when switching between upload/CMIS/Alfresco
    });

    // Note: Removed the hasConfiguredSources watcher since we now use timestamp-based detection

    return {
      selectedItems,
      isProcessing,
      isUploading,
      uploadProgress,
      processingProgress,
      processingStatus,
      currentProcessingId,
      statusData,
      lastStatusData,
      showDebugPanel,
      successMessage,
      error,
      skipGraph,
      repositoryItemsHidden,
      sourcesReconfiguredFlag,
      tableHeaders,
      displayFiles,
      canStartProcessing,
      getProcessingButtonText,
      formatFileSize,
      getFileProgress,
      getFilePhase,
      getFileStatus,
      getStatusColor,
      removeFile,
      removeSelectedFiles,
      cancelProcessing,
      startProcessing,
      uploadFiles,
      loadLastStatus,
    };
  },
});
</script>

<style scoped>
.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Hide all data table footer elements */
:deep(.v-data-table-footer) {
  display: none !important;
}

:deep(.v-data-table__footer) {
  display: none !important;
}

:deep(.v-pagination) {
  display: none !important;
}

:deep(.v-data-footer) {
  display: none !important;
}

/* Checkbox styling to match React - blue checkboxes with white checkmarks */
:deep(.v-data-table .v-selection-control .v-selection-control__input) {
  color: #1976d2 !important; /* Blue checkbox */
}

:deep(.v-data-table .v-checkbox .v-selection-control__input .v-icon) {
  color: #1976d2 !important; /* Blue checkmark */
  background-color: transparent !important;
}

:deep(.v-data-table .v-checkbox input:checked + .v-selection-control__input .v-icon) {
  color: #1976d2 !important; /* Blue when checked */
  background-color: #1976d2 !important; /* Blue background when checked */
}

/* Vuetify 3 specific checkbox styling */
:deep(.v-selection-control--dirty .v-selection-control__input .v-icon) {
  color: #1976d2 !important;
  opacity: 1 !important;
}

/* Dark theme checkbox styling */
.v-theme--dark :deep(.v-data-table .v-selection-control .v-selection-control__input) {
  color: #64b5f6 !important; /* Light blue for dark mode */
}

.v-theme--dark :deep(.v-data-table .v-checkbox .v-selection-control__input .v-icon) {
  color: #64b5f6 !important; /* Light blue checkmark */
}

.v-theme--dark :deep(.v-selection-control--dirty .v-selection-control__input .v-icon) {
  color: #64b5f6 !important;
}
</style>
