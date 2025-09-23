<template>
  <BaseSourceForm
    title="Google Drive"
    description="Connect to Google Drive using service account credentials"
  >
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
import { defineComponent, computed, watch } from 'vue';
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
    const isValid = computed(() => {
      return props.credentials.trim() !== '';
    });

    const config = computed(() => ({
      credentials: props.credentials
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
      handleCredentialsChange,
    };
  },
});
</script>
