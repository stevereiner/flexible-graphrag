<template>
  <slot v-if="open" />
  <v-app v-else>
    <v-main>
      <div class="d-flex align-center justify-center pa-8" style="min-height: 100vh">
        <div v-if="status.state === 'failed'" style="max-width: 900px; width: 100%">
          <v-alert type="error" class="mb-4">
            <div class="text-subtitle-1 mb-2">No Flexible GraphRAG backend to use.</div>
            <pre class="text-body-2 ma-0" style="white-space: pre-wrap; word-break: break-word; font-family: monospace">{{ status.message }}</pre>
            <div v-if="status.log_path" class="text-body-2 mt-2">Log: {{ status.log_path }}</div>
          </v-alert>
          <v-btn variant="outlined" @click="openApp">Open the app anyway</v-btn>
        </div>
        <div v-else class="text-center">
          <v-progress-circular indeterminate class="mb-4" />
          <div class="text-h6">Starting the Flexible GraphRAG backend… {{ seconds > 0 ? `${seconds} s` : '' }}</div>
          <div class="text-body-2 text-medium-emphasis mt-2">The first start can take a minute or more.</div>
          <div v-if="status.log_path" class="text-caption text-medium-emphasis mt-2">Log: {{ status.log_path }}</div>
        </div>
      </div>
    </v-main>
  </v-app>
</template>

<script lang="ts">
import { defineComponent, onBeforeUnmount, onMounted, ref } from 'vue';
import { invoke } from './tauri';

/** desktop/src-tauri/src/backend.rs `backend_status` */
interface BackendStatus {
  state: 'starting' | 'ready' | 'external' | 'failed';
  message?: string | null;
  log_path?: string | null;
}

/**
 * Desktop app: the app starts its own backend, which takes a while (first start: a minute or
 * more). Show that here and render the app (the default slot) only once the backend answers, so
 * the app's first requests don't fail. The Vue port of frontend-react/src/desktop/BackendGate.tsx.
 */
export default defineComponent({
  name: 'BackendGate',
  emits: ['ready'],
  setup(_props, { emit }) {
    const status = ref<BackendStatus>({ state: 'starting' });
    const open = ref(false);
    const seconds = ref(0);
    let stop = false;
    let readyRan = false;

    const openApp = () => {
      open.value = true;
      if (!readyRan) {
        readyRan = true;
        emit('ready');
      }
    };

    onMounted(async () => {
      const started = Date.now();
      while (!stop) {
        try {
          const s = await invoke<BackendStatus>('backend_status');
          status.value = s;
          if (s.state === 'ready' || s.state === 'external') {
            openApp();
            return;
          }
          if (s.state === 'failed') return;
        } catch (e) {
          status.value = { state: 'failed', message: `backend_status: ${e}` };
          return;
        }
        seconds.value = Math.round((Date.now() - started) / 1000);
        await new Promise((r) => setTimeout(r, 1000));
      }
    });
    onBeforeUnmount(() => { stop = true; });

    return { status, open, seconds, openApp };
  },
});
</script>
