import { Component, ViewChild, ElementRef, AfterViewChecked, AfterViewInit, ChangeDetectorRef, Renderer2, inject } from '@angular/core';
import { FlexibleGraphragConfigService } from '../../config.service';
import { HttpClient } from '@angular/common/http';

interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  queryType?: 'search' | 'qa';
  results?: any[];
  isLoading?: boolean;
}

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
  selector: 'app-chat-tab',
  templateUrl: './chat-tab.html',
  styleUrls: ['./chat-tab.scss'],
  standalone: false
})
export class ChatTabComponent implements AfterViewChecked, AfterViewInit {
  private readonly fgConfig = inject(FlexibleGraphragConfigService);
  @ViewChild('chatContainer') chatContainer!: ElementRef;

  chatMessages: ChatMessage[] = [];
  chatInput = '';
  agentIcon = this.fgConfig.agentIconUrl;
  isQuerying = false;
  error = '';

  constructor(private http: HttpClient, private cdr: ChangeDetectorRef, private renderer: Renderer2) {}

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
        top_k: 10
      };
      
      const response = await this.http.post<ApiResponse>('/api/search', request).toPromise();
      
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