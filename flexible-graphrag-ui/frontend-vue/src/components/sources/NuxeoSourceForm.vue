<template>
  <BaseSourceForm
    title="Nuxeo Repository"
    description="Connect to a Nuxeo content management system"
  >
    <v-text-field
      :model-value="url"
      @update:model-value="(v: string) => url = v"
      label="Nuxeo Base URL *"
      variant="outlined"
      class="mb-4"
      placeholder="e.g., http://localhost:8081/nuxeo"
      hint="Base repository URL (no /api/v1 suffix)"
      persistent-hint
      required
    />

    <v-select
      :model-value="authMethod"
      @update:model-value="(v: string) => authMethod = v"
      :items="authMethods"
      label="Authentication"
      variant="outlined"
      class="mb-4"
      density="compact"
    />

    <v-row v-if="authMethod === 'basic' || authMethod === 'token'" class="mb-4">
      <v-col cols="6">
        <v-text-field
          :model-value="username"
          @update:model-value="(v: string) => username = v"
          label="Username *"
          autocomplete="off"
          variant="outlined"
          required
        />
      </v-col>
      <v-col cols="6">
        <v-text-field
          :model-value="password"
          @update:model-value="(v: string) => password = v"
          label="Password *"
          type="password"
          autocomplete="new-password"
          variant="outlined"
          required
        />
      </v-col>
    </v-row>

    <template v-if="authMethod === 'oauth2'">
      <v-row class="mb-4">
        <v-col cols="6">
          <v-text-field
            :model-value="clientId"
            @update:model-value="(v: string) => clientId = v"
            label="Client ID *"
            variant="outlined"
            required
          />
        </v-col>
        <v-col cols="6">
          <v-text-field
            :model-value="clientSecret"
            @update:model-value="(v: string) => clientSecret = v"
            hint="Required unless an access token is given"
            persistent-hint
            :label="accessToken.trim() ? 'Client Secret' : 'Client Secret *'"
            type="password"
          autocomplete="new-password"
            variant="outlined"
          />
        </v-col>
      </v-row>
      <v-row class="mb-4">
        <v-col cols="6">
          <v-text-field
            :model-value="accessToken"
            @update:model-value="(v: string) => accessToken = v"
            label="Access Token (optional)"
            type="password"
          autocomplete="new-password"
            variant="outlined"
            hint="Obtain out-of-band (authorization code + PKCE)"
            persistent-hint
          />
        </v-col>
        <v-col cols="6">
          <v-text-field
            :model-value="refreshToken"
            @update:model-value="(v: string) => refreshToken = v"
            label="Refresh Token (optional)"
            type="password"
          autocomplete="new-password"
            variant="outlined"
          />
        </v-col>
      </v-row>
      <v-text-field
        :model-value="tokenEndpoint"
        @update:model-value="(v: string) => tokenEndpoint = v"
        label="Token Endpoint (optional)"
        variant="outlined"
        class="mb-4"
        placeholder="defaults to <url>/oauth2/token"
      />
    </template>

    <v-text-field
      :model-value="path"
      @update:model-value="(v: string) => path = v"
      label="Path *"
      variant="outlined"
      class="mb-4"
      placeholder="e.g., /default-domain/workspaces/GraphRAG"
      hint="Path to the folder or document to process"
      persistent-hint
      required
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'NuxeoSourceForm',
  components: {
    BaseSourceForm
  },
  props: {
    // Single-object persistence: seeds the form on mount, emits update:value on every edit,
    // so App holds one object and state survives Sources<->Processing tab switches.
    value: { type: Object, default: null },
  },
  emits: ['configuration-change', 'validation-change', 'update:value'],
  setup(props, { emit }) {
    const v: any = props.value || {};
    const url = ref(v.url ?? (import.meta.env.VITE_NUXEO_BASE_URL || 'http://localhost:8081/nuxeo'));
    const authMethod = ref(v.auth_method ?? 'basic');
    // VITE_NUXEO_PATH is a build-time var: the browser cannot read the
    // backend's .env, so NUXEO_PATH there does not reach this dialog.
    const path = ref(v.path ?? (import.meta.env.VITE_NUXEO_PATH || '/default-domain/workspaces/GraphRAG'));

    // no pre-filled credentials (were Administrator/Administrator)
    const username = ref(v.username ?? '');
    const password = ref(v.password ?? '');

    const clientId = ref(v.oauth2?.client_id ?? '');
    const clientSecret = ref(v.oauth2?.client_secret ?? '');
    const accessToken = ref(v.oauth2?.access_token ?? '');
    const refreshToken = ref(v.oauth2?.refresh_token ?? '');
    const tokenEndpoint = ref(v.oauth2?.token_endpoint ?? '');

    const authMethods = [
      { title: 'Basic (username / password)', value: 'basic' },
      { title: 'OAuth2 (Bearer)', value: 'oauth2' },
      { title: 'Token (X-Authentication-Token)', value: 'token' },
    ];

    const isValid = computed(() => {
      if (url.value.trim() === '') return false;
      // basic and token both use username/password (token mode fetches the auth token
      // from them on the backend, like Alfresco ticket).
      if (authMethod.value === 'basic' || authMethod.value === 'token') {
        return username.value.trim() !== '' && password.value.trim() !== '';
      }
      return clientId.value.trim() !== '' && (accessToken.value.trim() !== '' || clientSecret.value.trim() !== '');
    });

    const config = computed(() => {
      const base: any = { url: url.value, auth_method: authMethod.value, path: path.value };
      // token mode sends username/password; the backend fetches the auth token from them.
      if (authMethod.value === 'basic' || authMethod.value === 'token') {
        base.username = username.value;
        base.password = password.value;
      } else {
        base.oauth2 = {
          client_id: clientId.value,
          client_secret: clientSecret.value || undefined,
          access_token: accessToken.value || undefined,
          refresh_token: refreshToken.value || undefined,
          token_endpoint: tokenEndpoint.value || undefined,
        };
      }
      return base;
    });

    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
      emit('update:value', newConfig);  // persist live config to App
    }, { immediate: true, deep: true });

    return {
      url,
      authMethod,
      authMethods,
      path,
      username,
      password,
      clientId,
      clientSecret,
      accessToken,
      refreshToken,
      tokenEndpoint,
    };
  },
});
</script>
