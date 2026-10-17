<template>
  <BaseSourceForm
    title="Google Drive"
    description="Connect to Google Drive using service account credentials"
  >
    <v-text-field
      v-model="folderId"
      label="Folder ID (Optional)"
      variant="outlined"
      class="mb-4"
      placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
      hint="Optional: Google Drive folder ID to process specific folder. Leave empty to process all accessible files."
      persistent-hint
      autocomplete="off"
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
import { defineComponent, computed, watch, ref } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'GoogleDriveSourceForm',
  components: {
    BaseSourceForm
  },
  props: {
    credentials: {
      type: String,
      default: ''
    }
  },
  emits: ['update:credentials', 'configuration-change', 'validation-change'],
  setup(props, { emit }) {
    const folderId = ref('');

    const isValid = computed(() => {
      return props.credentials.trim() !== '';
    });

    const config = computed(() => ({
      credentials: props.credentials,
      folder_id: folderId.value.trim() || undefined
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleCredentialsChange = (value: string) => {
      emit('update:credentials', value);
    };

    return {
      folderId,
      handleCredentialsChange,
    };
  },
});
</script>
