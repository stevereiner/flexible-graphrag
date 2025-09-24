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
    
    <v-text-field
      v-model="folderPath"
      label="Folder Path (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="/Documents/Reports"
      hint="Optional: specific folder path in OneDrive"
      persistent-hint
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
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'OneDriveSourceForm',
  components: {
    BaseSourceForm
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
      folder_id: folderId.value || undefined
    }));

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
      handleUserPrincipalNameChange,
      handleClientIdChange,
      handleClientSecretChange,
      handleTenantIdChange,
    };
  },
});
</script>
