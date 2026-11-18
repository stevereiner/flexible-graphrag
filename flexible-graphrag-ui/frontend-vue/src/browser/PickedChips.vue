<template>
  <div v-if="items.length" class="mb-2">
    <div class="text-caption mb-1" style="opacity: 0.8">
      {{ items.length === 1 ? `1 ${noun} picked` : `${items.length} ${noun}s picked` }}: {{ note }}
    </div>
    <div class="d-flex flex-wrap ga-1 align-center">
      <v-chip
        v-for="item in items"
        :key="item.id"
        size="small"
        closable
        @click:close="$emit('remove', item.id)"
      >
        {{ item.path || item.name }}
      </v-chip>
      <v-btn size="small" variant="text" @click="$emit('clear')">Clear</v-btn>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, type PropType } from 'vue';

/** The files / items picked in the source browser, as removable chips (React's chip rows). */
export default defineComponent({
  name: 'PickedChips',
  props: {
    items: { type: Array as PropType<{ id: string; name: string; path?: string }[]>, default: () => [] },
    noun: { type: String, default: 'file' },
    note: { type: String, default: 'the ingest reads these instead of a folder' },
  },
  emits: ['remove', 'clear'],
});
</script>
