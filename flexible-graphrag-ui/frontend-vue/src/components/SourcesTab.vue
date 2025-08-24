<template>
  <div class="pa-4">
    <h2 class="mb-4">Data Source Configuration</h2>
    
    <!-- Data Source Selection -->
    <v-select
      v-model="dataSource"
      :items="dataSourceOptions"
      label="Data Source"
      variant="outlined"
      class="mb-4"
    ></v-select>

    <!-- File Upload -->
    <template v-if="dataSource === 'upload'">
      <v-card
        :class="[
          'pa-6 mb-4 text-center cursor-pointer',
          isDragOver ? 'drag-over' : 'drag-normal'
        ]"
        :style="dropZoneStyle"
        @drop="handleFileDrop"
        @dragover="handleDragOver"
        @dragenter="handleDragEnter"
        @dragleave="handleDragLeave"
        @click="() => fileInputRef?.click()"
      >
        <h3 class="mb-2" :style="{ color: '#ffffff' }">
          Drop files here or click to select
        </h3>
        <p :style="{ color: '#ffffff' }">
          Supports: PDF, DOCX, XLSX, PPTX, TXT, MD, HTML, CSV, PNG, JPG
        </p>
        <input
          ref="fileInputRef"
          type="file"
          multiple
          accept=".pdf,.docx,.xlsx,.pptx,.txt,.md,.html,.csv,.png,.jpg,.jpeg"
          @change="handleFileSelect"
          style="display: none"
        />
      </v-card>

      <!-- Selected Files Display -->
      <div v-if="selectedFiles.length > 0" class="mb-4">
        <h4 class="mb-2">Selected Files ({{ selectedFiles.length }}):</h4>
        <v-card
          v-for="(file, index) in selectedFiles"
          :key="index"
          class="pa-3 mb-2"
          variant="outlined"
        >
          <div class="d-flex align-center justify-space-between">
            <div>
              <div class="font-weight-medium">{{ file.name }}</div>
              <div class="text-caption text-medium-emphasis">{{ formatFileSize(file.size) }}</div>
            </div>
            <v-btn
              color="error"
              variant="text"
              size="small"
              @click="removeFile(index)"
            >
              Remove
            </v-btn>
          </div>
        </v-card>
      </div>

      <!-- Upload Progress -->
      <div v-if="isUploading" class="mb-4">
        <p class="mb-2">Uploading files... {{ uploadProgress }}%</p>
        <v-progress-linear
          :model-value="uploadProgress"
          color="primary"
        ></v-progress-linear>
      </div>
    </template>

    <!-- CMIS Fields -->
    <template v-if="dataSource === 'cmis'">
      <v-text-field
        v-model="cmisUrl"
        label="CMIS Repository URL"
        variant="outlined"
        class="mb-4"
        :placeholder="cmisPlaceholder"
      ></v-text-field>
      <v-row class="mb-4">
        <v-col cols="6">
          <v-text-field
            v-model="cmisUsername"
            label="Username"
            variant="outlined"
          ></v-text-field>
        </v-col>
        <v-col cols="6">
          <v-text-field
            v-model="cmisPassword"
            label="Password"
            type="password"
            variant="outlined"
          ></v-text-field>
        </v-col>
      </v-row>
      <v-text-field
        v-model="folderPath"
        label="Folder Path"
        variant="outlined"
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
        class="mb-4"
        :placeholder="alfrescoPlaceholder"
      ></v-text-field>
      <v-row class="mb-4">
        <v-col cols="6">
          <v-text-field
            v-model="alfrescoUsername"
            label="Username"
            variant="outlined"
          ></v-text-field>
        </v-col>
        <v-col cols="6">
          <v-text-field
            v-model="alfrescoPassword"
            label="Password"
            type="password"
            variant="outlined"
          ></v-text-field>
        </v-col>
      </v-row>
      <v-text-field
        v-model="folderPath"
        label="Path"
        variant="outlined"
        class="mb-4"
        placeholder="e.g., /Sites/example/documentLibrary"
      ></v-text-field>
    </template>

    <!-- Configure Processing Button -->
    <div class="d-flex align-center mt-4">
      <v-btn
        color="primary"
        size="large"
        :disabled="!isFormValid"
        @click="configureProcessing"
      >
        CONFIGURE PROCESSING →
      </v-btn>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import axios from 'axios';

