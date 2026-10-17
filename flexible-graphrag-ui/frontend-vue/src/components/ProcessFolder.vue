<template>
  <v-card class="pa-4 mb-4">
    <v-card-title>Process Documents</v-card-title>
    <v-card-text>
      <!-- Data Source Selection -->
      <v-select
        v-model="dataSource"
        :items="dataSourceOptions"
        label="Data Source"
        variant="outlined"
        class="mb-4"
        :disabled="isProcessing"
      ></v-select>

      <!-- File System Fields -->
      <template v-if="dataSource === 'filesystem'">
        <v-text-field
          v-model="folderPath"
          label="Folder Path (file or directory)"
          variant="outlined"
          :disabled="isProcessing"
          class="mb-4"
          placeholder="e.g., C:\Documents\reports or /home/user/docs/report.pdf"
        ></v-text-field>
      </template>

      <!-- CMIS Fields -->
      <template v-if="dataSource === 'cmis'">
        <v-text-field
          v-model="cmisUrl"
          label="CMIS Repository URL"
          variant="outlined"
          :disabled="isProcessing"
          class="mb-4"
          :placeholder="cmisPlaceholder"
        ></v-text-field>
        <v-row>
          <v-col cols="6">
            <v-text-field
              v-model="cmisUsername"
              label="Username"
              autocomplete="off"
              variant="outlined"
              :disabled="isProcessing"
              class="mb-4"
            ></v-text-field>
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="cmisPassword"
              label="Password"
              autocomplete="new-password"
              type="password"
              variant="outlined"
              :disabled="isProcessing"
              class="mb-4"
            ></v-text-field>
          </v-col>
        </v-row>
        <v-text-field
          v-model="folderPath"
          label="Folder Path"
          variant="outlined"
          :disabled="isProcessing"
          class="mb-4"
          placeholder="e.g., /Sites/example/documentLibrary"
        ></v-text-field>
      </template>

      <!-- Alfresco Fields -->
      <template v-if="dataSource === 'alfresco'">
        <v-text-field
          v-model="alfrescoUrl"
          label="Alfresco Base URL"
          variant="outlined"
          :disabled="isProcessing"
          class="mb-4"
          :placeholder="alfrescoPlaceholder"
        ></v-text-field>
        <v-row>
          <v-col cols="6">
            <v-text-field
              v-model="alfrescoUsername"
              label="Username"
              autocomplete="off"
              variant="outlined"
              :disabled="isProcessing"
              class="mb-4"
            ></v-text-field>
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="alfrescoPassword"
              label="Password"
              autocomplete="new-password"
              type="password"
              variant="outlined"
              :disabled="isProcessing"
              class="mb-4"
            ></v-text-field>
          </v-col>
        </v-row>
        <v-text-field
          v-model="folderPath"
          label="Path"
          variant="outlined"
          :disabled="isProcessing"
          class="mb-4"
          placeholder="e.g., /Sites/example/documentLibrary"
        ></v-text-field>
      </template>

      <!-- Processing Status -->
      <template v-if="isProcessing">
        <v-card
          color="info"
          variant="tonal"
          class="mb-4"
        >
          <v-card-text>
            <div class="d-flex align-center mb-2">
              <v-progress-circular
                indeterminate
                size="20"
                class="me-2"
              ></v-progress-circular>
              <span>{{ processingStatus || 'Processing documents...' }}</span>
            </div>
            <v-progress-linear
              :model-value="processingProgress"
              height="8"
              rounded
              color="primary"
              class="mb-2"
            ></v-progress-linear>
            <div class="text-caption text-medium-emphasis">
              {{ processingProgress }}% complete
              <div v-if="statusData?.file_progress" class="mt-1">
                {{ statusData.file_progress }}
              </div>
              <div v-if="statusData?.current_file" class="mt-1">
                Processing: {{ getFileName(statusData.current_file) }}
              </div>
              <div v-if="statusData?.current_phase" class="mt-1">
                Phase: {{ statusData.current_phase }}
              </div>
              <div v-if="statusData?.estimated_time_remaining" class="mt-1">
                Time remaining: {{ statusData.estimated_time_remaining }}
              </div>
            </div>
            <v-btn
              variant="outlined"
              color="error"
              size="small"
              @click="cancelProcessing"
              class="mt-2"
            >
              Cancel Processing
            </v-btn>
          </v-card-text>
        </v-card>
      </template>

      <v-btn
        color="primary"
        @click="handleProcessFolder"
        :disabled="!isFormValid || isProcessing"
        :loading="isProcessing"
        size="large"
      >
        {{ isProcessing ? 'Processing...' : 'Ingest Documents' }}
      </v-btn>

      <v-alert
        v-if="error"
        type="error"
        class="mt-4"
      >
        {{ error }}
      </v-alert>

      <v-alert
        v-if="success"
        type="success"
        class="mt-4"
      >
        {{ success }}
      </v-alert>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import axios from 'axios';
