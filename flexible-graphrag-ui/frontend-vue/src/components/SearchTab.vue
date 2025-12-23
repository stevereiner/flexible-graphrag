<template>
  <div class="pa-4">
    <v-tabs 
      v-model="activeTab" 
      class="mb-4"
      color="primary"
      slider-color="primary">
      <v-tab value="search">Hybrid Search</v-tab>
      <v-tab value="qa">AI Query</v-tab>
    </v-tabs>

    <!-- Search Input -->
    <div class="d-flex ga-2 mb-4">
      <v-text-field
        v-model="question"
        :label="activeTab === 'search' ? 'Search terms' : 'Ask a question'"
        variant="outlined"
        :placeholder="activeTab === 'search' 
          ? 'e.g., machine learning algorithms' 
          : 'e.g., What are the key findings?'"
        @keyup.enter="handleSearch"
        :disabled="isQuerying"
      ></v-text-field>
      <v-btn
        color="primary"
        size="large"
        :disabled="isQuerying || !question.trim()"
        :loading="isQuerying"
        @click="handleSearch"
        style="min-width: 150px;"
      >
        {{ activeTab === 'search' ? 'SEARCH' : 'ASK' }}
      </v-btn>
    </div>

    <v-window v-model="activeTab">
      <!-- Search Results Tab -->
      <v-window-item value="search">
        <div v-if="searchResults.length > 0" class="mt-4">
          <h3 class="mb-4">Search Results ({{ searchResults.length }})</h3>
          <v-card
            v-for="(result, index) in searchResults"
            :key="index"
            class="pa-4 mb-4"
            variant="outlined"
          >
            <div class="text-caption text-medium-emphasis mb-2">
              <strong>Source:</strong> {{ result.metadata?.source || 'Unknown' }} | 
              <strong> Score:</strong> {{ result.score?.toFixed(3) || 'N/A' }}
            </div>
            <p>{{ result.text || result.content || 'No content available' }}</p>
          </v-card>
        </div>
        
        <v-card
          v-if="hasSearched && searchResults.length === 0 && !isQuerying"
          class="pa-6 mt-4 text-center"
          variant="outlined"
        >
          <h3 class="text-medium-emphasis mb-2">No results found</h3>
          <p class="text-medium-emphasis">
            No results found for "{{ lastSearchQuery }}". Try different search terms.
          </p>
        </v-card>
      </v-window-item>

      <!-- Q&A Results Tab -->
      <v-window-item value="qa">
        <v-card
          v-if="qaAnswer"
          class="pa-4 mt-4"
          variant="outlined"
        >
          <div>
            <strong>Answer:</strong> {{ qaAnswer }}
          </div>
        </v-card>
      </v-window-item>
    </v-window>

    <!-- Error Message -->
    <v-alert
      v-if="error"
      type="error"
      class="mt-4"
      closable
      @click:close="error = ''"
    >
      {{ error }}
    </v-alert>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref, watch } from 'vue';
import axios from 'axios';

interface QueryRequest {
  query: string;
  query_type?: string;
  top_k?: number;
}

interface ApiResponse {
  success?: boolean;
  status?: string;
  message?: string;
  error?: string;
  answer?: string;
  results?: any[];
}

export default defineComponent({
  name: 'SearchTab',
  setup() {
    // State
    const activeTab = ref('search');
    const question = ref('');
    const searchResults = ref<any[]>([]);
    const qaAnswer = ref('');
    const hasSearched = ref(false);
    const lastSearchQuery = ref('');
    const isQuerying = ref(false);
    const error = ref('');

    // Methods
    const handleSearch = async () => {
      if (!question.value.trim() || isQuerying.value) return;
      
      try {
        isQuerying.value = true;
        error.value = '';
        searchResults.value = [];
        qaAnswer.value = '';
        lastSearchQuery.value = question.value;
        
        const queryType = activeTab.value === 'search' ? 'hybrid' : 'qa';
        const request: QueryRequest = {
          query: question.value,
          query_type: queryType,
          top_k: 10
        };
        
        const response = await axios.post<ApiResponse>('/api/search', request);
        
        if (response.data.success) {
          hasSearched.value = true;
          if (activeTab.value === 'search' && response.data.results) {
            searchResults.value = response.data.results;
          } else if (activeTab.value === 'qa' && response.data.answer) {
            qaAnswer.value = response.data.answer;
          }
        } else {
          hasSearched.value = true;
          error.value = response.data.error || 'Error executing query';
        }
      } catch (err) {
        console.error('Error querying:', err);
        const errorMessage = axios.isAxiosError(err)
          ? err.response?.data?.detail || err.response?.data?.error || 'Error executing query'
          : 'An unknown error occurred';
        error.value = errorMessage;
        hasSearched.value = true;
      } finally {
        isQuerying.value = false;
      }
    };

    // Clear results when tab changes
    watch(activeTab, () => {
      searchResults.value = [];
      qaAnswer.value = '';
      error.value = '';
      hasSearched.value = false;
      lastSearchQuery.value = '';
    });

    return {
      activeTab,
      question,
      searchResults,
      qaAnswer,
      hasSearched,
      lastSearchQuery,
      isQuerying,
      error,
      handleSearch,
    };
  },
});
</script>
