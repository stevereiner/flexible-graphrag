<template>
  <!-- Repository sign-in for search / AI chat (planning/SOURCE-AUTH-LOGIN.md): Alfresco, Nuxeo and
       CMIS. One header chip per signed-in server, a Sign in button while a server whose documents
       are in the stores has no sign-in, and the dialog sourceAuth.openSignIn() opens before a
       question or from a data-source form. -->
  <!-- One pill for every repository sign-in; its menu lists each server, signed in or offline -->
  <v-menu v-if="rows.length" location="bottom end">
    <template #activator="{ props: menuProps }">
      <v-chip
        v-bind="menuProps"
        class="mr-3"
        prepend-icon="mdi-account-circle"
        append-icon="mdi-menu-down"
        :variant="signedInCount ? 'tonal' : 'outlined'"
        :style="(missing.length ? 'border-style: dashed; ' : '') + 'max-width: 240px'"
        :title="pillTitle"
      >{{ pillLabel }}</v-chip>
    </template>
    <v-list density="compact" min-width="320">
      <v-list-subheader>REPOSITORY SIGN-INS</v-list-subheader>
      <v-list-item v-for="r in rows" :key="providerKey(r.provider)">
        <template #prepend>
          <span
            class="mr-3"
            :style="{ display: 'inline-block', width: '10px', height: '10px', borderRadius: '50%',
                      background: r.session ? (SOURCE_COLORS[r.provider.source] || '#66bb6a') : '#9e9e9e' }"
          />
        </template>
        <v-list-item-title>
          <strong>{{ providerTitle(r.provider) }}</strong>
          {{ r.session ? r.session.user_id : '' }}<em v-if="!r.session" class="text-medium-emphasis">offline</em>
        </v-list-item-title>
        <v-list-item-subtitle style="max-width: 320px" :title="providerTooltip(r.provider)">
          {{ providerCaption(r.provider) }}
        </v-list-item-subtitle>
        <template #append>
          <v-btn v-if="r.session" size="small" variant="text" @click.stop="signOut(r.session)">Sign out</v-btn>
          <v-btn v-else size="small" variant="outlined" @click="show(r.provider, 'ask')">Sign in</v-btn>
        </template>
      </v-list-item>
    </v-list>
  </v-menu>

  <v-dialog v-model="open" max-width="460" @update:model-value="(v: boolean) => { if (!v) finish(false) }">
    <v-card>
      <v-card-title>Sign in to {{ label }}</v-card-title>
      <v-card-text>
        <p v-if="reason === 'ingest'" class="mb-3">
          Sign in to add documents from {{ label }}. The same sign-in is used for search and AI chat.
        </p>
        <p v-else class="mb-3">
          {{ docs ? `${docs} document(s) from ${label} are in the stores. ` : `The stores may hold ${label} documents. ` }}
          Sign in to search and ask about the ones you may read.
        </p>
        <v-select
          v-if="picker"
          :model-value="shownProvider ? providerKey(shownProvider) : null"
          @update:model-value="(k: string) => { dialogProvider = missing.find((p) => providerKey(p) === k) || null }"
          :items="missing.map((p) => ({ title: `${labelOf(p.source)}: ${p.url}` + (p.documents != null ? ` (${p.documents} document${p.documents === 1 ? '' : 's'})` : ''), value: providerKey(p) }))"
          label="Server" variant="outlined" density="compact" class="mb-3"
          hint="Sign in to each server you want answers from; the others' documents are left out"
          persistent-hint
        />
        <div v-else-if="shownProvider?.url && !isKeySource(shownProvider.source)" class="text-caption mb-3" style="word-break: break-all">{{ shownProvider.url }}</div>
        <v-alert v-if="error" type="error" density="compact" class="mb-3">{{ error }}</v-alert>
        <p v-if="isPopup" class="text-body-2">
          Signs in at {{ label }} in a new window (allow pop-ups for this site).
          <template v-if="shownProvider?.source === 'microsoft'">One sign-in covers SharePoint and OneDrive.</template>
          <template v-if="shownProvider?.source === 'google'">One sign-in covers Google Drive and Cloud Storage.</template>
        </p>
        <template v-else>
          <p v-if="isKeySource(shownProvider?.source)" class="text-body-2 mb-3">
            Your AWS access key is used once to start a session (12 hours by default); only that session is kept, in this browser tab.
          </p>
          <v-text-field
            v-model="username" :label="credentialLabels(shownProvider?.source)[0]" variant="outlined" density="compact"
            autocomplete="off" autofocus class="mb-2"
          />
          <v-text-field
            v-model="password" :label="credentialLabels(shownProvider?.source)[1]" type="password" variant="outlined" density="compact"
            autocomplete="new-password"
            @keydown.enter="username.trim() && password && handleSignIn()"
          />
        </template>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn :disabled="busy" @click="handleContinueWithout">{{ reason === 'ingest' ? 'Cancel' : 'Continue without' }}</v-btn>
        <v-btn v-if="isPopup" color="primary" variant="flat" :disabled="busy" @click="handlePopup">
          {{ busy ? `Waiting for ${label}…` : `Sign in with ${label}` }}
        </v-btn>
        <v-btn v-else color="primary" variant="flat" :disabled="busy || !username.trim() || !password || !shownProvider" @click="handleSignIn">
          Sign in
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script lang="ts">
import { defineComponent, ref, computed, onMounted, onUnmounted } from 'vue';
import axios from 'axios';
import {
  AuthProvider, Requirements, SignInReason, SourceKind, SourceSession, continueWithout, getRequirements,
  getSessions, labelOf, missingProviders, onAuthChange, providerCaption, providerTitle, providerTooltip, registerSignInDialog,
  credentialLabels, isKeySource, isPopupSource, serverKey, signIn, signInPopup, signInRows, signOut,
} from './sourceAuth';
import { SOURCE_COLORS } from './sourceColors';

