<template>
  <BaseSourceForm
    title="Box Storage"
    description="Connect to Box with developer token or persistent app credentials"
  >
    <v-select
      v-model="authMode"
      :items="authModes"
      label="Authentication Type"
      variant="outlined"
      class="mb-2"
    />

    <template v-if="authMode === 'developer_token'">
      <v-text-field
        :model-value="developerToken"
        @update:model-value="handleDeveloperTokenChange"
        label="Developer Token *"
        variant="outlined"
        class="mb-2"
        type="password"
          autocomplete="new-password"
        hint="Temporary token for testing (expires after 1 hour)"
        persistent-hint
      />
    </template>

    <template v-if="authMode !== 'developer_token'">
      <div class="d-flex ga-2 mb-2">
        <v-text-field
          :model-value="clientId"
          @update:model-value="handleClientIdChange"
          label="App Client ID *"
          variant="outlined"
        />
        <v-text-field
          :model-value="clientSecret"
          @update:model-value="handleClientSecretChange"
          label="App Client Secret *"
          variant="outlined"
          type="password"
          autocomplete="new-password"
        />
      </div>

      <v-text-field
        v-if="authMode === 'ccg_user' || authMode === 'ccg_both'"
        :model-value="userId"
        @update:model-value="handleUserIdChange"
        label="Box User ID *"
        variant="outlined"
        class="mb-2"
        placeholder="12345678"
        hint="Access files for a specific Box user"
        persistent-hint
      />

      <v-text-field
        v-if="authMode === 'ccg_enterprise' || authMode === 'ccg_both'"
        :model-value="enterpriseId"
        @update:model-value="handleEnterpriseIdChange"
        label="Box Enterprise ID *"
        variant="outlined"
        class="mb-2"
        placeholder="987654321"
        hint="Access files across your entire Box organization"
        persistent-hint
      />
    </template>

    <div class="d-flex align-start ga-2">
      <v-text-field
        :model-value="folderId"
        @update:model-value="(v: string) => { folderId = v; folderLabel = ''; if (v) files = []; }"
        label="Folder ID (Optional)"
        variant="outlined"
        class="mb-2"
        placeholder="e.g., 123456789"
        :hint="folderLabel ? `Folder: ${folderLabel}` : 'Leave empty for the root folder (All Files, ID 0)'"
        persistent-hint
        :disabled="files.length > 0"
      />
      <v-btn
        variant="outlined"
        prepend-icon="mdi-folder-open"
        height="56"
        :disabled="!isValid"
        :title="isValid ? 'Pick a folder or files in Box' : 'Fill in the credentials first'"
        @click="browseOpen = true"
      >
        Browse…
      </v-btn>
      <DeepCheckbox :checked="recursive" @change="(v: boolean) => ownDeep = v" />
    </div>
    <PickedChips
      :items="files"
      @remove="(id: string) => { files = files.filter((f) => f.id !== id); }"
      @clear="files = []"
    />
    <SourceBrowser
      :open="browseOpen"
      :provider="provider"
      title="Pick a folder or files: Box"
      :mixed="false"
      @close="browseOpen = false"
      @select="handleBrowsed"
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';
import DeepCheckbox from './DeepCheckbox.vue';
import { loadUiDefaults } from '../../uiDefaults';
import SourceBrowser from '../../browser/SourceBrowser.vue';
import PickedChips from '../../browser/PickedChips.vue';
import { remoteProvider } from '../../browser/remoteProvider';
import type { BrowseItem } from '../../browser/types';
import { ingestStarted } from '../../ingestSignal';

type BoxAuthMode = 'developer_token' | 'ccg_user' | 'ccg_enterprise' | 'ccg_both';

