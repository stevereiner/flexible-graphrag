<template>
  <div class="pa-4">
    <v-tabs v-model="subTab" class="mb-4" density="compact">
      <v-tab :value="0">Processing</v-tab>
      <v-tab :value="1">{{ runningJobCount ? `Jobs (${runningJobCount} running)` : 'Jobs' }}</v-tab>
    </v-tabs>
    <div v-if="subTab === 0">
    <!-- Header with Checkboxes -->
    <div class="d-flex justify-space-between align-center mb-4">
      <h2>File Processing</h2>
      <div class="d-flex flex-column gap-2">
        <v-checkbox
          v-if="!columnsMode"
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
          v-if="!columnsMode &&
                configuredDataSource !== 'upload' &&
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
      <p v-if="ingestedRowCount > 0 && !isProcessing && processingProgress === 0"
         class="text-body-2 px-4 pt-3 mb-0" style="opacity: 0.8;">
        {{ ingestedRowCount }} of {{ displayFiles.length }} already in the stores, so left unchecked.
        {{ columnsMode ? 'Check rows, set Search+Vector / Graphs, and click START PROCESSING to update them.'
                       : 'Check rows and click START PROCESSING to update them.' }}
        Hover the status for details.
      </p>
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

        <!-- Search+Vector / Graphs columns: what the row should end up in -->
        <template #header.searchVector>
          <v-checkbox
            :model-value="countWant('sv') === displayFiles.length && displayFiles.length > 0"
            :indeterminate="countWant('sv') > 0 && countWant('sv') < displayFiles.length"
            :disabled="isProcessing || !canSearchVector"
            label="Search+Vector"
            title="Vector and full-text search stores, for every row"
            class="text-no-wrap"
            density="compact"
            hide-details
            @update:model-value="(v) => setWant(allRows(), 'sv', !!v)"
          ></v-checkbox>
        </template>
        <template #header.graphs>
          <v-checkbox
            :model-value="countWant('graphs') === displayFiles.length && displayFiles.length > 0"
            :indeterminate="countWant('graphs') > 0 && countWant('graphs') < displayFiles.length"
            :disabled="isProcessing || !canGraphs"
            label="Graphs"
            :title="canGraphs ? 'Property graph and RDF, for every row' : 'No graph store configured in .env'"
            class="text-no-wrap"
            density="compact"
            hide-details
            @update:model-value="(v) => setWant(allRows(), 'graphs', !!v)"
          ></v-checkbox>
        </template>
        <template #item.searchVector="{ item }">
          <v-checkbox
            :model-value="wantFor(item.index).sv"
            :disabled="isProcessing || !canSearchVector"
            density="compact"
            hide-details
            @update:model-value="(v) => setWant([item.index], 'sv', !!v)"
          ></v-checkbox>
        </template>
        <template #item.graphs="{ item }">
          <v-checkbox
            :model-value="wantFor(item.index).graphs"
            :disabled="isProcessing || !canGraphs"
            density="compact"
            hide-details
            @update:model-value="(v) => setWant([item.index], 'graphs', !!v)"
          ></v-checkbox>
        </template>
        <!-- Auto Sync column: kept up to date with repository changes -->
        <template #header.autoSync>
          <v-checkbox
            :model-value="countWant('sync') === displayFiles.length && displayFiles.length > 0"
            :indeterminate="countWant('sync') > 0 && countWant('sync') < displayFiles.length"
            :disabled="isProcessing"
            label="Auto Sync"
            title="Keep every row up to date with repository changes"
            class="text-no-wrap"
            density="compact"
            hide-details
            @update:model-value="(v) => setWant(allRows(), 'sync', !!v)"
          ></v-checkbox>
        </template>
        <template #item.autoSync="{ item }">
          <v-checkbox
            :model-value="wantFor(item.index).sync"
            :disabled="isProcessing"
            title="Unchecking stops this row's auto sync; for a datasource's own root it also stops watching it"
            density="compact"
            hide-details
            @update:model-value="(v) => setWant([item.index], 'sync', !!v)"
          ></v-checkbox>
        </template>

        <!-- Remove column -->
        <template #item.remove="{ item }">
          <div class="text-center" style="white-space: nowrap;">
            <v-btn
              icon="mdi-close"
              size="small"
              variant="text"
              color="error"
              title="Take this row off the list (the stores are not touched)"
              @click="removeFile(item.index)"
            >
            </v-btn>
          </div>
        </template>

        <!-- Status column -->
        <template #item.status="{ item }">
          <!-- Before a run: which stores the row is in now -->
          <v-chip
            v-if="columnsMode && !isProcessing && processingProgress === 0"
            :color="inStores(item.index) ? 'info' : undefined"
            size="small"
            variant="tonal"
            :title="ingestStatusTooltip(item.index)"
            style="cursor: help;"
          >
            {{ storesLabel(item.index) }}
          </v-chip>
          <v-chip
            v-else-if="showIngestStatus(item.index)"
            :color="ingestStatusFor(item.index)?.status === 'synced' ? 'info' : 'warning'"
            size="small"
            variant="tonal"
            :title="ingestStatusTooltip(item.index)"
            style="cursor: help;"
          >
            {{ ingestStatusLabel(item.index) }}
          </v-chip>
          <v-chip
            v-else
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

      <v-checkbox
        v-model="runInBackground"
        label="Run in background"
        title="Start the job and keep this tab free; follow it on the Jobs tab"
        :disabled="isProcessing"
        color="primary"
        density="compact"
        hide-details
      ></v-checkbox>
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

    <div v-if="subTab === 1">
      <div class="d-flex justify-space-between align-center mb-4">
        <h2>Jobs</h2>
        <div class="d-flex ga-2">
          <v-btn variant="outlined" size="small" prepend-icon="mdi-refresh" @click="loadJobs">Refresh</v-btn>
          <v-btn variant="outlined" size="small" prepend-icon="mdi-notification-clear-all"
                 :disabled="jobs.every(jobRunning)" title="Remove finished jobs from the list (running ones stay)"
                 @click="clearJobs">Clear finished</v-btn>
        </div>
      </div>
      <p v-if="jobs.length === 0" class="text-body-2" style="opacity: 0.75;">
        No jobs yet. Jobs started from the Processing tab -- and auto sync runs -- are listed here,
        oldest first. The backend keeps them until it restarts.
      </p>
      <div v-else style="overflow-x: auto;">
        <v-table density="compact" style="min-width: 900px;">
          <thead>
            <tr>
              <th>Started</th><th>Job</th><th>Source</th><th>Status</th>
              <th style="min-width: 140px;">Progress</th><th>Message</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="job in jobs" :key="job.processing_id">
              <td style="white-space: nowrap;">{{ job.started_at ? new Date(job.started_at).toLocaleString() : '' }}</td>
              <td :title="job.label || job.processing_id"
                  style="max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ job.kind === 'sync' ? ('auto sync ' + (job.sync_action || '') + (job.label ? ': ' + job.label : '')) : (job.label || job.processing_id) }}
              </td>
              <td>{{ job.data_source }}</td>
              <td>
                <v-chip size="small" variant="flat"
                        :color="job.status === 'completed' ? 'success' : job.status === 'failed' ? 'error'
                                : jobRunning(job) ? 'primary' : undefined">{{ job.status }}</v-chip>
              </td>
              <td>
                <v-progress-linear :model-value="job.progress || 0" color="primary" height="8" rounded></v-progress-linear>
                <span class="text-caption">{{ job.progress || 0 }}%</span>
              </td>
              <td style="min-width: 320px; white-space: normal; overflow-wrap: anywhere;">{{ job.message }}</td>
              <td>
                <v-btn v-if="jobRunning(job) && job.kind === 'ingest'" size="small" color="error"
                       variant="outlined" @click="cancelJob(job)">Cancel</v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch, onBeforeUnmount } from 'vue';
