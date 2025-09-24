<template>
  <BaseSourceForm
    title="Google Cloud Storage"
    description="Connect to Google Cloud Storage buckets"
  >
    <v-text-field
      :model-value="bucketName"
      @update:model-value="handleBucketNameChange"
      label="Bucket Name *"
      variant="outlined"
      class="mb-2"
      placeholder="my-gcs-bucket"
      hint="GCS bucket name (required)"
      persistent-hint
      required
    />
    
    <v-text-field
      :model-value="projectId"
      @update:model-value="handleProjectIdChange"
      label="Project ID *"
      variant="outlined"
      class="mb-2"
      placeholder="my-gcp-project"
      hint="Google Cloud project ID (required)"
      persistent-hint
      required
    />
    
    <v-textarea
      :model-value="credentials"
      @update:model-value="handleCredentialsChange"
      label="Service Account Credentials (JSON) *"
      variant="outlined"
      class="mb-2"
      placeholder='{"type": "service_account", "project_id": "...", ...}'
      hint="JSON service account key (required)"
      persistent-hint
      rows="4"
      required
    />
    
    <v-text-field
      v-model="prefix"
      label="Prefix (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="documents/reports/"
      hint="Optional: folder path prefix within bucket"
      persistent-hint
    />
    
    <v-text-field
      v-model="folderName"
      label="Folder Name (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="my-folder"
      hint="Optional: specific folder name"
      persistent-hint
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'GCSSourceForm',
  components: {
    BaseSourceForm
  },
  props: {
    bucketName: {
      type: String,
      default: ''
    },
    projectId: {
      type: String,
      default: ''
    },
    credentials: {
      type: String,
      default: ''
    }
  },
  emits: [
    'update:bucketName', 'update:projectId', 'update:credentials', 
    'configuration-change', 'validation-change'
  ],
  setup(props, { emit }) {
    const prefix = ref('');
    const folderName = ref('');

    const isValid = computed(() => {
      return props.bucketName.trim() !== '' && 
             props.projectId.trim() !== '' && 
             props.credentials.trim() !== '';
    });

    const config = computed(() => ({
      bucket_name: props.bucketName,
      project_id: props.projectId,
      credentials: props.credentials,
      prefix: prefix.value || undefined,
      folder_name: folderName.value || undefined
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleBucketNameChange = (value: string) => {
      emit('update:bucketName', value);
    };

    const handleProjectIdChange = (value: string) => {
      emit('update:projectId', value);
    };

    const handleCredentialsChange = (value: string) => {
      emit('update:credentials', value);
    };

    return {
      prefix,
      folderName,
      handleBucketNameChange,
      handleProjectIdChange,
      handleCredentialsChange,
    };
  },
});
</script>
