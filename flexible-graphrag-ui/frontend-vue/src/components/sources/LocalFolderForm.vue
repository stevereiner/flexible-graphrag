<template>
  <BaseSourceForm
    title="Local Files and Folders"
    description="Files and folders on this computer. A folder includes everything below it."
  >
    <div class="d-flex ga-2 mb-2">
      <v-btn variant="outlined" prepend-icon="mdi-folder-open" @click="browsing = true">Browse…</v-btn>
      <v-btn v-if="items.length" variant="text" @click="setItems([])">Clear</v-btn>
    </div>

    <div v-if="!items.length" class="text-body-2" style="opacity: 0.7">Nothing picked yet.</div>
    <v-list v-else density="compact">
      <v-list-item v-for="item in items" :key="item.path" :title="item.path">
        <template #prepend>
          <v-icon size="small">{{ item.isDirectory ? 'mdi-folder' : 'mdi-file-outline' }}</v-icon>
        </template>
        <template #append>
          <v-btn
            icon="mdi-delete"
            size="small"
            variant="text"
            title="Leave out"
            @click="setItems(items.filter((i) => i.path !== item.path))"
          />
        </template>
      </v-list-item>
    </v-list>

    <v-alert
      v-if="notice"
      :type="notice.severity"
      density="compact"
      variant="tonal"
      class="mt-2"
      closable
      @click:close="notice = null"
    >{{ notice.text }}</v-alert>

    <SourceBrowser
      :open="browsing"
      :provider="localProvider"
      title="Add files and folders from this computer"
      @close="browsing = false"
      @select="handleSelect"
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch, type PropType } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';
import SourceBrowser from '../../browser/SourceBrowser.vue';
import { localProvider } from '../../browser/localProvider';
import type { BrowseItem } from '../../browser/types';
import { addLocalRoots } from '../../desktop/localRoots';

/** A picked local file or folder: its native path. */
export interface LocalItem {
  path: string;
  isDirectory: boolean;
}

/**
 * Local files and folders (desktop app only): picked with the file browser, ingested by path as
 * the filesystem source (folders with everything below them), and kept in sync when Auto Sync is
 * on. The picked paths are added to the backend's allowed ingest folders (desktop/localRoots.ts).
 * The Vue port of frontend-react's LocalFolderForm; App holds the items (v-model:items).
 */
export default defineComponent({
  name: 'LocalFolderForm',
  components: { BaseSourceForm, SourceBrowser },
  props: {
    items: { type: Array as PropType<LocalItem[]>, default: () => [] },
  },
  emits: ['update:items', 'configuration-change', 'validation-change'],
  setup(props, { emit }) {
    const browsing = ref(false);
    const notice = ref<{ severity: 'warning' | 'info'; text: string } | null>(null);

    const config = computed(() => ({ paths: props.items.map((i) => i.path), items: props.items }));

    watch(config, (c) => {
      emit('validation-change', props.items.length > 0);
      emit('configuration-change', c);
    }, { immediate: true });

    const setItems = (items: LocalItem[]) => emit('update:items', items);

    // picks add up (several folders) until an ingest starts; App then empties the list (ingestSignal)

    const handleSelect = async (picked: BrowseItem[]) => {
      const add = picked
        .map((p) => ({ path: p.path || p.id, isDirectory: p.isDirectory }))
        .filter((p) => !props.items.some((i) => i.path === p.path));
      if (!add.length) return;
      setItems([...props.items, ...add]);
      const result = await addLocalRoots(add.map((a) => a.path));
      notice.value = result.message ? { severity: result.ok ? 'info' : 'warning', text: result.message } : null;
    };

    return { browsing, notice, localProvider, setItems, handleSelect };
  },
});
</script>
