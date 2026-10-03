import { Component } from '@angular/core';
import { HttpClient } from '@angular/common/http';

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

@Component({
  selector: 'app-search-tab',
  templateUrl: './search-tab.html',
  styleUrls: ['./search-tab.scss'],
  standalone: false
})
export class SearchTabComponent {
  activeTabIndex = 0;
  question = '';
  searchResults: any[] = [];
  qaAnswer = '';
  hasSearched = false;
  lastSearchQuery = '';
  isQuerying = false;
  error = '';

  constructor(private http: HttpClient) {}

  onTabChange(): void {
    // Clear results when tab changes
    this.searchResults = [];
    this.qaAnswer = '';
    this.error = '';
    this.hasSearched = false;
    this.lastSearchQuery = '';
  }

  async handleSearch(): Promise<void> {
    if (!this.question.trim() || this.isQuerying) return;
    
    try {
      this.isQuerying = true;
      this.error = '';
      this.searchResults = [];
      this.qaAnswer = '';
      this.lastSearchQuery = this.question;
      
      const queryType = this.activeTabIndex === 0 ? 'hybrid' : 'qa';
      const request: QueryRequest = {
        query: this.question,
        query_type: queryType,
        top_k: 10
      };
      
      const response = await this.http.post<ApiResponse>('/api/search', request).toPromise();
      
      if (response?.success) {
        this.hasSearched = true;
        if (this.activeTabIndex === 0 && response.results) {
          this.searchResults = response.results;
        } else if (this.activeTabIndex === 1 && response.answer) {
          this.qaAnswer = response.answer;
        }
      } else {
        this.hasSearched = true;
        this.error = response?.error || 'Error executing query';
      }
    } catch (err: any) {
      console.error('Error querying:', err);
      const errorMessage = err?.error?.detail || err?.error?.error || 'Error executing query';
      this.error = errorMessage;
      this.hasSearched = true;
    } finally {
      this.isQuerying = false;
    }
  }
}