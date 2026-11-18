<template>
  <BaseSourceForm
    title="Microsoft SharePoint"
    description="Connect to SharePoint sites using Azure app registration credentials"
  >
    <v-text-field
      :model-value="siteName"
      @update:model-value="handleSiteNameChange"
      label="Site Name *"
      variant="outlined"
      class="mb-2"
      placeholder="sitename"
      hint="SharePoint site name (not full URL, just the site name)"
      persistent-hint
      required
    />
    
    <v-text-field
      v-model="siteId"
      label="Site ID (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="12345678-1234-1234-1234-123456789012"
      hint="Optional: Site ID for Sites.Selected permission (recommended for security)"
      persistent-hint
    />
    
    <v-text-field
      :model-value="clientId"
      @update:model-value="handleClientIdChange"
      label="Client ID *"
      variant="outlined"
      class="mb-2"
      placeholder="12345678-1234-1234-1234-123456789012"
      hint="Azure app registration client ID (required)"
      persistent-hint
      required
    />
    
    <div class="d-flex ga-2 mb-2">
      <v-text-field
        :model-value="clientSecret"
        @update:model-value="handleClientSecretChange"
        label="Client Secret *"
        variant="outlined"
        type="password"
          autocomplete="new-password"
        placeholder="client-secret-here"
        hint="Azure app registration client secret (required)"
        persistent-hint
        required
      />
      
      <v-text-field
        :model-value="tenantId"
        @update:model-value="handleTenantIdChange"
        label="Tenant ID *"
        variant="outlined"
        placeholder="tenant-id"
        hint="Azure tenant ID (required)"
        persistent-hint
        required
      />
    </div>
    
    <v-text-field
      v-model="folderId"
      label="Folder ID (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="01BYE5RZ6QN6OWWLQZC5FK2GWWDURNZHIL"
      hint="Optional: specific folder ID (replaces document library)"
      persistent-hint
    />
    
    <div class="d-flex ga-2 mb-2 align-start">
      <v-text-field
        :model-value="folderPath"
        @update:model-value="handleFolderPathChange"
        label="Folder Path (Optional)"
        variant="outlined"
        placeholder="Reports/2024"
        hint="Optional: a folder in the site's document library (empty: the whole library)"
        persistent-hint
        autocomplete="off"
      />
      <v-btn
        variant="outlined"
        prepend-icon="mdi-folder-open"
        height="56"
        :disabled="!isValid"
        :title="isValid ? 'Pick a folder in the site\'s document library' : 'Fill in the site and the app credentials first'"
        @click="browseOpen = true"
      >
        Browse…
      </v-btn>
    </div>
    <SourceBrowser
      :open="browseOpen"
      :provider="provider"
      :title="`Pick a folder: ${siteName || 'SharePoint'}`"
      :files="false"
      :multiple="false"
      @close="browseOpen = false"
      @select="handleBrowsed"
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';
import SourceBrowser from '../../browser/SourceBrowser.vue';
import { remoteProvider } from '../../browser/remoteProvider';
import type { BrowseItem } from '../../browser/types';

export default defineComponent({
  name: 'SharePointSourceForm',
  components: {
    BaseSourceForm,
    SourceBrowser
  },
  props: {
    siteName: {
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
    'update:siteName', 
    'update:clientId', 
    'update:clientSecret', 
    'update:tenantId', 
    'configuration-change', 
    'validation-change'
  ],
  setup(props, { emit }) {
    const folderId = ref('');
    const folderPath = ref('');
    const siteId = ref('');

    const isValid = computed(() => {
      return props.siteName.trim() !== '' && 
             props.clientId.trim() !== '' && 
             props.clientSecret.trim() !== '' && 
             props.tenantId.trim() !== '';
    });

    const config = computed(() => ({
      site_name: props.siteName,
      client_id: props.clientId,
      client_secret: props.clientSecret,
      tenant_id: props.tenantId,
      site_id: siteId.value || undefined,
      folder_path: folderPath.value || undefined,
      folder_id: folderId.value || undefined
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleSiteNameChange = (value: string) => {
      emit('update:siteName', value);
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

    // Browse the site's document library with the credentials above (POST /api/browse)
    const browseOpen = ref(false);
    let browsedId = '';
    const provider = remoteProvider('sharepoint', 'SharePoint document library', () => config.value);

    const handleBrowsed = (items: BrowseItem[]) => {
      const folder = items[0];
      if (!folder) return;
      folderPath.value = folder.path || '';
      folderId.value = folder.id;
      browsedId = folder.id;
    };

    const handleFolderPathChange = (value: string) => {
      folderPath.value = value;
      // a typed path replaces a browsed folder: its id would win over the path (SharePointReader)
      if (browsedId && folderId.value === browsedId) {
        folderId.value = '';
        browsedId = '';
      }
    };

    return {
      folderId,
      folderPath,
      siteId,
      isValid,
      browseOpen,
      provider,
      handleBrowsed,
      handleFolderPathChange,
      handleSiteNameChange,
      handleClientIdChange,
      handleClientSecretChange,
      handleTenantIdChange,
    };
  },
});
</script>
