<template>
  <BaseSourceForm
    title="File Upload"
    description="Upload documents directly from your computer"
  >
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
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'FileUploadForm',
  components: {
    BaseSourceForm
  },
  props: {
    selectedFiles: {
      type: Array as () => File[],
      default: () => []
    }
  },
  emits: ['update:selectedFiles', 'configuration-change', 'validation-change'],
  setup(props, { emit }) {
    const isDragOver = ref(false);
    const fileInputRef = ref<HTMLInputElement>();

    const dropZoneStyle = computed(() => ({
      border: isDragOver.value ? '2px solid #ffffff' : '2px dashed #ffffff',
      backgroundColor: isDragOver.value ? '#000000' : '#1976d2',
      transition: 'all 0.2s ease-in-out',
    }));

    const isValid = computed(() => {
      return props.selectedFiles.length > 0;
    });

    const config = computed(() => ({
      files: props.selectedFiles
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

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
        requestAnimationFrame(() => {
          emit('update:selectedFiles', Array.from(files));
          target.value = '';
        });
      }
    };

    const handleFileDrop = (event: DragEvent) => {
      event.preventDefault();
      event.stopPropagation();
      isDragOver.value = false;
      
      const files = event.dataTransfer?.files;
      if (files) {
        requestAnimationFrame(() => {
          emit('update:selectedFiles', Array.from(files));
        });
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
      const newFiles = props.selectedFiles.filter((_, i) => i !== index);
      emit('update:selectedFiles', newFiles);
    };

    return {
      isDragOver,
      fileInputRef,
      dropZoneStyle,
      formatFileSize,
      handleFileSelect,
      handleFileDrop,
      handleDragOver,
      handleDragEnter,
      handleDragLeave,
      removeFile,
    };
  },
});
</script>

<style scoped>
.cursor-pointer {
  cursor: pointer;
}

.drag-normal {
  background-color: #1976d2 !important;
}
</style>