export default defineComponent({
  name: 'BoxSourceForm',
  components: {
    BaseSourceForm,
    DeepCheckbox,
    SourceBrowser,
    PickedChips
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
    },
    userId: {
      type: String,
      default: ''
    },
    enterpriseId: {
      type: String,
      default: ''
    }
  },
  emits: [
    'update:clientId', 'update:clientSecret', 'update:developerToken', 
    'update:userId', 'update:enterpriseId',
    'configuration-change', 'validation-change'
  ],
  setup(props, { emit }) {
    const folderId = ref('');
    // the browsed folder's name path, shown under its id (cleared when the id is typed)
    const folderLabel = ref('');
    // files picked in the browser (box_file_ids: the ingest then reads these instead of a folder)
    const files = ref<BrowseItem[]>([]);
    const authMode = ref<BoxAuthMode>('ccg_user');
    // Deep: include subfolders (recursive). Unset: the backend's DEFAULT_RECURSIVE, else on (Box's own default)
    const ownDeep = ref<boolean | undefined>(undefined);
    const uiDefaults = loadUiDefaults();
    const recursive = computed(() => ownDeep.value ?? uiDefaults.recursive ?? true);
    
    const authModes = [
      { title: 'App Access (User)', value: 'ccg_user' },
      { title: 'App Access (Enterprise)', value: 'ccg_enterprise' },
      { title: 'App Access (User + Enterprise)', value: 'ccg_both' },
      { title: 'Developer Token (expires after 1 hour)', value: 'developer_token' }
    ];

    const isValid = computed(() => {
      switch (authMode.value) {
        case 'developer_token':
          return props.developerToken.trim() !== '';
        case 'ccg_user':
          return props.clientId.trim() !== '' && props.clientSecret.trim() !== '' && props.userId.trim() !== '';
        case 'ccg_enterprise':
          return props.clientId.trim() !== '' && props.clientSecret.trim() !== '' && props.enterpriseId.trim() !== '';
        case 'ccg_both':
          return props.clientId.trim() !== '' && props.clientSecret.trim() !== '' && 
                 props.userId.trim() !== '' && props.enterpriseId.trim() !== '';
        default:
          return false;
      }
    });

    const config = computed(() => ({
      client_id: authMode.value !== 'developer_token' ? props.clientId : undefined,
      client_secret: authMode.value !== 'developer_token' ? props.clientSecret : undefined,
      developer_token: authMode.value === 'developer_token' ? props.developerToken : undefined,
      user_id: (authMode.value === 'ccg_user' || authMode.value === 'ccg_both') ? props.userId : undefined,
      enterprise_id: (authMode.value === 'ccg_enterprise' || authMode.value === 'ccg_both') ? props.enterpriseId : undefined,
      folder_id: folderId.value || undefined,
      box_file_ids: files.value.length ? files.value.map((f) => f.id) : undefined,
      recursive: recursive.value,
    }));

    // Browse Box with the credentials above (POST /api/browse)
    const browseOpen = ref(false);
    const provider = remoteProvider('box', 'Box', () => config.value);

    // an ingest started: the picked files empty (the run's rows stay in Processing)
    watch(ingestStarted, () => { files.value = []; });

    // one folder (folder_id), or files (box_file_ids): the browser keeps the two apart
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

    const handleClientIdChange = (value: string) => {
      emit('update:clientId', value);
    };

    const handleClientSecretChange = (value: string) => {
      emit('update:clientSecret', value);
    };

    const handleDeveloperTokenChange = (value: string) => {
      emit('update:developerToken', value);
    };

    const handleUserIdChange = (value: string) => {
      emit('update:userId', value);
    };

    const handleEnterpriseIdChange = (value: string) => {
      emit('update:enterpriseId', value);
    };

    return {
      ownDeep,
      recursive,
      folderId,
      folderLabel,
      files,
      isValid,
      browseOpen,
      provider,
      handleBrowsed,
      authMode,
      authModes,
      handleClientIdChange,
      handleClientSecretChange,
      handleDeveloperTokenChange,
      handleUserIdChange,
      handleEnterpriseIdChange,
    };
  },
});
</script>