export default defineComponent({
  name: 'SourcesTab',
  emits: ['configure-processing', 'sources-configured'],
  setup(_, { emit }) {
    // Data source options
    const dataSourceOptions = [
      { title: 'File Upload', value: 'upload' },
      { title: 'Alfresco Repository', value: 'alfresco' },
      { title: 'CMIS Repository', value: 'cmis' },
    ];

    // State
    const dataSource = ref('upload');
    const folderPath = ref('/Shared/GraphRAG');
    const selectedFiles = ref<File[]>([]);
    const isDragOver = ref(false);
    const fileInputRef = ref<HTMLInputElement>();
    const isUploading = ref(false);
    const uploadProgress = ref(0);

    // CMIS state
    const cmisUrl = ref(`${import.meta.env.VITE_CMIS_BASE_URL || 'http://localhost:8080'}/alfresco/api/-default-/public/cmis/versions/1.1/atom`);
    const cmisUsername = ref('admin');
    const cmisPassword = ref('admin');

    // Alfresco state
    const alfrescoUrl = ref(`${import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080'}/alfresco`);
    const alfrescoUsername = ref('admin');
    const alfrescoPassword = ref('admin');

    // Computed
    const cmisPlaceholder = computed(() => {
      const baseUrl = import.meta.env.VITE_CMIS_BASE_URL || 'http://localhost:8080';
      return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
    });

    const alfrescoPlaceholder = computed(() => {
      const baseUrl = import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080';
      return `e.g., ${baseUrl}/alfresco`;
    });

    const dropZoneStyle = computed(() => ({
      border: isDragOver.value ? '2px solid #ffffff' : '2px dashed #ffffff',
      backgroundColor: isDragOver.value ? '#000000' : '#1976d2', // Black on hover, blue default like React
      transition: 'all 0.2s ease-in-out',
    }));

    const isFormValid = computed(() => {
      switch (dataSource.value) {
        case 'upload':
          return selectedFiles.value.length > 0;
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

    const handleFileSelect = (event: Event) => {
      const target = event.target as HTMLInputElement;
      const files = target.files;
      if (files) {
        selectedFiles.value = Array.from(files);
      }
    };

    const handleFileDrop = (event: DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      isDragOver.value = false;
      
      const files = event.dataTransfer?.files;
      if (files) {
        selectedFiles.value = Array.from(files);
      }
    };

    const handleDragOver = (event: DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'copy';
      }
    };

    const handleDragEnter = (event: DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      isDragOver.value = true;
      if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'copy';
      }
    };

    const handleDragLeave = (event: DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      const x = event.clientX;
      const y = event.clientY;
      
      if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
        isDragOver.value = false;
      }
    };

    const removeFile = (index: number) => {
      selectedFiles.value = selectedFiles.value.filter((_, i) => i !== index);
    };

    const configureProcessing = () => {
      emit('sources-configured', {
        dataSource: dataSource.value,
        files: selectedFiles.value,
        folderPath: folderPath.value,
        cmisConfig: dataSource.value === 'cmis' ? {
          url: cmisUrl.value,
          username: cmisUsername.value,
          password: cmisPassword.value,
          folder_path: folderPath.value
        } : undefined,
        alfrescoConfig: dataSource.value === 'alfresco' ? {
          url: alfrescoUrl.value,
          username: alfrescoUsername.value,
          password: alfrescoPassword.value,
          path: folderPath.value
        } : undefined,
      });
      emit('configure-processing');
    };

    // Clear selected files when data source changes
    watch(dataSource, () => {
      selectedFiles.value = [];
      // Note: Preserve form field values (URLs, credentials, etc.) so users don't have to retype
    });

    return {
      dataSourceOptions,
      dataSource,
      folderPath,
      selectedFiles,
      isDragOver,
      fileInputRef,
      isUploading,
      uploadProgress,
      cmisUrl,
      cmisUsername,
      cmisPassword,
      alfrescoUrl,
      alfrescoUsername,
      alfrescoPassword,
      cmisPlaceholder,
      alfrescoPlaceholder,
      dropZoneStyle,
      isFormValid,
      formatFileSize,
      handleFileSelect,
      handleFileDrop,
      handleDragOver,
      handleDragEnter,
      handleDragLeave,
      removeFile,
      configureProcessing,
    };
  },
});
</script>

<style scoped>
.cursor-pointer {
  cursor: pointer;
}

/* CSS hover styles removed - now handled by computed dropZoneStyle */

.drag-normal {
  background-color: #1976d2 !important;
}
</style>
