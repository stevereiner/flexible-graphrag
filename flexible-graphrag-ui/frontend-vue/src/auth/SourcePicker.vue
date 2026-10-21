<template>
  <!-- Which sources a search / AI chat question covers (like Angel's content-lake UI): "All
       sources" plus one chip per source with documents in the stores. Several can be picked. A
       repository (Alfresco, Nuxeo, CMIS) needs a sign-in to that server first: its chip is greyed
       and clicking it opens the sign-in. Shared by Search and AI Chat; sent as the request's
       `sources` by sourceAuth's axios interceptor. Hidden with fewer than two sources. -->
  <div v-if="sources.length > 1" class="d-flex align-center flex-wrap ga-2 mb-4">
    <span class="text-body-2 text-medium-emphasis mr-1">Sources:</span>
    <v-chip
      size="small"
      :color="picked.length ? undefined : 'primary'"
      :variant="picked.length ? 'outlined' : 'flat'"
      @click="pickAll"
    >All sources</v-chip>
    <v-chip
      v-for="s in sources"
      :key="sourceKey(s)"
      size="small"
      :variant="isOn(s) ? 'flat' : 'outlined'"
      :color="SOURCE_COLORS[s.source] || (isOn(s) ? 'primary' : undefined)"
      :style="{ opacity: locked(s) ? 0.5 : 1 }"
      :title="locked(s)
        ? `Sign in to ${labelOf(signInFor(s).source)} first`
        : `${s.label} only (${s.documents} document${s.documents === 1 ? '' : 's'})${s.url ? ` — ${s.url}` : ''}`"
      @click="onChip(s)"
    >{{ chipLabel(s) }}</v-chip>
  </div>
</template>

<script lang="ts">
import { defineComponent, onMounted, onUnmounted, ref } from 'vue';
import {
  AvailableSource, Requirements, getAvailableSources, getPickedSources, getRequirements, onAuthChange,
  labelOf, openSignIn, setPickedSources, signInFor, sourceKey, sourceNeedsSignIn,
} from './sourceAuth';
import { SOURCE_COLORS } from './sourceColors';

export default defineComponent({
  name: 'SourcePicker',
  setup() {
    const sources = ref<AvailableSource[]>([]);
    const req = ref<Requirements>({ required: false, providers: [] });
    const picked = ref<string[]>(getPickedSources());
    let stop: (() => void) | null = null;

    const refresh = async (force = false) => {
      const [list, r] = await Promise.all([getAvailableSources(force), getRequirements(force)]);
      sources.value = list;
      req.value = r;
      // drop picks that are gone from the stores or now need a sign-in (e.g. after signing out)
      const usable = new Set(list.filter((s) => !sourceNeedsSignIn(s, r)).map(sourceKey));
      const kept = getPickedSources().filter((k) => usable.has(k));
      if (kept.length !== getPickedSources().length) setPickedSources(kept);
      picked.value = kept;
    };

    onMounted(() => {
      refresh(true);
      stop = onAuthChange(() => { refresh(); });
    });
    onUnmounted(() => stop?.());

    const locked = (s: AvailableSource) => sourceNeedsSignIn(s, req.value);
    const isOn = (s: AvailableSource) => picked.value.includes(sourceKey(s));
    const chipLabel = (s: AvailableSource) => {
      const several = sources.value.filter((x) => x.source === s.source).length > 1;
      return several && s.url ? `${s.label} (${s.url.replace(/^https?:\/\//, '')})` : s.label;
    };
    const pickAll = () => { setPickedSources([]); picked.value = []; };
    const onChip = (s: AvailableSource) => {
      if (locked(s)) {
        openSignIn({ ...signInFor(s), methods: ['basic'], documents: s.documents }, 'ask');
        return;
      }
      const key = sourceKey(s);
      const next = picked.value.includes(key) ? picked.value.filter((k) => k !== key) : [...picked.value, key];
      setPickedSources(next);
      picked.value = next;
    };

    return { sources, picked, locked, isOn, chipLabel, pickAll, onChip, sourceKey, SOURCE_COLORS, labelOf, signInFor };
  },
});
</script>
