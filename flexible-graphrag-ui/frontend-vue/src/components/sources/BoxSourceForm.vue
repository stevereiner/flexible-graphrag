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
        label="Developer Token"
        variant="outlined"
        class="mb-2"
        type="password"
        hint="Temporary token for testing (expires after 1 hour)"
        persistent-hint
      />
    </template>

    <template v-if="authMode !== 'developer_token'">
      <div class="d-flex ga-2 mb-2">
        <v-text-field
          :model-value="clientId"
          @update:model-value="handleClientIdChange"
          label="App Client ID"
          variant="outlined"
        />
        <v-text-field
          :model-value="clientSecret"
          @update:model-value="handleClientSecretChange"
          label="App Client Secret"
          variant="outlined"
          type="password"
        />
      </div>

      <v-text-field
        v-if="authMode === 'ccg_user' || authMode === 'ccg_both'"
        :model-value="userId"
        @update:model-value="handleUserIdChange"
        label="Box User ID"
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
        label="Box Enterprise ID"
        variant="outlined"
        class="mb-2"
        placeholder="987654321"
        hint="Access files across your entire Box organization"
        persistent-hint
      />
    </template>

    <v-text-field
      v-model="folderId"
      label="Folder ID (Optional)"
      variant="outlined"
      class="mb-2"
      placeholder="0"
      hint="Leave empty for root folder"
      persistent-hint
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

type BoxAuthMode = 'developer_token' | 'ccg_user' | 'ccg_enterprise' | 'ccg_both';

export default defineComponent({
  name: 'BoxSourceForm',
  components: {
    BaseSourceForm
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
    const authMode = ref<BoxAuthMode>('developer_token');
    
    const authModes = [
      { title: 'Developer Token', value: 'developer_token' },
      { title: 'App Access (User)', value: 'ccg_user' },
      { title: 'App Access (Enterprise)', value: 'ccg_enterprise' },
      { title: 'App Access (User + Enterprise)', value: 'ccg_both' }
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
      folder_id: folderId.value || undefined
    }));

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
      folderId,
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
