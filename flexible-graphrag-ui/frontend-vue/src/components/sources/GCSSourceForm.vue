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
      v-model="prefix"
      label="Prefix (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="sample-docs/"
      hint="Optional: folder path prefix (e.g., 'sample-docs/' for a specific folder)"
      persistent-hint
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
    credentials: {
      type: String,
      default: ''
    }
  },
  emits: [
    'update:bucketName', 'update:credentials', 
    'configuration-change', 'validation-change'
  ],
  setup(props, { emit }) {
    const prefix = ref('');

    const isValid = computed(() => {
      return props.bucketName.trim() !== '' && 
             props.credentials.trim() !== '';
    });

    const config = computed(() => ({
      bucket_name: props.bucketName,
      credentials: props.credentials,
      prefix: prefix.value || undefined
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleBucketNameChange = (value: string) => {
      emit('update:bucketName', value);
    };

    const handleCredentialsChange = (value: string) => {
      emit('update:credentials', value);
    };

    return {
      prefix,
      handleBucketNameChange,
      handleCredentialsChange,
    };
  },
});
</script>
