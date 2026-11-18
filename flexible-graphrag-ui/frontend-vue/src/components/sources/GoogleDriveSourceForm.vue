<template>
  <BaseSourceForm
    title="Google Drive"
    description="Connect to Google Drive using service account credentials"
  >
    <div class="d-flex ga-2 mb-4 align-start">
      <v-text-field
        :model-value="folderId"
        @update:model-value="(v: string) => { folderId = v; folderLabel = ''; if (v) files = []; }"
        :label="files.length ? 'Folder ID' : 'Folder ID *'"
        variant="outlined"
        placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        :hint="folderLabel ? `Folder: ${folderLabel}` : 'A folder shared with the service account, or pick files with Browse…'"
        persistent-hint
        autocomplete="off"
        :disabled="files.length > 0"
      />
      <v-btn
        variant="outlined"
        prepend-icon="mdi-folder-open"
        height="56"
        :disabled="!canBrowse"
        :title="canBrowse ? 'Pick a folder or files in Google Drive' : 'Paste the service account credentials first'"
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
    <SourceBrowser
      :open="browseOpen"
      :provider="provider"
      title="Pick a folder or files: Google Drive"
      :mixed="false"
      @close="browseOpen = false"
      @select="handleBrowsed"
    />
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
import { defineComponent, computed, watch, ref } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';
import SourceBrowser from '../../browser/SourceBrowser.vue';
import PickedChips from '../../browser/PickedChips.vue';
import { remoteProvider } from '../../browser/remoteProvider';
import type { BrowseItem } from '../../browser/types';
import { ingestStarted } from '../../ingestSignal';

export default defineComponent({
  name: 'GoogleDriveSourceForm',
  components: {
    BaseSourceForm,
    SourceBrowser,
    PickedChips
  },
  props: {
    credentials: {
      type: String,
      default: ''
    }
  },
  emits: ['update:credentials', 'configuration-change', 'validation-change'],
  setup(props, { emit }) {
    const folderId = ref('');
    // the browsed folder's name path, shown under its id (cleared when the id is typed)
    const folderLabel = ref('');
    // files picked in the browser (file_ids: the ingest reads these when there is no folder id)
    const files = ref<BrowseItem[]>([]);

    // Browse needs the credentials; the ingest also needs a folder or files (the reader reads
    // nothing else: a service account has no "whole drive")
    const canBrowse = computed(() => props.credentials.trim() !== '');
    const isValid = computed(() =>
      canBrowse.value && (folderId.value.trim() !== '' || files.value.length > 0));

    const config = computed(() => ({
      credentials: props.credentials,
      folder_id: folderId.value.trim() || undefined,
      file_ids: files.value.length ? files.value.map((f) => f.id) : undefined
    }));

    // Browse what the service account can see (POST /api/browse)
    const browseOpen = ref(false);
    const provider = remoteProvider('google_drive', 'Google Drive', () => config.value);

    // an ingest started: the picked files empty (the run's rows stay in Processing)
    watch(ingestStarted, () => { files.value = []; });

    // one folder (folder_id), or files (file_ids): the browser keeps the two apart (a folder id
    // would win over file ids in the ingest)
    const handleBrowsed = (items: BrowseItem[]) => {
      if (!items.length) return;
      if (items[0].isDirectory) {
        folderId.value = items[0].id;
        folderLabel.value = items[0].path || items[0].name;
        files.value = [];
      } else {
        files.value = items;
        folderId.value = '';
        folderLabel.value = '';
      }
    };

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleCredentialsChange = (value: string) => {
      emit('update:credentials', value);
    };

    return {
      folderId,
      folderLabel,
      files,
      isValid,
      canBrowse,
      browseOpen,
      provider,
      handleBrowsed,
      handleCredentialsChange,
    };
  },
});
</script>