const providerKey = (p: AuthProvider) => `${p.source}|${serverKey(p.source, p.url)}`;

export default defineComponent({
  name: 'SourceSignIn',
  setup() {
    const sessions = ref<SourceSession[]>(getSessions());
    // servers with documents in the stores and no sign-in yet -- the dialog lets the user pick one
    const missing = ref<AuthProvider[]>([]);
    const requirements = ref<Requirements>({ required: false, providers: [] });
    const open = ref(false);
    const dialogProvider = ref<AuthProvider | null>(null);
    const reason = ref<SignInReason>('ask');
    const username = ref('');
    const password = ref('');
    const error = ref('');
    const busy = ref(false);
    let resolver: ((signedIn: boolean) => void) | null = null;
    const cleanups: Array<() => void> = [];

    const refreshMissing = async (force = false) => {
      const req = await getRequirements(force);
      requirements.value = req;
      missing.value = missingProviders(req);
    };

    const finish = (signedIn: boolean) => {
      open.value = false;
      password.value = '';
      error.value = '';
      const r = resolver;
      resolver = null;
      r?.(signedIn);
    };

    const show = (p: AuthProvider | null, why: SignInReason) => {
      dialogProvider.value = p;
      reason.value = why;
      error.value = '';
      open.value = true;
    };

    onMounted(() => {
      refreshMissing();
      cleanups.push(onAuthChange(() => { sessions.value = getSessions(); refreshMissing(); }));
      cleanups.push(registerSignInDialog((p, why) => {
        resolver?.(false);  // a dialog already open is superseded
        show(p, why);
        if (why === 'ask') refreshMissing(true);  // refresh the server list for the picker
        return new Promise<boolean>((resolve) => { resolver = resolve; });
      }));
    });
    onUnmounted(() => cleanups.forEach((c) => c()));

    const shownProvider = computed(() => dialogProvider.value || missing.value[0] || null);
    const label = computed(() => labelOf(shownProvider.value?.source || 'alfresco'));
    const docs = computed(() => shownProvider.value?.documents);
    const picker = computed(() => reason.value === 'ask' && missing.value.length > 1);
    // eslint-disable-next-line @typescript-eslint/no-unused-expressions
    const rows = computed(() => { sessions.value; return signInRows(requirements.value); });
    const signedInCount = computed(() => rows.value.filter((r) => r.session).length);
    // short: the name before the @ (full names and servers are in the tooltip and the menu)
    const pillLabel = computed(() => (rows.value.length === 1
      ? `${providerTitle(rows.value[0].provider)}: ${rows.value[0].session ? rows.value[0].session.user_id.split('@')[0] : 'offline'}`
      : `Sign-ins ${signedInCount.value}/${rows.value.length}`));
    const pillTitle = computed(() => rows.value
      .map((r) => `${providerTitle(r.provider)}: ${r.session ? r.session.user_id : 'offline'}`).join('\n'));

    const handleSignIn = async () => {
      const p = shownProvider.value;
      if (!p) return;
      busy.value = true;
      error.value = '';
      try {
        await signIn(p.source as SourceKind, username.value.trim(), password.value, p.url || undefined);
        finish(true);
      } catch (err) {
        error.value = axios.isAxiosError(err) ? err.response?.data?.detail || 'Sign-in failed' : 'Sign-in failed';
      } finally {
        busy.value = false;
      }
    };

    const isPopup = computed(() => isPopupSource(shownProvider.value?.source));

    // Microsoft 365 / Box: signInPopup opens the popup synchronously, so call it first in the click
    const handlePopup = async () => {
      const signingIn = signInPopup(shownProvider.value!.source as SourceKind);
      busy.value = true;
      error.value = '';
      try {
        await signingIn;
        finish(true);
      } catch (err) {
        error.value = axios.isAxiosError(err) ? err.response?.data?.detail || 'Sign-in failed' : (err as Error).message;
      } finally {
        busy.value = false;
      }
    };

    const handleContinueWithout = () => {
      if (reason.value === 'ask') continueWithout();  // only questions remember "without"
      finish(false);
    };

    return {
      sessions, missing, dialogProvider, open, reason, username, password, error, busy, shownProvider, label, docs, picker,
      show, handleSignIn, handleContinueWithout, finish, signOut, labelOf, providerKey,
      rows, signedInCount, pillLabel, pillTitle, SOURCE_COLORS, providerTitle, providerCaption, providerTooltip, isPopup, handlePopup, isKeySource, credentialLabels,
    };
  },
});
</script>
