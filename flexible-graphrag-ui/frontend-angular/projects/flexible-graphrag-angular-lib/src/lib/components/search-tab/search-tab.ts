import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FlexibleGraphragConfigService } from '../../config.service';
import { SourceDocument } from '../../models/api.models';
import { ProcessingSessionService } from '../../services/processing-session.service';
import { SourceAuthService } from '../../services/source-auth.service';

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
  sources?: SourceDocument[];
  results?: any[];
}

@Component({
  selector: 'app-search-tab',
  templateUrl: './search-tab.html',
  styleUrls: ['./search-tab.scss'],
  standalone: false
})
export class SearchTabComponent implements OnInit, OnDestroy {
  activeTabIndex = 0;
  question = '';
  searchResults: any[] = [];
  qaAnswer = '';
  qaSources: SourceDocument[] = [];
  hasSearched = false;
  lastSearchQuery = '';
  isQuerying = false;
  error = '';
  // Why a search found nothing, when the backend says (e.g. the matches are in Alfresco and the
  // user continued without signing in)
  emptyMessage = '';
  private readonly sourceAuth = inject(SourceAuthService);

  /** The store part of a result's source label ("a.txt | Neo4j property graph" -> "Neo4j property graph"). */
  storeLabel(result: any): string {
    const source: string = result.source || '';
    const i = source.lastIndexOf(' | ');
    return i >= 0 ? source.slice(i + 3) : '';
  }

  constructor(private http: HttpClient, private fgConfig: FlexibleGraphragConfigService,
              private session: ProcessingSessionService) {}

  /** Back on the page (e.g. after closing a result's document in ACA's viewer): take the
   * question and results back, if they are this user's. */
  ngOnInit(): void {
    const saved = this.session.searchTab;
    if (saved && saved.owner === this.owner()) {
      const { owner, ...state } = saved;
      Object.assign(this, state);
    }
  }

  ngOnDestroy(): void {
    this.session.searchTab = {
      owner: this.owner(),
      activeTabIndex: this.activeTabIndex,
      question: this.question,
      searchResults: this.searchResults,
      qaAnswer: this.qaAnswer,
      qaSources: this.qaSources,
      hasSearched: this.hasSearched,
      lastSearchQuery: this.lastSearchQuery,
    };
  }

  private owner(): string {
    return JSON.stringify(this.fgConfig.questionHeaders());
  }

  onTabChange(): void {
    // Clear results when tab changes
    this.searchResults = [];
    this.qaAnswer = '';
    this.qaSources = [];
    this.error = '';
    this.hasSearched = false;
    this.lastSearchQuery = '';
  }

  async handleSearch(): Promise<void> {
    if (!this.question.trim() || this.isQuerying) return;
    
    try {
      this.isQuerying = true;
      this.error = '';
      this.emptyMessage = '';
      this.searchResults = [];
      this.qaAnswer = '';
      this.qaSources = [];
      this.lastSearchQuery = this.question;
      
      const queryType = this.activeTabIndex === 0 ? 'hybrid' : 'qa';
      const request: QueryRequest = {
        query: this.question,
        query_type: queryType,
        top_k: 10
      };
      
      // Ask for an Alfresco sign-in first when the stores need one; on a 401 with our ticket
      // (expired, or signed out elsewhere) sign in again and ask once more
      await this.sourceAuth.beforeQuestion();
      const post = () => this.http.post<ApiResponse>(`${this.fgConfig.apiUrl}/search`, request,
        { headers: this.fgConfig.questionHeaders() }).toPromise();
      let response: ApiResponse | undefined;
      try {
        response = await post();
      } catch (err: any) {
        if (err?.status === 401 && await this.sourceAuth.afterUnauthorized()) response = await post();
        else throw err;
      }
      
      if (response?.success) {
        this.hasSearched = true;
        this.emptyMessage = response.message || '';
        if (this.activeTabIndex === 0 && response.results) {
          this.searchResults = response.results;
        } else if (this.activeTabIndex === 1 && response.answer) {
          this.qaAnswer = response.answer;
          this.qaSources = response.sources || [];
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