import { IngestRequest, AsyncProcessingResponse, ProcessingStatusResponse } from '../types/api';

const emit = defineEmits<{
  (e: 'processed', payload: { dataSource: string, path?: string }): void;
}>();

// Get folder path from environment variables or use default
const defaultFolderPath = import.meta.env.VITE_PROCESS_FOLDER_PATH || '/Shared/GraphRAG';

// Data source options
const dataSourceOptions = [
  { title: 'File System', value: 'filesystem' },
  { title: 'CMIS Repository', value: 'cmis' },
  { title: 'Alfresco Repository', value: 'alfresco' }
];

// Define reactive variables
const dataSource = ref('filesystem');
const folderPath = ref(defaultFolderPath);

// CMIS fields - use environment variables with fallback
const cmisUrl = ref(`${import.meta.env.VITE_CMIS_BASE_URL || 'http://localhost:8080'}/alfresco/api/-default-/public/cmis/versions/1.1/atom`);
// no pre-filled credentials (were admin/admin)
const cmisUsername = ref('');
const cmisPassword = ref('');

// Alfresco fields - use environment variables with fallback
const alfrescoUrl = ref(`${import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080'}/alfresco`);
const alfrescoUsername = ref('');
const alfrescoPassword = ref('');

// UI state
const isProcessing = ref(false);
const error = ref('');
const success = ref('');
const processingStatus = ref('');
const processingProgress = ref(0);
const currentProcessingId = ref<string | null>(null);
const statusData = ref<any>(null);

// Computed properties for placeholders (safer than using import.meta.env in templates)
const cmisPlaceholder = computed(() => {
  const baseUrl = import.meta.env.VITE_CMIS_BASE_URL || 'http://localhost:8080';
  return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
});

const alfrescoPlaceholder = computed(() => {
  const baseUrl = import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080';
  return `e.g., ${baseUrl}/alfresco`;
});

// Computed property for form validation
const isFormValid = computed(() => {
  switch (dataSource.value) {
    case 'filesystem':
      return folderPath.value.trim() !== '';
    case 'cmis':
      return folderPath.value.trim() !== '' && 
             cmisUrl.value.trim() !== '' && 
             cmisUsername.value.trim() !== '' && 
             cmisPassword.value.trim() !== '';
    case 'alfresco':
      return folderPath.value.trim() !== '' && 
             alfrescoUrl.value.trim() !== '' && 
             alfrescoUsername.value.trim() !== '' && 
             alfrescoPassword.value.trim() !== '';
    default:
      return false;
  }
});

// Clear messages when data source changes
watch(dataSource, () => {
  error.value = '';
  success.value = '';
  processingStatus.value = '';
  processingProgress.value = 0;
});

// Helper function to extract filename from path
const getFileName = (filePath: string): string => {
  return filePath.split(/[/\\]/).pop() || filePath;
};

