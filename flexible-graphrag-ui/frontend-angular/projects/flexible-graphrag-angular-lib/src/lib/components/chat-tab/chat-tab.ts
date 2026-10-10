import { Component, ViewChild, ElementRef, AfterViewChecked, AfterViewInit, ChangeDetectorRef, Renderer2, inject,
         Input, Output, EventEmitter, OnChanges, OnDestroy, OnInit, SimpleChanges } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';
import { HttpClient } from '@angular/common/http';
import { AskScope, SourceDocument } from '../../models/api.models';
import { ProcessingSessionService } from '../../services/processing-session.service';

interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  queryType?: 'search' | 'qa';
  results?: any[];
  sources?: SourceDocument[];
  isLoading?: boolean;
}

interface QueryRequest {
  query: string;
  query_type?: string;
  top_k?: number;
  scope?: AskScope;
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
  selector: 'app-chat-tab',
  templateUrl: './chat-tab.html',
  styleUrls: ['./chat-tab.scss'],
  standalone: false
})
export class ChatTabComponent implements AfterViewChecked, AfterViewInit, OnChanges, OnInit, OnDestroy {
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  private readonly session = inject(ProcessingSessionService);
  @ViewChild('chatContainer') chatContainer!: ElementRef;

  /** Ask about this document or folder only; null = all content. */
  @Input() scope: AskScope | null = null;
  /** The user cleared the scope (the bar's ✕): back to all content. */
  @Output() scopeChange = new EventEmitter<AskScope | null>();

  welcomeTitle = this.fgConfig.chatWelcomeTitle;
  welcomeLines = this.fgConfig.chatWelcomeLines;
  showScopeBar = this.fgConfig.showChatScope;

  chatMessages: ChatMessage[] = [];
  chatInput = '';
  agentIcon = this.fgConfig.agentIconUrl;
  isQuerying = false;
  error = '';

  constructor(private http: HttpClient, private cdr: ChangeDetectorRef, private renderer: Renderer2) {}

  /** Back on the page (e.g. after closing an answer's document in ACA's viewer): take the
   * conversation back, if it is this user's and about the same document / folder. */
  ngOnInit(): void {
    const saved = this.session.chatTab;
    if (saved && saved.owner === this.owner() && saved.scopeKey === JSON.stringify(this.scope)) {
      this.chatMessages = saved['messages'] || [];
    }
  }

  ngOnDestroy(): void {
    this.session.chatTab = {
      owner: this.owner(),
      scopeKey: JSON.stringify(this.scope),
      messages: this.chatMessages.filter((m) => !m.isLoading),
    };
  }

  private owner(): string {
    return JSON.stringify(this.fgConfig.questionHeaders());
  }

  ngOnChanges(changes: SimpleChanges): void {
    // A new scope is a new conversation: earlier answers came from other documents
    const c = changes['scope'];
    if (c && !c.firstChange && JSON.stringify(c.currentValue) !== JSON.stringify(c.previousValue)) {
      this.chatMessages = [];
    }
  }

  get scopeLabel(): string {
    return this.scope ? (this.scope.name || this.scope.path || 'selected item') : 'All content';
  }

  get scopeIcon(): string {
    if (!this.scope) return 'travel_explore';
    return this.scope.is_folder ? 'folder' : 'description';
  }

  clearScope(): void {
    this.scope = null;
    this.chatMessages = [];
    this.scopeChange.emit(null);
  }

  ngAfterViewInit(): void {
    // Initial scroll setup
  }

  ngAfterViewChecked(): void {
    // Removed automatic scrolling from here - using direct calls instead
  }

  formatTime(timestamp: Date): string {
    return timestamp.toLocaleTimeString();
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      if (this.chatContainer && this.chatContainer.nativeElement) {
        const scrollContainer = this.chatContainer.nativeElement;
        console.log('ANGULAR SCROLL - Before:', {
          scrollTop: scrollContainer.scrollTop,
          scrollHeight: scrollContainer.scrollHeight,
          clientHeight: scrollContainer.clientHeight,
          hasOverflow: scrollContainer.scrollHeight > scrollContainer.clientHeight
        });
        
        // Simple, direct scroll to bottom
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
        
        console.log('ANGULAR SCROLL - After:', {
          scrollTop: scrollContainer.scrollTop,
          success: scrollContainer.scrollTop > 0
        });
      } else {
        console.log('ANGULAR SCROLL - Container not found!');
      }
    }, 100);
  }

  onEnterKey(event: any): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.handleChatSubmit();
    }
  }

  async handleChatSubmit(): Promise<void> {
    if (!this.chatInput.trim() || this.isQuerying) return;
    
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: this.chatInput.trim(),
      timestamp: new Date(),
      queryType: 'qa'
    };
    
    // Add user message
    this.chatMessages.push(userMessage);
    this.scrollToBottom();
    
    // Add loading assistant message
    const loadingMessage: ChatMessage = {
      id: (Date.now() + 1).toString(),
      type: 'assistant',
      content: '',
      timestamp: new Date(),
      queryType: 'qa',
      isLoading: true
    };
    this.chatMessages.push(loadingMessage);
    this.scrollToBottom();
    
    const currentInput = this.chatInput;
    this.chatInput = '';
    
    try {
      this.isQuerying = true;
      this.error = '';
      
      const request: QueryRequest = {
        query: currentInput,
        query_type: 'qa',
        top_k: 10,
        ...(this.scope ? { scope: this.scope } : {}),
      };
      
      const response = await this.http.post<ApiResponse>(`${this.fgConfig.apiUrl}/search`, request,
        { headers: this.fgConfig.questionHeaders() }).toPromise();
      
      // Remove loading message
      const messageIndex = this.chatMessages.findIndex(msg => msg.id === loadingMessage.id);
      if (messageIndex !== -1) {
        this.chatMessages.splice(messageIndex, 1);
      }
      
      if (response?.success) {
        const assistantMessage: ChatMessage = {
          id: (Date.now() + 2).toString(),
          type: 'assistant',
          content: response.answer || 'No answer provided',
          sources: response.sources || [],
          timestamp: new Date(),
          queryType: 'qa'
        };
        this.chatMessages.push(assistantMessage);
        this.scrollToBottom();
      } else {
        const errorMessage: ChatMessage = {
          id: (Date.now() + 2).toString(),
          type: 'assistant',
          content: `Error: ${response?.error || 'Unknown error occurred'}`,
          timestamp: new Date(),
          queryType: 'qa'
        };
        this.chatMessages.push(errorMessage);
      }
    } catch (err: any) {
      console.error('Error in chat query:', err);
      const errorMessage = err?.error?.detail || err?.error?.error || 'Error executing query';
      
            // Remove loading message
      const messageIndex = this.chatMessages.findIndex(msg => msg.id === loadingMessage.id);
      if (messageIndex !== -1) {
        this.chatMessages.splice(messageIndex, 1);
      }

      const errorMsg: ChatMessage = {
        id: (Date.now() + 2).toString(),
        type: 'assistant',
        content: `Error: ${errorMessage}`,
        timestamp: new Date(),
        queryType: 'qa'
      };
      this.chatMessages.push(errorMsg);
      this.scrollToBottom();
    } finally {
      this.isQuerying = false;
    }
  }

  clearChatHistory(): void {
    this.chatMessages = [];
  }
}