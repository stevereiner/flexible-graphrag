<template>
  <!-- Alfresco sign-in for search / AI chat (planning/SOURCE-AUTH-LOGIN.md): the header control,
       and the dialog sourceAuth.openSignIn() opens before a question when the stores hold
       Alfresco documents. -->
  <v-chip
    v-if="session"
    class="mr-3"
    closable
    variant="tonal"
    :title="`Signed in to Alfresco at ${session.url}`"
    @click:close="signOut()"
  >
    Alfresco: {{ session.user_id }}
  </v-chip>
  <v-btn v-else-if="provider" variant="text" class="mr-2" @click="openFromHeader">
    Sign in to Alfresco
  </v-btn>

  <v-dialog v-model="open" max-width="420" @update:model-value="(v: boolean) => { if (!v) finish(false) }">
    <v-card>
      <v-card-title>Sign in to Alfresco</v-card-title>
      <v-card-text>
        <p v-if="reason === 'ingest'" class="mb-3">
          Sign in to add documents from Alfresco. The same sign-in is used for search and AI chat.
        </p>
        <p v-else class="mb-3">
          {{ docs ? `${docs} document(s) from Alfresco are in the stores. ` : 'The stores may hold Alfresco documents. ' }}
          Sign in to search and ask about the ones you may read.
        </p>
        <v-select
          v-if="reason === 'ask' && providers.length > 1"
          :model-value="shownProvider?.url"
          @update:model-value="(u: string) => { dialogProvider = providers.find((p) => p.url === u) || null }"
          :items="providers.map((p) => ({ title: p.url + (p.documents != null ? ` (${p.documents} document${p.documents === 1 ? '' : 's'})` : ''), value: p.url }))"
          label="Alfresco server" variant="outlined" density="compact" class="mb-3"
          hint="One Alfresco sign-in at a time: documents from the other server(s) are left out"
          persistent-hint
        />
        <div v-else-if="shownProvider?.url" class="text-caption mb-3">{{ shownProvider.url }}</div>
        <v-alert v-if="error" type="error" density="compact" class="mb-3">{{ error }}</v-alert>
        <v-text-field
          v-model="username" label="Username" variant="outlined" density="compact"
          autocomplete="off" autofocus class="mb-2"
        />
        <v-text-field
          v-model="password" label="Password" type="password" variant="outlined" density="compact"
          autocomplete="new-password"
          @keydown.enter="username.trim() && password && handleSignIn()"
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn :disabled="busy" @click="handleContinueWithout">{{ reason === 'ingest' ? 'Cancel' : 'Continue without' }}</v-btn>
        <v-btn color="primary" variant="flat" :disabled="busy || !username.trim() || !password" @click="handleSignIn">
          Sign in
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted, onUnmounted, watch } from 'vue';
import axios from 'axios';
import {
  AuthProvider, AlfrescoSession, SignInReason, continueWithout, getAlfrescoSession, getRequirements,
  onAuthChange, registerSignInDialog, signIn, signOut,
} from './sourceAuth';

export default defineComponent({
  name: 'SourceSignIn',
  setup() {
    const session = ref<AlfrescoSession | null>(getAlfrescoSession());
    const provider = ref<AuthProvider | null>(null);  // header: is a sign-in needed at all?
    // every Alfresco server with documents in the stores -- the dialog lets the user pick one
    const providers = ref<AuthProvider[]>([]);
    const open = ref(false);
    const dialogProvider = ref<AuthProvider | null>(null);
    const reason = ref<SignInReason>('ask');
    const username = ref('');
    const password = ref('');
    const error = ref('');
    const busy = ref(false);
    let resolver: ((signedIn: boolean) => void) | null = null;
    const cleanups: Array<() => void> = [];

    const refreshProvider = async () => {
      const req = await getRequirements();
      providers.value = req.providers.filter((p) => p.source === 'alfresco');
      provider.value = providers.value[0] || null;
    };

    const finish = (signedIn: boolean) => {
      open.value = false;
      password.value = '';
      error.value = '';
      const r = resolver;
      resolver = null;
      r?.(signedIn);
    };

    onMounted(() => {
      refreshProvider();
      cleanups.push(onAuthChange(() => { session.value = getAlfrescoSession(); }));
      cleanups.push(registerSignInDialog((p, why) => {
        resolver?.(false);  // a dialog already open is superseded
        dialogProvider.value = p;
        reason.value = why;
        open.value = true;
        if (why === 'ask') {  // refresh the server list for the picker
          getRequirements(true).then((req) => { providers.value = req.providers.filter((x) => x.source === 'alfresco'); });
        }
        return new Promise<boolean>((resolve) => { resolver = resolve; });
      }));
    });
    onUnmounted(() => cleanups.forEach((c) => c()));
    watch(session, refreshProvider);

    const openFromHeader = () => {
      dialogProvider.value = provider.value;
      reason.value = 'ask';
      open.value = true;
    };

    const handleSignIn = async () => {
      busy.value = true;
      error.value = '';
      try {
        await signIn(username.value.trim(), password.value, dialogProvider.value?.url || provider.value?.url);
        finish(true);
      } catch (err) {
        error.value = axios.isAxiosError(err) ? err.response?.data?.detail || 'Sign-in failed' : 'Sign-in failed';
      } finally {
        busy.value = false;
      }
    };

    const handleContinueWithout = () => {
      if (reason.value === 'ask') continueWithout();  // only questions remember "without"
      finish(false);
    };

    const shownProvider = computed(() => dialogProvider.value || provider.value);
    const docs = computed(() => shownProvider.value?.documents);

    return {
      session, provider, providers, dialogProvider, open, reason, username, password, error, busy, shownProvider, docs,
      openFromHeader, handleSignIn, handleContinueWithout, finish, signOut,
    };
  },
});
</script>
