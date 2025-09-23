<template>
  <BaseSourceForm
    title="YouTube"
    description="Extract transcripts from YouTube videos"
  >
    <v-text-field
      :model-value="url"
      @update:model-value="handleUrlChange"
      label="YouTube URL"
      variant="outlined"
      class="mb-2"
      placeholder="https://www.youtube.com/watch?v=..."
      hint="Enter a YouTube video URL to extract transcript from"
      persistent-hint
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'YouTubeSourceForm',
  components: {
    BaseSourceForm
  },
  props: {
    url: {
      type: String,
      default: ''
    }
  },
  emits: ['update:url', 'configuration-change', 'validation-change'],
  setup(props, { emit }) {
    const isValid = computed(() => {
      return props.url.trim() !== '' && 
             (props.url.includes('youtube.com/watch') || props.url.includes('youtu.be/'));
    });

    const config = computed(() => ({
      url: props.url,
      chunk_size_seconds: 60  // Use default value
    }));

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleUrlChange = (value: string) => {
      emit('update:url', value);
    };

    return {
      handleUrlChange,
    };
  },
});
</script>
