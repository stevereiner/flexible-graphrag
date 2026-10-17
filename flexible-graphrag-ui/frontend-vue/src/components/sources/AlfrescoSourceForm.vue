<template>
  <BaseSourceForm
    title="Alfresco Repository"
    description="Connect to an Alfresco content management system"
  >
    <v-text-field
      :model-value="url"
      @update:model-value="(v: string) => url = v"
      label="Alfresco Base URL *"
      variant="outlined"
      class="mb-4"
      :placeholder="`e.g., ${defaultUrl}`"
      required
    />

    <div class="d-flex align-center flex-wrap ga-3 mb-4">
      <template v-if="signedInHere">
        <span class="text-body-2">
          Signed in to Alfresco as <strong>{{ session?.user_id }}</strong>{{ usingSignIn ? ' (used for this ingest)' : '' }}
        </span>
        <v-btn size="small" variant="text" @click="signOut()">Sign out</v-btn>
        <v-checkbox
          v-model="useOther" density="compact" hide-details
          label="Use other credentials (e.g. for Auto Sync)"
        />
      </template>
      <template v-else>
        <v-btn size="small" variant="outlined" @click="signInHere">Sign in to Alfresco</v-btn>
        <span class="text-body-2 text-medium-emphasis">or enter credentials below</span>
      </template>
    </div>

    <v-select
      v-if="!usingSignIn"
      :model-value="authMethod"
      @update:model-value="(v: string) => authMethod = v"
      :items="authMethods"
      label="Authentication"
      variant="outlined"
      class="mb-4"
      density="compact"
    />

    <v-row v-if="!usingSignIn && (authMethod === 'basic' || authMethod === 'ticket')" class="mb-4">
      <v-col cols="6">
        <v-text-field
          :model-value="username"
          @update:model-value="(v: string) => username = v"
          label="Username *"
          variant="outlined"
          autocomplete="off"
          required
        />
      </v-col>
      <v-col cols="6">
        <v-text-field
          :model-value="password"
          @update:model-value="(v: string) => password = v"
          label="Password *"
          type="password"
          variant="outlined"
          autocomplete="new-password"
          required
        />
      </v-col>
    </v-row>

    <template v-if="!usingSignIn && authMethod === 'oauth2'">
      <v-row class="mb-4">
        <v-col cols="6">
          <v-text-field
            :model-value="clientId"
            @update:model-value="(v: string) => clientId = v"
            label="Client ID *"
            autocomplete="off"
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
      <v-text-field
        :model-value="tokenEndpoint"
        @update:model-value="(v: string) => tokenEndpoint = v"
        label="Token Endpoint (optional)"
        variant="outlined"
        class="mb-4"
        placeholder="e.g., https://<keycloak>/realms/alfresco/protocol/openid-connect/token"
      />
      <v-text-field
        :model-value="scope"
        @update:model-value="(v: string) => scope = v"
        label="Scope (optional)"
        variant="outlined"
        class="mb-4"
      />
      <v-row class="mb-4">
        <v-col cols="6">
          <v-text-field
            :model-value="accessToken"
            @update:model-value="(v: string) => accessToken = v"
            label="Access Token (optional)"
            type="password"
            autocomplete="new-password"
            variant="outlined"
            hint="Provide a pre-obtained token instead of client_credentials"
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
    </template>

    <v-text-field
      :model-value="path"
      @update:model-value="(v: string) => path = v"
      label="Path *"
      variant="outlined"
      class="mb-4"
      placeholder="e.g., /Shared/GraphRAG"
      required
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch, onMounted, onUnmounted } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';
import { AlfrescoSession, getAlfrescoSession, onAuthChange, openSignIn, signOut, validateSession } from '../../auth/sourceAuth';

// Same Alfresco server? (an /alfresco suffix and trailing slashes don't matter)
const sameServer = (a: string, b: string) =>
  a.trim().replace(/\/+$/, '').replace(/\/alfresco$/i, '').toLowerCase() ===
  b.trim().replace(/\/+$/, '').replace(/\/alfresco$/i, '').toLowerCase();

