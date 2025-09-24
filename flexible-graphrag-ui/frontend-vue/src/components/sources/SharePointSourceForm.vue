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
    
    <v-text-field
      v-model="folderPath"
      label="Folder Path (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="/Shared Documents/Reports"
      hint="Optional: specific folder path within site"
      persistent-hint
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'SharePointSourceForm',
  components: {
    BaseSourceForm
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

    return {
      folderId,
      folderPath,
      siteId,
      handleSiteNameChange,
      handleClientIdChange,
      handleClientSecretChange,
      handleTenantIdChange,
    };
  },
});
</script>
