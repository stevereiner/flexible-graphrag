<template>
  <v-card class="pa-4">
    <v-card-title>Search and Query</v-card-title>
    <v-card-text>
      <!-- Tab Selection -->
      <v-tabs
        v-model="activeTab"
        class="mb-4"
        color="primary"
      >
        <v-tab value="search">Hybrid Search</v-tab>
        <v-tab value="qa">Q&A Query</v-tab>
      </v-tabs>

      <!-- Query Input -->
      <v-text-field
        v-model="question"
        :label="activeTab === 'search' ? 'Search terms' : 'Ask a question'"
        variant="outlined"
        @keyup.enter="handleQuery"
        :loading="isQuerying"
        :disabled="isQuerying"
        class="mb-4"
        :placeholder="activeTab === 'search' 
          ? 'e.g., machine learning algorithms' 
          : 'e.g., What are the key findings?'"
        @keydown.enter.prevent
      ></v-text-field>
      
      <v-btn
        color="primary"
        @click="handleQuery"
        :disabled="!question.trim() || isQuerying"
        :loading="isQuerying"
        size="large"
      >
        {{ isQuerying ? '' : (activeTab === 'search' ? 'Search' : 'Ask') }}
        <template v-slot:loader>
          <v-progress-circular indeterminate size="24"></v-progress-circular>
        </template>
      </v-btn>

      <!-- Search Results Tab -->
      <v-window v-model="activeTab" class="mt-4">
        <v-window-item value="search">
          <div v-if="searchResults.length > 0">
            <v-card-title class="pa-0 mb-3">
              Search Results ({{ searchResults.length }})
            </v-card-title>
            <v-card
              v-for="(result, index) in searchResults"
              :key="index"
              class="mb-3"
              variant="outlined"
            >
              <v-card-text>
                <div class="text-caption text-medium-emphasis mb-2">
                  <strong>Source:</strong> {{ result.file_name || result.metadata?.source || result.source || 'Unknown' }} | 
                  <strong>Score:</strong> {{ result.score?.toFixed(3) || 'N/A' }}
                </div>
                <div class="text-body-1">
                  {{ result.text || result.content || 'No content available' }}
                </div>
              </v-card-text>
            </v-card>
          </div>
          <!-- Show message when no results found after a search -->
          <v-alert
            v-else-if="hasSearched && !isQuerying"
            type="info"
            class="mt-4"
            variant="tonal"
          >
            No results found for "{{ lastSearchQuery }}". Try different search terms.
          </v-alert>
        </v-window-item>

        <!-- Q&A Answer Tab -->
        <v-window-item value="qa">
          <v-alert
            v-if="qaAnswer"
            type="info"
            class="mt-4"
            variant="tonal"
          >
            <div class="text-body-1">
              <strong>Answer:</strong> {{ qaAnswer }}
            </div>
          </v-alert>
        </v-window-item>
      </v-window>

      <!-- Error Alert -->
      <v-alert
        v-if="error"
        type="error"
        class="mt-4"
      >
        {{ error }}
      </v-alert>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import axios from 'axios';

interface QueryRequest {
  query: string;
  query_type?: string;
  top_k?: number;
}

interface ApiResponse {
  success: boolean;
  message?: string;
  error?: string;
  answer?: string;
  results?: any[];
}

// Reactive variables
const activeTab = ref('search');
const question = ref('');
const isQuerying = ref(false);
const error = ref('');
const searchResults = ref<any[]>([]);
const qaAnswer = ref('');
const hasSearched = ref(false);
const lastSearchQuery = ref('');

// Clear results when switching tabs
watch(activeTab, () => {
  error.value = '';
  searchResults.value = [];
  qaAnswer.value = '';
  hasSearched.value = false;
  lastSearchQuery.value = '';
});

const handleQuery = async (): Promise<void> => {
  if (!question.value.trim() || isQuerying.value) return;
  
  try {
    isQuerying.value = true;
    error.value = '';
    searchResults.value = [];
    qaAnswer.value = '';
    lastSearchQuery.value = question.value;
    
    console.log('Sending query request:', {
      query: question.value,
      type: activeTab.value
    });
    
    const queryType = activeTab.value === 'search' ? 'hybrid' : 'qa';
    const request: QueryRequest = {
      query: question.value,
      query_type: queryType,
      top_k: 10
    };
    
    const response = await axios({
      method: 'post',
      url: '/api/search',
      data: request,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    });
    
    console.log('Query response received:', response.data);
    
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
  } catch (err: any) {
    console.error('Error querying:', {
      message: err.message,
      response: err.response?.data,
      status: err.response?.status
    });
    error.value = err.response?.data?.detail || err.response?.data?.error || 'Error executing query';
  } finally {
    isQuerying.value = false;
  }
};
</script>