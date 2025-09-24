<template>
  <BaseSourceForm
    title="Wikipedia"
    description="Extract content from Wikipedia articles"
  >
    <v-text-field
      :model-value="url"
      @update:model-value="handleUrlChange"
      label="Wikipedia URL or Query"
      variant="outlined"
      class="mb-2"
      placeholder="https://en.wikipedia.org/wiki/Article_Name or search query"
      hint="Enter a Wikipedia URL or search query to extract content from"
      persistent-hint
    />
    
    <v-row class="mb-2">
      <v-col cols="6">
        <v-select
          :model-value="language"
          @update:model-value="handleLanguageChange"
          :items="languageOptions"
          label="Language"
          variant="outlined"
        />
      </v-col>
      <v-col cols="6">
        <v-text-field
          :model-value="maxDocs"
          @update:model-value="handleMaxDocsChange"
          label="Max Documents"
          variant="outlined"
          type="number"
          min="1"
          max="50"
          hint="Maximum number of articles to retrieve"
          persistent-hint
        />
      </v-col>
    </v-row>
  </BaseSourceForm>
</template>

<script lang="ts">
import { defineComponent, computed, watch } from 'vue';
import BaseSourceForm from './BaseSourceForm.vue';

export default defineComponent({
  name: 'WikipediaSourceForm',
  components: {
    BaseSourceForm
  },
  props: {
    url: {
      type: String,
      default: ''
    },
    language: {
      type: String,
      default: 'en'
    },
    maxDocs: {
      type: Number,
      default: 5
    }
  },
  emits: ['update:url', 'update:language', 'update:maxDocs', 'configuration-change', 'validation-change'],
  setup(props, { emit }) {
    const languageOptions = [
      { title: 'English', value: 'en' },
      { title: 'Spanish', value: 'es' },
      { title: 'French', value: 'fr' },
      { title: 'German', value: 'de' },
      { title: 'Italian', value: 'it' },
      { title: 'Portuguese', value: 'pt' },
      { title: 'Russian', value: 'ru' },
      { title: 'Chinese', value: 'zh' },
      { title: 'Japanese', value: 'ja' },
      { title: 'Korean', value: 'ko' }
    ];

    const isValid = computed(() => {
      return props.url.trim() !== '';
    });

    const config = computed(() => {
      // Extract query from URL if it's a Wikipedia URL
      let query = props.url;
      if (props.url.includes('wikipedia.org/wiki/')) {
        const parts = props.url.split('/wiki/');
        if (parts.length > 1) {
          query = decodeURIComponent(parts[1]);
          // Only replace underscores with spaces if the title doesn't contain hyphens
          // This preserves titles like "Nasdaq-100" while still handling "Albert_Einstein"
          if (!query.includes('-')) {
            query = query.replace(/_/g, ' ');
          }
        }
      }

      return {
        query: query,
        language: props.language,
        max_docs: props.maxDocs
      };
    });

    // Emit validation and configuration changes
    watch([isValid, config], ([newIsValid, newConfig]) => {
      emit('validation-change', newIsValid);
      emit('configuration-change', newConfig);
    }, { immediate: true });

    const handleUrlChange = (value: string) => {
      emit('update:url', value);
    };

    const handleLanguageChange = (value: string) => {
      emit('update:language', value);
    };

    const handleMaxDocsChange = (value: number) => {
      emit('update:maxDocs', value);
    };

    return {
      languageOptions,
      handleUrlChange,
      handleLanguageChange,
      handleMaxDocsChange,
    };
  },
});
</script>
