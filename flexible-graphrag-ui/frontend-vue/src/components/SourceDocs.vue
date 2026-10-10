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
      <span v-else :title="doc.path || doc.name">{{ doc.name }}</span>
      <span v-if="i < docs.length - 1">, </span>
    </template>
  </span>
</template>

<script lang="ts">
import { defineComponent, PropType } from 'vue';

/** A document a search result or an answer came from (backend doc_refs.py). */
export interface SourceDocument {
  doc_id: string;
  name: string;
  path: string;
  source_type: string;  // 'alfresco' | 'nuxeo' | '' (other sources)
  node_id: string;      // repository node id (Alfresco / Nuxeo)
  parent_id?: string;   // an Alfresco document's folder id ('' when unknown)
  open_url: string;     // link to the document (Alfresco Share, Nuxeo Web UI); '' when none
}

/** The store part of a result's source label ("a.txt | Neo4j property graph" -> "Neo4j property graph"). */
export const storeLabel = (source?: string): string => {
  const s = source || '';
  const i = s.lastIndexOf(' | ');
  return i >= 0 ? s.slice(i + 3) : '';
};

/**
 * The documents a search result or an answer came from. A document with an open link
 * (Alfresco Share, Nuxeo Web UI) opens in a new tab; others are plain names.
 */
export default defineComponent({
  name: 'SourceDocs',
  props: {
    docs: { type: Array as PropType<SourceDocument[]>, default: () => [] },
    /** Text before the list, e.g. "Sources:". */
    label: { type: String, default: '' },
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
