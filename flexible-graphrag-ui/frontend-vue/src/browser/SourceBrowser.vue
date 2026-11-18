<template>
  <v-dialog :model-value="open" max-width="1100" scrollable @update:model-value="(v: boolean) => { if (!v) close(); }">
    <v-card>
      <v-card-title>{{ title || `Browse ${provider.label}` }}</v-card-title>
      <v-divider />
      <v-card-text style="height: 60vh">
        <v-alert v-if="error" type="warning" density="compact" class="mb-2">{{ error }}</v-alert>
        <div class="d-flex align-center mb-1">
          <v-breadcrumbs :items="crumbs" density="compact" class="pa-0 flex-grow-1">
            <template #item="{ item, index }">
              <a v-if="index < crumbs.length - 1" href="#" @click.prevent="goTo(index)">{{ item.title }}</a>
              <span v-else>{{ item.title }}</span>
            </template>
          </v-breadcrumbs>
          <v-btn icon="mdi-refresh" variant="text" size="small" title="Refresh" :disabled="loading" @click="reload" />
        </div>
        <v-progress-linear v-if="loading" indeterminate class="mb-1" />
        <v-table density="compact" fixed-header hover>
          <thead>
            <tr>
              <th style="width: 40px" />
              <th>Name</th>
              <th style="width: 110px">Size</th>
              <th style="width: 190px">Modified</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!loading && !items.length">
              <td colspan="4" class="text-medium-emphasis">{{ error ? '' : 'Empty folder' }}</td>
            </tr>
            <tr
              v-for="item in items"
              :key="item.id"
              style="cursor: pointer"
              @click="toggle(item)"
              @dblclick="item.isDirectory && openFolder(item)"
            >
              <td>
                <v-checkbox-btn :model-value="isSelected(item)" density="compact" @click.stop="toggle(item)" />
              </td>
              <td>
                <v-icon size="small" class="mr-1" :color="item.isDirectory ? 'amber-darken-2' : undefined">
                  {{ item.isDirectory ? 'mdi-folder' : 'mdi-file-outline' }}
                </v-icon>
                <a v-if="item.isDirectory" href="#" @click.prevent.stop="openFolder(item)">{{ item.name }}</a>
                <span v-else>{{ item.name }}</span>
              </td>
              <td>{{ item.isDirectory || item.size == null ? '' : formatSize(item.size) }}</td>
              <td>{{ formatDate(item.modified) }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>
      <v-divider />
      <div class="px-4 pt-2">
        <div class="text-caption text-medium-emphasis">{{ caption }}</div>
        <div v-if="selectionProblem" class="text-caption text-warning">{{ selectionProblem }}</div>
      </div>
      <v-card-actions>
        <v-spacer />
        <v-btn @click="close">Cancel</v-btn>
        <v-btn :disabled="!currentFolder" @click="currentFolder && pick([currentFolder])">
          {{ replaces ? 'Use this folder' : 'Add this folder' }}
        </v-btn>
        <v-btn color="primary" variant="flat" :disabled="!selected.length || !!selectionProblem" @click="pick(selected)">
          {{ `${replaces ? 'Use' : 'Add'} selected${multiple && selected.length ? ` (${selected.length})` : ''}` }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script lang="ts">
import { defineComponent, ref, computed, watch, type PropType } from 'vue';
import type { BrowseItem, BrowseProvider } from './types';
import { saveTrail, startTrail } from './lastFolder';

const MAX_PAGES = 50;

/**
 * A read-only picker over any BrowseProvider (the Vue port of frontend-react's SourceBrowser):
 * one folder level at a time, opened from a breadcrumb. `files` / `multiple` / `mixed` say what
 * the source's config can hold (files too; several; folders and files together), with the same
 * rules and messages as the React browser.
 */
export default defineComponent({
  name: 'SourceBrowser',
  props: {
    open: { type: Boolean, default: false },
    provider: { type: Object as PropType<BrowseProvider>, required: true },
    title: { type: String, default: '' },
    /** files too (default yes) */
    files: { type: Boolean, default: true },
    /** several (default yes) */
    multiple: { type: Boolean, default: true },
    /** folders and files together (default yes; no = one folder, or files only: OneDrive
     *  folder_path / file_ids). files + multiple=false: one folder or one file (CMIS folder_path). */
    mixed: { type: Boolean, default: true },
  },
  emits: ['close', 'select'],
  setup(props, { emit }) {
    // the opened folders, root first (empty = the source's roots)
    const trail = ref<BrowseItem[]>([]);
    const items = ref<BrowseItem[]>([]);
    const selected = ref<BrowseItem[]>([]);
    const loading = ref(false);
    const error = ref('');
    let request = 0; // a newer listing wins over a slower older one

    const currentFolder = computed(() => trail.value[trail.value.length - 1] || null);
    const crumbs = computed(() => [
      { title: props.provider.label },
      ...trail.value.map((f) => ({ title: f.name })),
    ]);

    const sortItems = (list: BrowseItem[]) =>
      [...list].sort((a, b) => (a.isDirectory === b.isDirectory ? 0 : a.isDirectory ? -1 : 1));

    // all of one folder's children, page by page
    const listAll = async (folder: BrowseItem): Promise<BrowseItem[]> => {
      const listed: BrowseItem[] = [];
      let token: string | null | undefined = null;
      for (let page = 0; page < MAX_PAGES; page++) {
        const listing = await props.provider.list(folder, token);
        listed.push(...listing.items);
        token = listing.nextPageToken;
        if (!token) break;
      }
      return listed;
    };

    const load = async () => {
      const mine = ++request;
      const folder = currentFolder.value;
      loading.value = true;
      error.value = '';
      selected.value = [];
      saveTrail(props.provider.key, trail.value);
      try {
        const listed = folder ? await listAll(folder) : await props.provider.roots();
        if (mine === request) items.value = sortItems(listed);
      } catch (e: any) {
        if (mine === request) {
          items.value = [];
          error.value = `Could not list ${folder ? (folder.path || folder.name) : props.provider.label}: ${e?.message || e}`;
        }
      } finally {
        if (mine === request) loading.value = false;
      }
    };

    // A fresh start each time the browser opens: the folder last open in this source's browser when
    // its root is still among the roots and it still lists, else the roots
    const restore = async () => {
      const mine = ++request;
      trail.value = [];
      items.value = [];
      selected.value = [];
      error.value = '';
      loading.value = true;
      try {
        const [roots, saved] = await Promise.all([props.provider.roots(), startTrail(props.provider)]);
        if (mine !== request) return;
        const root = saved.length ? roots.find((r) => r.id === saved[0].id) : undefined;
        if (root) {
          const folders = [root, ...saved.slice(1)];
          try {
            const listed = await listAll(folders[folders.length - 1]);
            if (mine !== request) return;
            trail.value = folders;
            items.value = sortItems(listed);
            return;
          } catch { /* gone or unreadable now: the roots */ }
        }
        if (mine === request) items.value = sortItems(roots);
      } catch (e: any) {
        if (mine === request) error.value = `Could not list ${props.provider.label}: ${e?.message || e}`;
      } finally {
        if (mine === request) loading.value = false;
      }
    };
    watch(() => props.open, (open) => { if (open) restore(); }, { immediate: true });

    const openFolder = (folder: BrowseItem) => {
      trail.value = [...trail.value, folder];
      load();
    };
    const goTo = (index: number) => {
      // crumb 0 = the roots, crumb n = trail[n - 1]
      trail.value = trail.value.slice(0, index);
      load();
    };
    const reload = () => load();

    const isSelected = (item: BrowseItem) => selected.value.some((s) => s.id === item.id);
    const toggle = (item: BrowseItem) => {
      selected.value = isSelected(item)
        ? selected.value.filter((s) => s.id !== item.id)
        : [...selected.value, item];
    };

    // why the selection can't be added (the source's config can't hold it), '' when it can
    const selectionProblem = computed(() => {
      const sel = selected.value;
      const folderCount = sel.filter((s) => s.isDirectory).length;
      if (!props.files && sel.some((s) => !s.isDirectory)) return 'Pick a folder: this source takes a folder, not files.';
      if (!props.multiple && sel.length > 1) {
        return props.files ? 'Pick one folder or file: this source takes a single path.'
          : 'Pick one folder: this source takes a single folder.';
      }
      if (!props.mixed && folderCount > 0 && sel.length > 1) {
        return 'Pick one folder, or files only: this source takes a folder or a list of files.';
      }
      return '';
    });
    // the pick replaces what the form had (one folder / one list), rather than adding to it
    const replaces = computed(() => !props.multiple || !props.mixed);

    const caption = computed(() =>
      !props.multiple && props.files
        ? 'Open a folder to see what is in it. Select one folder or file, or use the folder you are in.'
        : !props.mixed && props.files
        ? 'Open a folder to see what is in it. Select one folder or several files, or use the folder you are in.'
        : props.multiple || props.files
        ? 'Open a folder to see what is in it. Select files and folders, or add the folder you are in.'
        : 'Open a folder to see what is in it. Select a folder, or use the folder you are in.');

    const close = () => emit('close');
    const pick = (picked: BrowseItem[]) => {
      emit('select', picked);
      emit('close');
    };

    const formatSize = (bytes: number) => {
      if (bytes < 1024) return `${bytes} B`;
      const units = ['KB', 'MB', 'GB', 'TB'];
      let v = bytes / 1024;
      let u = 0;
      while (v >= 1024 && u < units.length - 1) { v /= 1024; u++; }
      return `${v.toFixed(v < 10 ? 1 : 0)} ${units[u]}`;
    };
    const formatDate = (iso?: string) => {
      if (!iso) return '';
      const d = new Date(iso);
      return isNaN(d.getTime()) ? iso : d.toLocaleString();
    };

    return {
      items, selected, loading, error, currentFolder, crumbs, selectionProblem, replaces, caption,
      openFolder, goTo, reload, isSelected, toggle, close, pick, formatSize, formatDate,
    };
  },
});
</script>
