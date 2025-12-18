<template>
  <BaseSourceForm
    title="Alfresco Repository"
    description="Connect to an Alfresco content management system"
  >
    <v-text-field
      :model-value="url"
      @update:model-value="handleUrlChange"
      label="Alfresco Base URL *"
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
      :model-value="path"
      @update:model-value="handlePathChange"
      label="Path *"
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
  name: 'AlfrescoSourceForm',
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
    path: {
      type: String,
      default: '/Shared/GraphRAG'
    }
  },
  emits: ['update:url', 'update:username', 'update:password', 'update:path', 'configuration-change', 'validation-change'],
  setup(props, { emit }) {
    const placeholder = computed(() => {
      const baseUrl = import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080';
      return `e.g., ${baseUrl}`;
    });

    const isValid = computed(() => {
      return props.url.trim() !== '' && 
             props.username.trim() !== '' && 
             props.password.trim() !== '' && 
             props.path.trim() !== '';
    });

    const config = computed(() => ({
      url: props.url,
      username: props.username,
      password: props.password,
      path: props.path
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

    const handlePathChange = (value: string) => {
      emit('update:path', value);
    };

    return {
      placeholder,
      handleUrlChange,
      handleUsernameChange,
      handlePasswordChange,
      handlePathChange,
    };
  },
});
</script>
