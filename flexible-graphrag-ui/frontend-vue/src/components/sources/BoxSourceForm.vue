<template>
  <BaseSourceForm
    title="Box"
    description="Connect to Box cloud storage"
  >
    <v-text-field
      :model-value="clientId"
      @update:model-value="handleClientIdChange"
      label="Client ID *"
      variant="outlined"
      class="mb-2"
      placeholder="your-box-client-id"
      required
    />
    
    <v-text-field
      :model-value="clientSecret"
      @update:model-value="handleClientSecretChange"
      label="Client Secret *"
      variant="outlined"
      class="mb-2"
      type="password"
      required
    />
    
    <v-text-field
      :model-value="developerToken"
      @update:model-value="handleDeveloperTokenChange"
      label="Developer Token *"
      variant="outlined"
      class="mb-2"
      type="password"
      hint="Box developer token for authentication"
      persistent-hint
      required
    />
    
    <v-text-field
      v-model="folderId"
      label="Folder ID (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="123456789"
      hint="Optional: specific Box folder ID"
      persistent-hint
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'BoxSourceForm',
  components: {
    BaseSourceForm
  },
  props: {
    clientId: {
      type: String,
      default: ''
    },
    clientSecret: {
      type: String,
      default: ''
    },
    developerToken: {
      type: String,
      default: ''
    }
  },
  emits: [
    'update:clientId', 'update:clientSecret', 'update:developerToken', 
    'configuration-change', 'validation-change'
  ],
  setup(props, { emit }) {
    const folderId = ref('');

    const isValid = computed(() => {
      return props.clientId.trim() !== '' && 
             props.clientSecret.trim() !== '' && 
             props.developerToken.trim() !== '';
    });

    const config = computed(() => ({
      client_id: props.clientId,
      client_secret: props.clientSecret,
      developer_token: props.developerToken,
      folder_id: folderId.value || undefined
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleClientIdChange = (value: string) => {
      emit('update:clientId', value);
    };

    const handleClientSecretChange = (value: string) => {
      emit('update:clientSecret', value);
    };

    const handleDeveloperTokenChange = (value: string) => {
      emit('update:developerToken', value);
    };

    return {
      folderId,
      handleClientIdChange,
      handleClientSecretChange,
      handleDeveloperTokenChange,
    };
  },
});
</script>
