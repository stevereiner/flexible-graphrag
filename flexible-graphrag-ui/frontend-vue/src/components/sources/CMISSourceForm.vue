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
    
    <SourceSignInSection
      source="cmis" :url="url" :session="session" :using-sign-in="usingSignIn"
      v-model:use-other="useOther"
    />

    <v-row v-if="!usingSignIn" class="mb-4">
      <v-col cols="6">
        <v-text-field
          :model-value="username"
          @update:model-value="handleUsernameChange"
          label="Username *"
          autocomplete="off"
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
          autocomplete="new-password"
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
import { defineComponent, computed, watch, toRef } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';
import SourceSignInSection from '../../auth/SourceSignInSection.vue';
import { useSourceSession } from '../../auth/useSourceSession';

export default defineComponent({
  name: 'CMISSourceForm',
  components: {
    BaseSourceForm,
    SourceSignInSection
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

    // The CMIS sign-in (header / dialog): for an Alfresco or Nuxeo CMIS server it holds that
    // vendor's ticket / token, which the ingest then uses instead of a password.
    const { session, useOther, usingSignIn, credential } = useSourceSession('cmis', toRef(props, 'url'));

    const isValid = computed(() => {
      if (props.url.trim() === '' || props.folderPath.trim() === '') return false;
      if (usingSignIn.value) return true;
      return props.username.trim() !== '' && props.password.trim() !== '';
    });

    const config = computed(() => (
      usingSignIn.value && credential.value
        ? { url: props.url, folder_path: props.folderPath, ...credential.value }
        : { url: props.url, username: props.username, password: props.password, folder_path: props.folderPath }
    ));

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
      session,
      useOther,
      usingSignIn,
      placeholder,
      handleUrlChange,
      handleUsernameChange,
      handlePasswordChange,
      handleFolderPathChange,
    };
  },
});
</script>