export default defineComponent({
  name: 'AlfrescoSourceForm',
  components: {
    BaseSourceForm
  },
  props: {
    // Single-object persistence (see NuxeoSourceForm): seeds on mount, emits update:value on edit.
    value: { type: Object, default: null },
  },
  emits: ['configuration-change', 'validation-change', 'update:value'],
  setup(props, { emit }) {
    const v: any = props.value || {};
    const defaultUrl = import.meta.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080';
    // VITE_ALFRESCO_PATH, not VITE_PROCESS_FOLDER_PATH: the latter is the LOCAL
    // filesystem folder for Process Folder, so reusing it put a Windows path in
    // an Alfresco repository field and this fallback never applied.
    const defaultPath = import.meta.env.VITE_ALFRESCO_PATH || '/Shared/GraphRAG';

    const url = ref(v.url ?? defaultUrl);
    const authMethod = ref(v.auth_method ?? 'basic');
    const path = ref(v.path ?? defaultPath);

    // No pre-filled credentials (they were admin/admin): sign in, or type a username/password
    const username = ref(v.username ?? '');
    const password = ref(v.password ?? '');

    // The Alfresco sign-in (header / dialog, planning/SOURCE-AUTH-LOGIN.md). When signed in to this
    // server, the ingest uses that session's ticket -- nobody types a ticket. "Use other
    // credentials" falls back to the fields (e.g. a service account for Auto Sync, which needs
    // durable credentials, never a ticket).
    const session = ref<AlfrescoSession | null>(getAlfrescoSession());
    const useOther = ref(false);
    let stopAuth: (() => void) | null = null;
    onMounted(() => {
      stopAuth = onAuthChange(() => { session.value = getAlfrescoSession(); });
      validateSession(true);  // a kept ticket may be dead by now
    });
    onUnmounted(() => stopAuth?.());
    const signedInHere = computed(() => !!session.value && sameServer(session.value.url, url.value));
    const usingSignIn = computed(() => signedInHere.value && !useOther.value);
    const signInHere = () => openSignIn({ source: 'alfresco', url: url.value, methods: ['basic'], documents: null }, 'ingest');

    const clientId = ref(v.oauth2?.client_id ?? '');
    const clientSecret = ref(v.oauth2?.client_secret ?? '');
    const tokenEndpoint = ref(v.oauth2?.token_endpoint ?? '');
    const scope = ref(v.oauth2?.scope ?? '');
    const accessToken = ref(v.oauth2?.access_token ?? '');
    const refreshToken = ref(v.oauth2?.refresh_token ?? '');

    const authMethods = [
      { title: 'Basic (username / password)', value: 'basic' },
      { title: 'Ticket (login ticket)', value: 'ticket' },
      { title: 'OAuth2 (Bearer, via Identity Service)', value: 'oauth2' },
    ];

    const isValid = computed(() => {
      if (url.value.trim() === '' || path.value.trim() === '') return false;
      if (usingSignIn.value) return true;
      if (authMethod.value === 'oauth2') {
        return clientId.value.trim() !== '' && (accessToken.value.trim() !== '' || clientSecret.value.trim() !== '');
      }
      return username.value.trim() !== '' && password.value.trim() !== '';
    });

    const config = computed(() => {
      if (usingSignIn.value && session.value) {
        return { url: url.value, path: path.value, auth_method: 'ticket', ticket: session.value.ticket };
      }
      const base: any = { url: url.value, auth_method: authMethod.value, path: path.value };
      if (authMethod.value === 'oauth2') {
        base.oauth2 = {
          client_id: clientId.value,
          client_secret: clientSecret.value || undefined,
          token_endpoint: tokenEndpoint.value || undefined,
          scope: scope.value || undefined,
          access_token: accessToken.value || undefined,
          refresh_token: refreshToken.value || undefined,
        };
      } else {
        base.username = username.value;
        base.password = password.value;
      }
      return base;
    });

    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
      emit('update:value', newConfig);  // persist live config to App
    }, { immediate: true, deep: true });

    return {
      defaultUrl,
      session,
      useOther,
      signedInHere,
      usingSignIn,
      signInHere,
      signOut,
      url,
      authMethod,
      authMethods,
      path,
      username,
      password,
      clientId,
      clientSecret,
      tokenEndpoint,
      scope,
      accessToken,
      refreshToken,
    };
  },
});
</script>
