<template>
  <BaseSourceForm
    title="CMIS Repository"
    description="Connect to a CMIS-compliant content management system"
  >
    <v-text-field
      :model-value="url"
      @update:model-value="handleUrlChange"
      label="CMIS Repository URL *"
      variant="outlined"
      class="mb-4"
      :placeholder="placeholder"
      required
    />
    
    <v-row class="mb-4">
      <v-col cols="6">
        <v-text-field
          :model-value="username"
          @update:model-value="handleUsernameChange"
          label="Username *"
          variant="outlined"
          required
        />
      </v-col>
      <v-col cols="6">
        <v-text-field
          :model-value="password"
          @update:model-value="handlePasswordChange"
          label="Password *"
          type="password"
          variant="outlined"
          required
        />
      </v-col>
    </v-row>
    
    <v-text-field
      :model-value="folderPath"
      @update:model-value="handleFolderPathChange"
      label="Folder Path *"
      variant="outlined"
      class="mb-4"
      placeholder="e.g., /Sites/example/documentLibrary"
      hint="Path to the folder containing documents to process"
      persistent-hint
      required
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'CMISSourceForm',
  components: {
    BaseSourceForm
  },
  props: {
    url: {
      type: String,
      default: ''
    },
    username: {
      type: String,
      default: 'admin'
    },
    password: {
      type: String,
      default: 'admin'
    },
    folderPath: {
      type: String,
      default: '/Shared/GraphRAG'
    }
  },
  emits: ['update:url', 'update:username', 'update:password', 'update:folderPath', 'configuration-change', 'validation-change'],
  setup(props, { emit }) {
    const placeholder = computed(() => {
      const baseUrl = import.meta.env.VITE_CMIS_BASE_URL || 'http://localhost:8080';
      return `e.g., ${baseUrl}/alfresco/api/-default-/public/cmis/versions/1.1/atom`;
    });

    const isValid = computed(() => {
      return props.url.trim() !== '' && 
             props.username.trim() !== '' && 
             props.password.trim() !== '' && 
             props.folderPath.trim() !== '';
    });

    const config = computed(() => ({
      url: props.url,
      username: props.username,
      password: props.password,
      folder_path: props.folderPath
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleUrlChange = (value: string) => {
      emit('update:url', value);
    };

    const handleUsernameChange = (value: string) => {
      emit('update:username', value);
    };

    const handlePasswordChange = (value: string) => {
      emit('update:password', value);
    };

    const handleFolderPathChange = (value: string) => {
      emit('update:folderPath', value);
    };

    return {
      placeholder,
      handleUrlChange,
      handleUsernameChange,
      handlePasswordChange,
      handleFolderPathChange,
    };
  },
});
</script>
