<template>
  <BaseSourceForm
    title="Azure Blob Storage"
    description="Connect to Azure Blob Storage using Account Key Authentication (Method 1)"
  >
    <v-text-field
      v-model="accountUrl"
      label="Account URL *"
      variant="outlined"
      class="mb-2"
      placeholder="https://mystorageaccount.blob.core.windows.net"
      hint="Azure Storage account URL (required)"
      persistent-hint
      required
    />
    
    <v-text-field
      :model-value="containerName"
      @update:model-value="handleContainerNameChange"
      label="Container Name *"
      variant="outlined"
      class="mb-2"
      placeholder="my-container"
      required
    />
    
    <v-text-field
      :model-value="blobName"
      @update:model-value="handleBlobNameChange"
      label="Blob (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="specific-file.pdf"
      hint="Optional: one blob's full name (e.g. docs/a.pdf); used instead of the prefix"
      persistent-hint
    />

    <div class="d-flex ga-2 mb-2 align-start">
      <v-text-field
        v-model="prefix"
        label="Prefix (Optional)"
        variant="outlined"
        placeholder="documents/reports/"
        hint="Optional: folder path prefix within container"
        persistent-hint
      />
      <v-btn
        variant="outlined"
        prepend-icon="mdi-folder-open"
        height="56"
        :disabled="!isValid"
        :title="isValid ? 'Pick a folder or a blob in the container' : 'Fill in the account URL, container, account name and key first'"
        @click="browseOpen = true"
      >
        Browse…
      </v-btn>
    </div>
    <SourceBrowser
      :open="browseOpen"
      :provider="provider"
      :title="`Pick a folder or a file: ${containerName || 'Azure Blob'}`"
      :multiple="false"
      @close="browseOpen = false"
      @select="handleBrowsed"
    />

    <v-text-field
      :model-value="accountName"
      @update:model-value="handleAccountNameChange"
      label="Account Name *"
      variant="outlined"
      class="mb-2"
      placeholder="mystorageaccount"
      hint="Azure Storage account name (required)"
      persistent-hint
      required
    />
    
    <v-text-field
      :model-value="accountKey"
      @update:model-value="handleAccountKeyChange"
      label="Account Key *"
      variant="outlined"
      class="mb-2"
      type="password"
          autocomplete="new-password"
      placeholder="account-key-here"
      hint="Azure Storage account key (required)"
      persistent-hint
      required
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
  name: 'AzureBlobSourceForm',
  components: {
    BaseSourceForm,
    SourceBrowser
  },
  props: {
    connectionString: {
      type: String,
      default: ''
    },
    containerName: {
      type: String,
      default: ''
    },
    blobName: {
      type: String,
      default: ''
    },
    accountName: {
      type: String,
      default: ''
    },
    accountKey: {
      type: String,
      default: ''
    }
  },
  emits: [
    'update:connectionString', 'update:containerName', 'update:blobName', 
    'update:accountName', 'update:accountKey', 'configuration-change', 'validation-change'
  ],
  setup(props, { emit }) {
    const prefix = ref('');
    const accountUrl = ref('');

    const isValid = computed(() => {
      // Method 1 requires: account_url, container_name, account_name, account_key
      return accountUrl.value.trim() !== '' && 
             props.containerName.trim() !== '' && 
             props.accountName.trim() !== '' && 
             props.accountKey.trim() !== '';
    });

    const config = computed(() => ({
      // Method 1 (Account Key Authentication) fields
      container_name: props.containerName,
      account_url: accountUrl.value,
      blob: props.blobName || undefined,
      prefix: prefix.value || undefined,
      account_name: props.accountName,
      account_key: props.accountKey
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleContainerNameChange = (value: string) => {
      emit('update:containerName', value);
    };

    const handleBlobNameChange = (value: string) => {
      emit('update:blobName', value);
    };

    const handleAccountNameChange = (value: string) => {
      emit('update:accountName', value);
    };

    const handleAccountKeyChange = (value: string) => {
      emit('update:accountKey', value);
    };

    // Browse the container with the account key above (POST /api/browse)
    const browseOpen = ref(false);
    const provider = remoteProvider('azure_blob', 'Azure Blob container', () => config.value);

    // one folder (prefix "docs/reports/") or one blob (its full name): the ingest takes blob over prefix
    const handleBrowsed = (items: BrowseItem[]) => {
      if (!items.length) return;
      const picked = items[0].path || items[0].id;
      if (items[0].isDirectory) {
        prefix.value = picked;
        emit('update:blobName', '');
      } else {
        emit('update:blobName', picked);
        prefix.value = '';
      }
    };

    return {
      isValid,
      browseOpen,
      provider,
      handleBrowsed,
      prefix,
      accountUrl,
      handleContainerNameChange,
      handleBlobNameChange,
      handleAccountNameChange,
      handleAccountKeyChange,
    };
  },
});
</script>
