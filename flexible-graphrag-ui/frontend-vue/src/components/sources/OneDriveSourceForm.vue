<template>
  <BaseSourceForm
    title="Microsoft OneDrive"
    description="Connect to OneDrive using Azure app registration credentials"
  >
    <v-row class="mb-2">
      <v-col cols="6">
        <v-text-field
          :model-value="userPrincipalName"
          @update:model-value="handleUserPrincipalNameChange"
          label="User Principal Name *"
          variant="outlined"
          placeholder="user@domain.com"
          hint="User principal name (email)"
          persistent-hint
          required
        />
      </v-col>
      <v-col cols="6">
        <v-text-field
          :model-value="clientId"
          @update:model-value="handleClientIdChange"
          label="Client ID *"
          variant="outlined"
          placeholder="12345678-1234-1234-1234-123456789012"
          required
        />
      </v-col>
    </v-row>
    
    <v-row class="mb-2">
      <v-col cols="6">
        <v-text-field
          :model-value="clientSecret"
          @update:model-value="handleClientSecretChange"
          label="Client Secret *"
          variant="outlined"
          type="password"
          autocomplete="new-password"
          required
        />
      </v-col>
      <v-col cols="6">
        <v-text-field
          :model-value="tenantId"
          @update:model-value="handleTenantIdChange"
          label="Tenant ID *"
          variant="outlined"
          placeholder="common or tenant-id"
          required
        />
      </v-col>
    </v-row>
    
    <div class="d-flex ga-2 mb-2 align-start">
      <v-text-field
        :model-value="folderPath"
        @update:model-value="(v: string) => { folderPath = v; if (v) files = []; }"
        label="Folder Path (Optional)"
        variant="outlined"
        placeholder="Documents/Reports"
        hint="Optional: a folder in the user's OneDrive (empty: the whole drive)"
        persistent-hint
        :disabled="files.length > 0"
      />
      <v-btn
        variant="outlined"
        prepend-icon="mdi-folder-open"
        height="56"
        :disabled="!isValid"
        :title="isValid ? 'Pick a folder or files in the user\'s OneDrive' : 'Fill in the user and the app credentials first'"
        @click="browseOpen = true"
      >
        Browse…
      </v-btn>
    </div>
    <PickedChips
      :items="files"
      @remove="(id: string) => { files = files.filter((f) => f.id !== id); }"
      @clear="files = []"
    />

    <v-text-field
      v-model="folderId"
      label="Folder ID (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="01BYE5RZ6QN6OWWLQZC5FK2GWWDURNZHIL"
      hint="Optional: specific OneDrive folder ID"
      persistent-hint
    />
    <SourceBrowser
      :open="browseOpen"
      :provider="provider"
      :title="`Pick a folder or files: ${userPrincipalName || 'OneDrive'}`"
      :mixed="false"
      @close="browseOpen = false"
      @select="handleBrowsed"
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';
import SourceBrowser from '../../browser/SourceBrowser.vue';
import PickedChips from '../../browser/PickedChips.vue';
import { remoteProvider } from '../../browser/remoteProvider';
import type { BrowseItem } from '../../browser/types';
import { ingestStarted } from '../../ingestSignal';

export default defineComponent({
  name: 'OneDriveSourceForm',
  components: {
    BaseSourceForm,
    SourceBrowser,
    PickedChips
  },
  props: {
    userPrincipalName: {
      type: String,
      default: ''
    },
    clientId: {
      type: String,
      default: ''
    },
    clientSecret: {
      type: String,
      default: ''
    },
    tenantId: {
      type: String,
      default: ''
    }
  },
  emits: [
    'update:userPrincipalName', 'update:clientId', 'update:clientSecret', 
    'update:tenantId', 'configuration-change', 'validation-change'
  ],
  setup(props, { emit }) {
    const folderPath = ref('');
    const folderId = ref('');
    // files picked in the browser (file_ids: the ingest then reads these instead of a folder)
    const files = ref<BrowseItem[]>([]);

    const isValid = computed(() => {
      return props.userPrincipalName.trim() !== '' && 
             props.clientId.trim() !== '' && 
             props.clientSecret.trim() !== '' && 
             props.tenantId.trim() !== '';
    });

    const config = computed(() => ({
      user_principal_name: props.userPrincipalName,
      client_id: props.clientId,
      client_secret: props.clientSecret,
      tenant_id: props.tenantId,
      folder_path: folderPath.value || undefined,
      folder_id: folderId.value || undefined,
      file_ids: files.value.length ? files.value.map((f) => f.id) : undefined
    }));

    // Browse the user's OneDrive with the credentials above (POST /api/browse)
    const browseOpen = ref(false);
    const provider = remoteProvider('onedrive', 'OneDrive', () => config.value);

    // an ingest started: the picked files empty (the run's rows stay in Processing)
    watch(ingestStarted, () => { files.value = []; });

    // one folder (folder_path), or files (file_ids): the browser keeps the two apart
    const handleBrowsed = (items: BrowseItem[]) => {
      if (!items.length) return;
      if (items[0].isDirectory) {
        folderPath.value = items[0].path || '';
        files.value = [];
      } else {
        files.value = items;
        folderPath.value = '';
      }
    };

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleUserPrincipalNameChange = (value: string) => {
      emit('update:userPrincipalName', value);
    };

    const handleClientIdChange = (value: string) => {
      emit('update:clientId', value);
    };

    const handleClientSecretChange = (value: string) => {
      emit('update:clientSecret', value);
    };

    const handleTenantIdChange = (value: string) => {
      emit('update:tenantId', value);
    };

    return {
      folderPath,
      folderId,
      files,
      isValid,
      browseOpen,
      provider,
      handleBrowsed,
      handleUserPrincipalNameChange,
      handleClientIdChange,
      handleClientSecretChange,
      handleTenantIdChange,
    };
  },
});
</script>
