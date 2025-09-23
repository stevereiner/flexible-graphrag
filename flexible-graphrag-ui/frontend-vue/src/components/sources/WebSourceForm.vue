<template>
  <BaseSourceForm
    title="Web Page"
    description="Extract content from any web page"
  >
    <v-text-field
      :model-value="url"
      @update:model-value="handleUrlChange"
      label="Website URL"
      variant="outlined"
      class="mb-2"
      placeholder="https://example.com"
      hint="Enter a valid website URL to extract content from"
      persistent-hint
    />
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'WebSourceForm',
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
      return props.url.trim() !== '' && props.url.startsWith('http');
    });

    const config = computed(() => ({
      url: props.url
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