import axios from 'axios';

// Sources with no auto change sync: the "Enable auto change sync" checkbox is hidden for them
const NO_AUTO_SYNC_SOURCES = ['upload', 'cmis', 'web', 'wikipedia', 'youtube'];

// A file the server refused to store (unsupported extension, bad name, too large)
interface SkippedFile {
  filename: string;
  reason: string;
}

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
    configuredNuxeoConfig: {
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
    // Search+Vector / Graphs columns once the ingest-status check answered with `stores`
    // (with them, Filename and Progress give up width: at 30% + 45% the two checkbox columns were
    // squeezed until their labels broke letter by letter)
    const tableHeaders = computed(() => [
      { title: 'Filename', key: 'name', width: columnsMode.value ? '25%' : '30%' },
      { title: 'File Size', key: 'size', width: '80px' },
      { title: 'Progress', key: 'progress', width: columnsMode.value ? '30%' : '45%', sortable: false },
      ...(columnsMode.value ? [
        { title: 'Search+Vector', key: 'searchVector', sortable: false, align: 'start', width: '170px', minWidth: '170px' },
        { title: 'Graphs', key: 'graphs', sortable: false, align: 'start', width: '120px', minWidth: '120px' },
        // Auto Sync only for repository sources (uploads are not kept in sync)
        ...(props.configuredDataSource === 'upload' ? [] : [
          { title: 'Auto Sync', key: 'autoSync', sortable: false, align: 'start', width: '140px', minWidth: '140px' },
        ]),
      ] : []),
      { title: '', key: 'remove', width: '50px', sortable: false, align: 'center' },
      { title: 'Status', key: 'status', width: '100px' },
    ] as any[]);

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
      } else if (props.configuredDataSource === 'cmis' || props.configuredDataSource === 'alfresco' || props.configuredDataSource === 'nuxeo') {
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
        
        // The selection decides the rows, before, during and after a run. The backend's per-file
        // list used to replace them once a run started, so a folder row could turn into one of
        // its files (and stay that way), and the rows stopped lining up with the ingest status.
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
          'loading': 'Loading',
          'loaded': 'Loaded',
          'cocoindex': 'Processing',
          'downloading': 'Downloading',
          'downloaded': 'Downloaded',
          'parsing': 'Parsing',
          'parsed': 'Parsed',
          'chunked': 'Chunked',
          'embedded': 'Embedded',
          'docling': 'Converting',
          'chunking': 'Chunking',
          'kg_extracting': 'Extracting Graph',
          'kg_extracted': 'Graph Extracted',
          'vector_indexing': 'Vector Index',
          'graph_indexing': 'Property Graph',
          'kg_extraction': 'Extracting Graph',
          'search_indexing': 'Search Index',
          'rdf_indexing': 'RDF Graph',
          'indexing_complete': 'Complete',
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
      } else if (props.configuredDataSource === 'cmis' || props.configuredDataSource === 'alfresco' || props.configuredDataSource === 'nuxeo') {
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

        // Search+Vector / Graphs columns: each checked row says what it should end up as
        const planned = columnsMode.value ? itemActions() : null;
        const actions = planned;
        if (planned && planned.length === 0) {
          successMessage.value = 'Nothing to do: the checked rows already match their Search+Vector / Graphs settings.';
          isProcessing.value = false;
          return;
        }
        if (planned) {
          request.item_actions = actions;
        } else if (skipGraph.value) {
          request.skip_graph = true;
          console.log('✓ skip_graph flag set to true - Knowledge graph extraction will be skipped');
        }
        
        // Add enable_sync flag if checked
        // Only for a source that shows the checkbox: the value survives switching sources, so
        // a sync left ticked on Alfresco would otherwise make a later upload a live sync too.
        if (!planned && enableSync.value && !NO_AUTO_SYNC_SOURCES.includes(props.configuredDataSource)) {
          request.enable_sync = true;
          console.log('✓ enable_sync flag set to true - Incremental updates will be enabled');
        }

        if (props.configuredDataSource === 'upload') {
          // For upload, we need to upload files first, then use their paths
          const { paths: uploadedPaths, skipped } = await uploadFiles();

          // Nothing survived the upload (e.g. every file had an unsupported extension).
          // Stop here: posting paths: [] starts a job that can only fail, and its "failed"
          // status then overwrites the skip reasons the user actually needs to read.
          if (uploadedPaths.length === 0) {
            error.value = skipped.length > 0
              ? `No files could be uploaded:\n${formatSkipped(skipped)}`
              : 'No files could be uploaded';
            isProcessing.value = false;
            return;
          }

          if (skipped.length > 0) {
            error.value = `Some files were skipped:\n${formatSkipped(skipped)}`;
          }

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
          const alfrescoPath = props.configuredAlfrescoConfig?.path || props.configuredFolderPath || '/Shared/GraphRAG';
          request.paths = [alfrescoPath];
          // Send what the Sources tab configured. This used to be a hardcoded admin/admin
          // literal, so the form's credentials, auth method and URL were silently discarded
          // (and the URL differed from the form's, so the datasource never matched ingest status).
          request.alfresco_config = props.configuredAlfrescoConfig
            ? { ...props.configuredAlfrescoConfig, path: alfrescoPath }
            : {
                url: 'http://localhost:8080',
                username: 'admin',
                password: 'admin',
                path: alfrescoPath
              };
        } else if (props.configuredDataSource === 'nuxeo') {
          request.nuxeo_config = props.configuredNuxeoConfig;
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
        if (response.data.status === 'started' && runInBackground.value) {
          // The job carries on in the backend; this tab is free to start another one
          watchedJobs.value = [...watchedJobs.value, response.data.processing_id];
          isProcessing.value = false;
          successMessage.value = `Started in the background (job ${response.data.processing_id}). Follow it on the Jobs tab.`;
        } else if (response.data.status === 'started') {
          foregroundRun = true;
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

    const formatSkipped = (skipped: SkippedFile[]): string =>
      skipped.map(file => `${file.filename}: ${file.reason}`).join('\n');

    const uploadFiles = async (): Promise<{ paths: string[]; skipped: SkippedFile[] }> => {
      if (props.configuredFiles.length === 0) return { paths: [], skipped: [] };
      
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
          // Skipped files are returned rather than reported here: only the caller knows
          // whether anything survived, and "all skipped" needs a different message than
          // "some skipped".
          const skipped: SkippedFile[] = response.data.skipped || [];

          return { paths: response.data.files.map((file: any) => file.path), skipped };
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

    // ── Ingest status of the current rows (auto sync or earlier ingest) ───────────────
    // Asks the backend which rows are already in the stores (an auto change sync covers them,
    // or an earlier ingest put them there), so they start unchecked instead of being
    // ingested again. One call per configuration; quietly nothing on an older backend.
    const ingestStatus = ref<any[]>([]);
    let ingestStatusKey = '';
    let ingestStatusRequest: any = null;  // the request behind `ingestStatus` (rows line up)
    // Which stores are configured; any can be "none" in .env (from the ingest-status response)
    const stores = ref<Record<string, boolean>>({});

    const looksLikeFile = (path: string): boolean =>
      /\.[A-Za-z0-9]{1,8}$/.test((path || '').split('/').pop() || '');

    const ingestStatusFor = (index: number): any | null => {
      // Rows and ingest status line up one-to-one, except after a run, when the rows can be the
      // backend's per-file list instead of the one path that was checked.
      if (ingestStatus.value.length !== displayFiles.value.length) return null;
      const c = ingestStatus.value[index];
      return c && c.status !== 'none' ? c : null;
    };

    const ingestStatusIsSync = (c: any): boolean =>
      !!c?.datasources?.some((m: any) => m.auto_sync && m.status === c.status);

    const ingestStatusLabel = (index: number): string => {
      const c = ingestStatusFor(index);
      const synced = ingestStatusIsSync(c);
      switch (c?.status) {
        case 'synced': return synced ? 'already synced' : 'already ingested';
        case 'partial': return synced ? 'synced, no subfolders' : 'ingested, no subfolders';
        case 'overlaps': return synced ? 'contains synced' : 'contains ingested';
        case 'removed': return 'removed';
        default: return '';
      }
    };

    const ingestStatusTooltip = (index: number): string => {
      const c = ingestStatusFor(index);
      if (!c) return '';
      const lines = c.datasources.map((m: any) => {
        const how = m.auto_sync ? 'synced by' : 'ingested (no auto sync) by';
        const what = m.relation === 'indexed' ? 'indexed by'
          : m.relation === 'contains' ? `contains ${m.root}, ${how}`
          : `${m.root}${m.recursive ? ' (with subfolders)' : ''}, ${how}`;
        return `${what} ${m.source_name || m.config_id}${m.skip_graph ? ' [no graph]' : ''}`;
      });
      if (c.indexed) {
        const where = ['vector', 'search', 'graph'].filter((t) => c.indexed[t]);
        lines.push(`in: ${where.join(', ') || 'none'}`);
      }
      lines.push(c.status === 'synced'
        ? 'Left unchecked. Check it and click START PROCESSING to update it.'
        : c.status === 'removed'
          ? 'Removed from the stores and kept out of its auto sync, even when it changes. Ingest it to put it back.'
          : 'Part of it is already in the stores; ingesting it again refreshes that part.');
      return lines.join('\n');
    };

    const ingestedRowCount = computed(() =>
      displayFiles.value.filter((_: any, i: number) => ingestStatusFor(i)?.status === 'synced').length);

    const showIngestStatus = (index: number): boolean =>
      !!ingestStatusFor(index) && !isProcessing.value && processingProgress.value === 0;

    const refreshIngestStatus = () => {
      const source = props.configuredDataSource;
      const cfg: any = source === 'alfresco' ? props.configuredAlfrescoConfig
        : source === 'nuxeo' ? props.configuredNuxeoConfig : null;
      const isUpload = source === 'upload';
      if ((!isUpload && source !== 'alfresco' && source !== 'nuxeo') || isProcessing.value
          || (isUpload && !displayFiles.value.length)) {
        if ((!isUpload && source !== 'alfresco' && source !== 'nuxeo') || (isUpload && !displayFiles.value.length)) {
          ingestStatus.value = []; ingestStatusKey = '';
        }
        return;
      }
      const path = cfg?.path || props.configuredFolderPath || '/';
      // Uploaded files: rows by file name (the backend finds them under its upload directory)
      const request = isUpload
        ? { data_source: 'upload', recursive: false,
            items: displayFiles.value.map((f: any) => ({ path: f.name, is_folder: false })) }
        : {
            data_source: source,
            url: cfg?.url,
            recursive: !!cfg?.recursive,
            items: [{ path, is_folder: !looksLikeFile(path) }],
          };
      const key = JSON.stringify(request);
      if (key === ingestStatusKey) return;
      ingestStatusKey = key;
      ingestStatusRequest = request;
      ingestStatus.value = [];
      axios.post('/api/sync/ingest-status', request)
        .then((res) => {
          if (key !== ingestStatusKey) return;  // configuration changed while this was in flight
          ingestStatus.value = res.data?.enabled ? res.data.items : [];
          stores.value = res.data?.stores || {};
          if (!awaitingStatus) {
            selectedItems.value = selectedItems.value.filter((i) => ingestStatusFor(i)?.status !== 'synced');
          }
        })
        .catch((err) => console.warn('Ingest status check unavailable:', err));
    };

    watch(
      () => [props.configuredDataSource, props.configurationTimestamp, props.configuredFolderPath,
             displayFiles.value.length],
      () => refreshIngestStatus(),
      { immediate: true },
    );

    // ── Search+Vector / Graphs columns ────────────────────────────────────────────────
    type ItemActionKind = 'ingest' | 'ingest_no_graph' | 'remove_graph' | 'remove_all' | 'keep';
    type ColumnKind = 'sv' | 'graphs' | 'sync';
    const TERMINAL_JOB = ['completed', 'failed', 'cancelled'];
    // What each row should end up in, by row name, once the user changed it (see wantFor)
    const wantSearch = ref<Record<string, boolean>>({});
    const wantGraphs = ref<Record<string, boolean>>({});
    const wantSync = ref<Record<string, boolean>>({});
    let awaitingStatus = false;  // a run just ended: check nothing until the fresh ingest status

    const columnsMode = computed(() => ingestStatus.value.length > 0 && ingestStatusRequest !== null && Object.keys(stores.value).length > 0);
    const canSearchVector = computed(() => !!(stores.value.vector || stores.value.search));
    const canGraphs = computed(() => !!stores.value.graph);
    const inStores = (index: number): boolean =>
      ['synced', 'partial', 'overlaps'].includes(ingestStatusFor(index)?.status);

    /** What a row is in now, from the ingest status. */
    const currentFor = (index: number) => {
      const c = ingestStatusFor(index);
      const sync = !!c?.auto_sync;
      if (!c || !inStores(index)) return { sv: false, graphs: false, sync };
      if (c.indexed) return { sv: !!(c.indexed.vector || c.indexed.search), graphs: !!c.indexed.graph, sync };
      return { sv: true, graphs: (c.datasources || []).some((m: any) => !m.skip_graph), sync };
    };

    /** Whether an auto sync already covers the row (so Auto Sync on resumes, not starts, it). */
    const coveredBySync = (index: number): boolean =>
      !!(ingestStatusFor(index)?.datasources || []).some((m: any) => m.auto_sync);

    /** What a row should end up in: the user's choice, else what it is in now, else everything. */
    const wantFor = (index: number) => {
      const name = displayFiles.value[index]?.name;
      const cur = currentFor(index);
      const fresh = !inStores(index);
      const sv = wantSearch.value[name] ?? (fresh ? canSearchVector.value : cur.sv);
      const graphs = wantGraphs.value[name] ?? (fresh ? canGraphs.value : cur.graphs);
      const sync = wantSync.value[name] ?? cur.sync;
      // Graphs and Auto Sync both need Search+Vector: a sync with nothing indexed would only
      // put the document back on its next change
      return { sv, graphs: sv && graphs, sync: sv && sync };
    };

    /** Changing a row's Search+Vector / Graphs checks the row: START PROCESSING applies it. */
    const setWant = (indices: number[], kind: ColumnKind, value: boolean) => {
      for (const i of indices) {
        const name = displayFiles.value[i]?.name;
        if (!name) continue;
        if (kind === 'sv') {
          wantSearch.value = { ...wantSearch.value, [name]: value };
          if (!value) {  // no graphs and no sync without search + vector
            wantGraphs.value = { ...wantGraphs.value, [name]: false };
            wantSync.value = { ...wantSync.value, [name]: false };
          }
        } else if (kind === 'graphs') {
          wantGraphs.value = { ...wantGraphs.value, [name]: value };
          if (value) wantSearch.value = { ...wantSearch.value, [name]: true };
        } else {
          wantSync.value = { ...wantSync.value, [name]: value };
          if (value) wantSearch.value = { ...wantSearch.value, [name]: true };
        }
      }
      selectedItems.value = [...new Set([...selectedItems.value, ...indices])];
    };
    const allRows = (): number[] => displayFiles.value.map((_: any, i: number) => i);
    const countWant = (kind: ColumnKind): number => allRows().filter((i) => wantFor(i)[kind]).length;

    /** What START PROCESSING does with a checked row, or null when there is nothing to do. */
    const actionFor = (index: number): ItemActionKind | null => {
      const cur = currentFor(index);
      const want = wantFor(index);
      if (!want.sv) return cur.sv || cur.graphs ? 'remove_all' : null;
      if (want.graphs) return 'ingest';
      return cur.sv && cur.graphs ? 'remove_graph' : 'ingest_no_graph';
    };

    /** The Status column in columns mode: which stores the row is in now. */
    const storesLabel = (index: number): string => {
      const c = ingestStatusFor(index);
      if (c?.status === 'removed') return 'removed';
      const cur = currentFor(index);
      if (!cur.sv && !cur.graphs) return 'not ingested';
      return (cur.graphs ? 'search+vector, graphs' : 'search+vector') + (cur.sync ? ' (synced)' : '');
    };

    /** A sync change for a checked row: false stops it, true resumes it, null = none. */
    const syncChange = (index: number): boolean | null => {
      const want = wantFor(index).sync;
      return want !== currentFor(index).sync ? want : null;
    };

    /**
     * What START PROCESSING sends for the checked rows: per row a store action and/or an Auto
     * Sync change. A row no sync covers yet, with Auto Sync checked, is ingested with
     * auto_sync: true: the backend makes this run\'s datasource an auto sync watching it.
     */
    const itemActions = () => {
      const rows: any[] = [];
      for (const i of [...selectedItems.value].sort((a, b) => a - b)) {
        const item = ingestStatusRequest?.items?.[i];
        if (!item) continue;
        const ref = { path: item.path, id: item.id, is_folder: !!item.is_folder };
        const sync = syncChange(i);
        if (sync === true && !coveredBySync(i)) {
          rows.push({ ...ref, action: actionFor(i) ?? (wantFor(i).graphs ? 'ingest' : 'ingest_no_graph'), auto_sync: true });
          continue;
        }
        const action = actionFor(i);
        if (!action && sync === null) continue;
        rows.push({ ...ref, action: action ?? 'keep', ...(sync === null ? {} : { auto_sync: sync }) });
      }
      return rows;
    };

    /**
     * A run is over. The rows' choices go back to their defaults -- rows in the stores
     * unchecked, columns showing what each row is in now -- so a second START does not repeat
     * the run. The ingest status is asked again once the run's document_state rows are written.
     */
    const afterRun = () => {
      wantSearch.value = {};
      wantGraphs.value = {};
      wantSync.value = {};
      selectedItems.value = [];
      awaitingStatus = true;
      setTimeout(() => {
        awaitingStatus = false;
        ingestStatusKey = '';
        refreshIngestStatus();
      }, 4000);
    };

    let foregroundRun = false;  // a background start also flips isProcessing; only reset after a real run
    watch(isProcessing, (now, before) => {
      if (before && !now && foregroundRun) afterRun();
      if (!now) foregroundRun = false;
    });

    // ── Jobs sub-tab ──────────────────────────────────────────────────────────────────
    const runInBackground = ref(false);
    const subTab = ref(0);  // 0 Processing, 1 Jobs
    const jobs = ref<any[]>([]);
    const watchedJobs = ref<string[]>([]);  // background jobs started here, until they finish
    const jobRunning = (job: any): boolean => !TERMINAL_JOB.includes(job.status);
    const runningJobCount = computed(() => jobs.value.filter(jobRunning).length);

    const showFinishedJob = async (job: any) => {
      if (!isProcessing.value) {
        try {
          const res = await axios.get(`/api/processing-status/${job.processing_id}`);
          const status = res.data;
          statusData.value = null;
          lastStatusData.value = status;
          processingProgress.value = status.status === 'completed' ? 100 : status.progress || 0;
          if (status.status === 'completed') successMessage.value = status.message || 'Background job finished.';
          else error.value = `Background job ${status.status}: ${status.error || status.message || ''}`;
        } catch { /* the job may have been cleared */ }
      }
      afterRun();
    };

    const loadJobs = async () => {
      try {
        const res = await axios.get('/api/processing-status');
        jobs.value = res.data?.jobs || [];
        for (const job of jobs.value) {
          if (watchedJobs.value.includes(job.processing_id) && !jobRunning(job)) {
            watchedJobs.value = watchedJobs.value.filter((id) => id !== job.processing_id);
            showFinishedJob(job);
          }
        }
      } catch (err) {
        console.warn('Job list unavailable:', err);
      }
    };

    // Refresh the job list while it is shown or a background job started here is still going:
    // every 3 s while a job runs, every 15 s when none does (still picks up auto sync runs)
    let jobsTimer: any = null;
    let jobsDelay = 0;
    const scheduleJobs = () => {
      const wanted = subTab.value === 1 || watchedJobs.value.length > 0;
      const delay = watchedJobs.value.length > 0 || jobs.value.some(jobRunning) ? 3000 : 15000;
      if (jobsTimer && (!wanted || delay < jobsDelay)) {  // stop, or a job just started
        clearTimeout(jobsTimer);
        jobsTimer = null;
      }
      if (wanted && !jobsTimer) {
        jobsDelay = delay;
        jobsTimer = setTimeout(async () => {
          jobsTimer = null;
          await loadJobs();
          scheduleJobs();
        }, delay);
      }
    };
    watch(() => [subTab.value, watchedJobs.value.length], () => {
      if (!jobsTimer && (subTab.value === 1 || watchedJobs.value.length > 0)) loadJobs();
      scheduleJobs();
    });
    onBeforeUnmount(() => clearTimeout(jobsTimer));

    const clearJobs = async () => {
      try {
        await axios.delete('/api/processing-status');
      } catch (err: any) {
        error.value = `Clear failed: ${err?.response?.data?.detail || err?.message || err}`;
      }
      loadJobs();
    };

    const cancelJob = async (job: any) => {
      try {
        await axios.post(`/api/cancel-processing/${job.processing_id}`, {});
      } catch (err: any) {
        error.value = `Cancel failed: ${err?.response?.data?.detail || err?.message || err}`;
      }
      loadJobs();
    };

    // A new selection opens on the Processing sub-tab, from the defaults
    watch(() => props.configurationTimestamp, () => {
      subTab.value = 0;
      wantSearch.value = {};
      wantGraphs.value = {};
      wantSync.value = {};
    });

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
          (props.configuredDataSource === 'cmis' || props.configuredDataSource === 'alfresco' || props.configuredDataSource === 'nuxeo')) {
        // Clear old processing messages when reconfiguring
        successMessage.value = '';
        error.value = '';
        
        // Reset hidden flag and increment reconfigured counter when repository sources are reconfigured
        repositoryItemsHidden.value = false;
        sourcesReconfiguredFlag.value++;

        // A fresh configuration starts from a clean table: the previous run's progress/status
        // otherwise stays on the rows and hides the "already ingested" check. Re-ask ingest status
        // even for an identical configuration -- the last run may have just ingested it.
        if (!isProcessing.value) {
          processingProgress.value = 0;
          processingStatus.value = '';
          currentProcessingId.value = null;
          statusData.value = null;
          lastStatusData.value = null;
        }
        ingestStatusKey = '';
        refreshIngestStatus();

        // Auto-select repository files after configuration (except rows already in the stores)
        setTimeout(() => {
          const currentFiles = displayFiles.value;
          selectedItems.value = currentFiles
            .map((_, index) => index)
            .filter((index) => ingestStatusFor(index)?.status !== 'synced');
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
      if (props.configuredDataSource === 'cmis' || props.configuredDataSource === 'alfresco' || props.configuredDataSource === 'nuxeo') {
        console.log('Repository displayFiles changed:', newFiles.length, 'files');
        // every row except those already in the stores (see refreshIngestStatus)
        selectedItems.value = newFiles
          .map((_, index) => index)
          .filter((index) => ingestStatusFor(index)?.status !== 'synced');
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
      enableSync,  // was never returned, so the "Enable auto change sync" checkbox did nothing
      ingestStatusLabel,
      ingestStatusTooltip,
      columnsMode,
      canSearchVector,
      canGraphs,
      inStores,
      wantFor,
      setWant,
      allRows,
      countWant,
      storesLabel,
      runInBackground,
      subTab,
      jobs,
      jobRunning,
      runningJobCount,
      loadJobs,
      clearJobs,
      cancelJob,
      ingestStatusFor,
      ingestedRowCount,
      showIngestStatus,
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
/* Search+Vector / Graphs header labels stay on one line */
:deep(.v-data-table__th .v-label) {
  white-space: nowrap;
}
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