// Polling function for processing status
const pollProcessingStatus = async (processingId: string): Promise<void> => {
  try {
    const response = await axios.get<ProcessingStatusResponse>(`/api/processing-status/${processingId}`);
    const status = response.data;
    
    processingStatus.value = status.message;
    processingProgress.value = status.progress;
    statusData.value = status;  // Store full status for enhanced progress display
    
    if (status.status === 'completed') {
      isProcessing.value = false;
      processingStatus.value = '';
      processingProgress.value = 0;
      currentProcessingId.value = null;
      success.value = status.message || 'Documents ingested successfully!';
      emit('processed', { 
        dataSource: dataSource.value, 
        path: folderPath.value 
      });
    } else if (status.status === 'failed') {
      isProcessing.value = false;
      processingStatus.value = '';
      processingProgress.value = 0;
      currentProcessingId.value = null;
      error.value = status.error || 'Processing failed';
    } else if (status.status === 'cancelled') {
      isProcessing.value = false;
      processingStatus.value = '';
      processingProgress.value = 0;
      currentProcessingId.value = null;
      success.value = 'Processing cancelled successfully';
    } else if (status.status === 'started' || status.status === 'processing') {
      // Continue polling
      setTimeout(() => pollProcessingStatus(processingId), 2000);
    }
  } catch (err: any) {
    console.error('Error checking processing status:', err);
    error.value = 'Error checking processing status';
    isProcessing.value = false;
    currentProcessingId.value = null;
  }
};

const processFolder = async (): Promise<boolean> => {
  if (!isFormValid.value || isProcessing.value) return false;
  
  try {
    isProcessing.value = true;
    error.value = '';
    success.value = '';
    
    console.log('Sending request to process documents with data source:', dataSource.value);
    
    const request: IngestRequest = {
      data_source: dataSource.value
    };

    if (dataSource.value === 'filesystem') {
      request.paths = [folderPath.value];
    } else if (dataSource.value === 'cmis') {
      request.paths = [folderPath.value];
      request.cmis_config = {
        url: cmisUrl.value,
        username: cmisUsername.value,
        password: cmisPassword.value,
        folder_path: folderPath.value
      };
    } else if (dataSource.value === 'alfresco') {
      request.paths = [folderPath.value];
      request.alfresco_config = {
        url: alfrescoUrl.value,
        username: alfrescoUsername.value,
        password: alfrescoPassword.value,
        path: folderPath.value
      };
    }
    
    const response = await axios.post<AsyncProcessingResponse>('/api/ingest', request, {
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    });
    
    console.log('Response received:', response);
    
    // Handle async processing response
    if (response.data.status === 'started') {
      processingStatus.value = response.data.message;
      processingProgress.value = 0;
      currentProcessingId.value = response.data.processing_id;
      success.value = `Processing started: ${response.data.estimated_time || 'Please wait...'}`;
      // Start polling for status
      setTimeout(() => pollProcessingStatus(response.data.processing_id), 2000);
      return true;
    } else if (response.data.status === 'completed') {
      success.value = 'Documents ingested successfully!';
      emit('processed', { 
        dataSource: dataSource.value, 
        path: folderPath.value 
      });
      return true;
    } else if (response.data.status === 'failed') {
      error.value = response.data.error || 'Processing failed';
      return false;
    } else {
      error.value = response.data.error || 'Unknown processing status';
      return false;
    }
  } catch (err: any) {
    console.error('Error processing documents:', {
      message: err.message,
      response: err.response?.data,
      status: err.response?.status,
      headers: err.response?.headers
    });
    error.value = err.response?.data?.detail || err.response?.data?.error || 'Error processing documents';
    isProcessing.value = false;
    currentProcessingId.value = null;
    return false;
  }
};

const cancelProcessing = async (): Promise<void> => {
  if (!currentProcessingId.value) return;
  
  try {
    const response = await axios.post(`/api/cancel-processing/${currentProcessingId.value}`);
    if (response.data.success) {
      success.value = 'Processing cancelled successfully';
      isProcessing.value = false;
      processingStatus.value = '';
      processingProgress.value = 0;
      currentProcessingId.value = null;
    } else {
      error.value = 'Failed to cancel processing';
    }
  } catch (err: any) {
    console.error('Error cancelling processing:', err);
    error.value = 'Error cancelling processing';
  }
};

const handleProcessFolder = (event: Event) => {
  event.preventDefault();
  processFolder();
};
</script>