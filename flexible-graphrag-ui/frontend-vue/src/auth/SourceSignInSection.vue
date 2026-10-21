<template>
  <!-- "Signed in to X as Y (used for this ingest)" with Sign out / Use other credentials, or a
       "Sign in to X" button: the same sign-in the header and search / chat use. -->
  <div class="d-flex align-center flex-wrap ga-3 mb-4">
    <template v-if="session">
      <span class="text-body-2">
        Signed in to {{ label }} as <strong>{{ session.user_id }}</strong>{{ usingSignIn ? ' (used for this ingest)' : '' }}
      </span>
      <v-btn size="small" variant="text" @click="signOut(session)">Sign out</v-btn>
      <v-checkbox
        :model-value="useOther" @update:model-value="(v: boolean | null) => $emit('update:useOther', !!v)"
        density="compact" hide-details
        :label="source === 'alfresco' ? 'Use other credentials (e.g. for Auto Sync)' : 'Use other credentials'"
      />
    </template>
    <template v-else>
      <v-btn size="small" variant="outlined" :disabled="!url.trim()" @click="signInHere">Sign in to {{ label }}</v-btn>
      <span class="text-body-2 text-medium-emphasis">or enter credentials below</span>
    </template>
  </div>
</template>

<script lang="ts">
import { computed, defineComponent, PropType } from 'vue';
import { SourceKind, SourceSession, labelOf, openSignIn, signOut } from './sourceAuth';

export default defineComponent({
  name: 'SourceSignInSection',
  props: {
    source: { type: String as PropType<SourceKind>, required: true },
    url: { type: String, required: true },
    session: { type: Object as PropType<SourceSession | null>, default: null },
    usingSignIn: { type: Boolean, default: false },
    useOther: { type: Boolean, default: false },
  },
  emits: ['update:useOther'],
  setup(props) {
    const label = computed(() => labelOf(props.source));
    const signInHere = () => openSignIn({ source: props.source, url: props.url, methods: ['basic'], documents: null }, 'ingest');
    return { label, signInHere, signOut };
  },
});
</script>
