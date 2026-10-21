<template>
  <!-- Deep: a selected folder's subfolders, at every depth, are ingested too and its auto sync
       follows them. Off: only the documents directly in the folder. Sent as `recursive`. -->
  <v-checkbox
    :model-value="checked"
    @update:model-value="(v: any) => $emit('change', !!v)"
    label="Deep"
    title="Include subfolders, at every depth, in the ingest and its auto sync"
    density="compact"
    hide-details
    class="flex-grow-0 ml-2 text-no-wrap"
  />
</template>

<script lang="ts">
import { defineComponent } from 'vue';

export default defineComponent({
  name: 'DeepCheckbox',
  props: { checked: { type: Boolean, required: true } },
  emits: ['change'],
});
</script>
