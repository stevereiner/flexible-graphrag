<template>
  <span v-if="docs && docs.length">
    <strong v-if="label" class="mr-1">{{ label }}</strong>
    <template v-for="(doc, i) in docs" :key="doc.doc_id || doc.name || i">
      <a
        v-if="doc.open_url"
        :href="doc.open_url"
        target="_blank"
        rel="noopener noreferrer"
        class="source-doc-link"
        :title="doc.path || doc.name"
      >{{ doc.name }}</a>
      <template v-else-if="openable(doc)">
        <a href="#" class="source-doc-link" :title="`Open ${doc.path}`" @click.prevent="openLocal(doc.path, false)">{{ doc.name }}</a>
        <v-btn
          icon="mdi-folder-open-outline"
          size="x-small"
          variant="text"
          density="compact"
          class="ml-1"
          title="Show in folder"
          @click="openLocal(doc.path, true)"
        />
      </template>
      <span v-else :title="doc.path || doc.name">{{ doc.name }}</span>
      <span v-if="i < docs.length - 1">, </span>
    </template>
    <span v-if="error" class="d-block text-error" style="font-size: 0.8em">{{ error }}</span>
  </span>
</template>

<script lang="ts">
import { defineComponent, PropType, ref } from 'vue';
import { invoke, isTauri } from '../desktop/tauri';
import { openRoots } from '../desktop/localRoots';
import { isRemoteBackend } from '../apiConnection';

/** A document a search result or an answer came from (backend doc_refs.py). */
export interface SourceDocument {
  doc_id: string;
  name: string;
  path: string;
  source_type: string;  // 'alfresco' | 'nuxeo' | '' (other sources)
  node_id: string;      // repository node id (Alfresco / Nuxeo)
  parent_id?: string;   // an Alfresco document's folder id ('' when unknown)
  open_url: string;     // link to the document (Alfresco Share, Nuxeo Web UI); '' when none
  backend?: string;     // a remote backend's document (REMOTE_FG_*): its name; its path is on that machine
}

/** Display names of the data source types a result's documents came from (backend source_type). */
const SOURCE_TYPE_LABELS: Record<string, string> = {
  alfresco: 'Alfresco', nuxeo: 'Nuxeo', cmis: 'CMIS', sharepoint: 'SharePoint', onedrive: 'OneDrive',
  box: 'Box', google_drive: 'Google Drive', s3: 'Amazon S3', gcs: 'Google Cloud Storage',
  azure_blob: 'Azure Blob', filesystem: 'Files', upload: 'Uploads', web: 'Web', wikipedia: 'Wikipedia',
  youtube: 'YouTube',
};

/** The data source part of a result's source line ("SharePoint"), '' when unknown. */
export const sourceTypeLabel = (docs?: { source_type?: string }[]): string =>
  Array.from(new Set((docs || []).map((d) => d.source_type || '').filter(Boolean)))
    .map((t) => SOURCE_TYPE_LABELS[t] || t).join(', ');

/** The store part of a result's source label ("a.txt | Neo4j property graph" -> "Neo4j property graph"). */
export const storeLabel = (source?: string): string => {
  const s = source || '';
  const i = s.lastIndexOf(' | ');
  return i >= 0 ? s.slice(i + 3) : '';
};

/** A local file's path (Windows drive or UNC path, or a Unix path): the desktop app can open it. */
const isLocalPath = (p?: string): boolean => !!p && (/^[A-Za-z]:[\\/]/.test(p) || p.startsWith('\\\\') || p.startsWith('/'));

/**
 * The documents a search result or an answer came from. A document with an open link
 * (Alfresco Share, Nuxeo Web UI) opens in a new tab. In the desktop app a local file opens with
 * its default app, and its folder button shows it in its folder (desktop/src-tauri/src/open_file.rs,
 * which opens only files inside the folders added in the app or the backend's own allowed folders,
 * desktop/localRoots.ts openRoots). Others are plain names (a remote backend's files among them).
 */
export default defineComponent({
  name: 'SourceDocs',
  props: {
    docs: { type: Array as PropType<SourceDocument[]>, default: () => [] },
    /** Text before the list, e.g. "Sources:". */
    label: { type: String, default: '' },
  },
  setup() {
    const desktop = isTauri();
    const error = ref('');
    const openLocal = (path: string, reveal: boolean) => {
      error.value = '';
      openRoots()
        .then((roots) => invoke<void>('open_local_file', { path, roots, reveal }))
        .catch((e) => { error.value = String(e); });
    };
    // a file on this computer: not a remote backend's document, nor with the app's backend elsewhere
    const openable = (doc: SourceDocument) => desktop && !doc.backend && !isRemoteBackend() && isLocalPath(doc.path);
    return { desktop, error, openLocal, openable };
  },
});
</script>

<style scoped>
.source-doc-link {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}
.source-doc-link:hover {
  text-decoration: underline;
}
</style>
