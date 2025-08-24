import React, { useEffect, useRef } from 'react';
import {
  Box,
  Typography,
  Button,
  TextField,
  Paper,
  CircularProgress,
  List,
  ListItem,
  Avatar,
  Divider,
  IconButton,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import PersonIcon from '@mui/icons-material/Person';
import { Theme } from '@mui/material/styles';
import axios from 'axios';
import { QueryRequest, ApiResponse, ChatMessage } from '../types/api';
import agentIcon from '../agent.png';

interface ChatTabProps {
  currentTheme: Theme;
  isDarkMode: boolean;
  chatMessages: ChatMessage[];
  chatInput: string;
  isQuerying: boolean;
  onChatMessagesChange: (messages: ChatMessage[]) => void;
  onChatInputChange: (input: string) => void;
  onIsQueryingChange: (isQuerying: boolean) => void;
}

export const ChatTab: React.FC<ChatTabProps> = ({ 
  currentTheme, 
  isDarkMode,
  chatMessages,
  chatInput,
  isQuerying,
  onChatMessagesChange,
  onChatInputChange,
  onIsQueryingChange,
}) => {
  // Local state (only for UI-specific state that doesn't need persistence)  
  const chatContainerRef = useRef<HTMLDivElement>(null);
  // Chat state now comes from props for persistence

  // Auto-scroll to bottom of chat
  const scrollToBottom = () => {
    if (chatContainerRef.current) {
      chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
    }
  };

  // Auto-scroll when messages change
  useEffect(() => {
    scrollToBottom();
  }, [chatMessages]);

  // Chat functionality
  const handleChatSubmit = async (): Promise<void> => {
    if (!chatInput.trim() || isQuerying) return;
    
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      type: 'user',
      content: chatInput.trim(),
      timestamp: new Date(),
      queryType: 'qa'
    };
    
    // Add user message
    onChatMessagesChange([...chatMessages, userMessage]);
    
    // Add loading assistant message
    const loadingMessage: ChatMessage = {
      id: (Date.now() + 1).toString(),
      type: 'assistant',
      content: '',
      timestamp: new Date(),
      queryType: 'qa',
      isLoading: true
    };
    onChatMessagesChange([...chatMessages, userMessage, loadingMessage]);
    
    const currentInput = chatInput;
    onChatInputChange('');
    
    try {
      onIsQueryingChange(true);
      
      const request: QueryRequest = {
        query: currentInput,
        query_type: 'qa',
        top_k: 10
      };
      
      const response = await axios.post<ApiResponse>('/api/search', request);
      
      // Remove loading message and add response
      const messagesWithoutLoading = [...chatMessages, userMessage].filter(msg => msg.id !== loadingMessage.id);
      
      if (response.data.success) {
        const assistantMessage: ChatMessage = {
          id: (Date.now() + 2).toString(),
          type: 'assistant',
          content: response.data.answer || 'No answer provided',
          timestamp: new Date(),
          queryType: 'qa'
        };
        onChatMessagesChange([...messagesWithoutLoading, assistantMessage]);
      } else {
        const errorMessage: ChatMessage = {
          id: (Date.now() + 2).toString(),
          type: 'assistant',
          content: `Error: ${response.data.error || 'Unknown error occurred'}`,
          timestamp: new Date(),
          queryType: 'qa'
        };
        onChatMessagesChange([...messagesWithoutLoading, errorMessage]);
      }
    } catch (err) {
      console.error('Error in chat query:', err);
      const errorMessage = axios.isAxiosError(err)
        ? err.response?.data?.detail || err.response?.data?.error || 'Error executing query'
        : 'An unknown error occurred';
      
      // Remove loading message and add error
      const messagesWithoutLoading = [...chatMessages, userMessage].filter(msg => msg.id !== loadingMessage.id);
      const errorMsg: ChatMessage = {
        id: (Date.now() + 2).toString(),
        type: 'assistant',
        content: `Error: ${errorMessage}`,
        timestamp: new Date(),
        queryType: 'qa'
      };
      onChatMessagesChange([...messagesWithoutLoading, errorMsg]);
    } finally {
      onIsQueryingChange(false);
    }
  };

  const clearChatHistory = () => {
    onChatMessagesChange([]);
  };

  return (
    <Box sx={{ 
      p: 3, 
      height: 'calc(100vh - 230px)', // Increased offset to prevent QHD scrollbars
      display: 'flex', 
      flexDirection: 'column', 
      overflow: 'hidden' 
    }}>
      {/* Removed header to save space - Clear History button moved to input area */}

      {/* Chat Messages */}
      <Paper 
        ref={chatContainerRef}
        sx={{ 
          flex: 1, // Take remaining space after header and input
          p: 2, 
          mb: 2, 
          overflowY: 'auto',
          bgcolor: isDarkMode ? '#2d2d2d' : '#f8f9fa',
          minHeight: '200px' // Reduced minimum height to prevent empty scrollbars
        }}
      >
        {chatMessages.length === 0 ? (
          <Box sx={{ 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center', 
            justifyContent: 'center', 
            height: '100%',
            color: currentTheme.palette.text.secondary
          }}>
            <img 
              src={agentIcon} 
              alt="Assistant" 
              style={{ 
                width: 48, 
                height: 48, 
                opacity: 0.5, 
                marginBottom: 16,
                backgroundColor: 'transparent',
                borderRadius: '50%'
              }} 
            />
            <Typography variant="h6" gutterBottom sx={{ color: currentTheme.palette.text.primary, fontWeight: 600 }}>
              Welcome to Flexible GraphRAG Chat
            </Typography>
            <Typography variant="body2" textAlign="center" sx={{ color: currentTheme.palette.text.secondary }}>
              Ask questions about your documents and get conversational answers.
              <br />
              The AI will provide detailed responses based on your processed documents.
            </Typography>
          </Box>
        ) : (
          <List sx={{ p: 0 }}>
            {chatMessages.map((message, index) => (
              <React.Fragment key={message.id}>
                <ListItem 
                  sx={{ 
                    display: 'flex', 
                    flexDirection: message.type === 'user' ? 'row-reverse' : 'row',
                    alignItems: 'flex-start',
                    px: 1,
                    py: 1
                  }}
                >
                  <Avatar 
                    sx={{ 
                      bgcolor: message.type === 'user' ? currentTheme.palette.primary.main : currentTheme.palette.success.main,
                      mx: 1,
                      width: 32,
                      height: 32
                    }}
                  >
                    {message.type === 'user' ? (
                      <PersonIcon />
                    ) : (
                      <img 
                        src={agentIcon} 
                        alt="Assistant" 
                        style={{ 
                          width: 28, 
                          height: 28, 
                          backgroundColor: 'transparent',
                          borderRadius: '50%'
                        }}
                      />
                    )}
                  </Avatar>
                  
                  <Box sx={{ 
                    maxWidth: message.type === 'user' ? '70%' : '80%',
                    bgcolor: message.type === 'user' ? currentTheme.palette.primary.light : currentTheme.palette.background.paper,
                    borderRadius: 2,
                    p: 2,
                    color: currentTheme.palette.text.primary
                  }}>
                    {message.isLoading ? (
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <CircularProgress size={16} />
                        <Typography variant="body2" color="text.secondary">
                          Thinking...
                        </Typography>
                      </Box>
                    ) : (
                      <>
                        <Typography variant="body1" sx={{ mb: 1 }}>
                          {message.content}
                        </Typography>
                        
                        <Typography variant="caption" sx={{ display: 'block', mt: 1, color: currentTheme.palette.text.secondary, fontWeight: 500 }}>
                          {message.timestamp.toLocaleTimeString()}
                        </Typography>
                      </>
                    )}
                  </Box>
                </ListItem>
                {index < chatMessages.length - 1 && <Divider sx={{ my: 1 }} />}
              </React.Fragment>
            ))}
          </List>
        )}
      </Paper>

      {/* Input Area */}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <TextField
          fullWidth
          multiline
          maxRows={3}
          value={chatInput}
          onChange={(e) => onChatInputChange(e.target.value)}
          onKeyPress={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleChatSubmit();
            }
          }}
          placeholder="Ask a question and press Enter or click arrow, Shift+Enter for a new line"
          variant="outlined"
          size="small"
          disabled={isQuerying}
          sx={{ 
            '& .MuiOutlinedInput-root': {
              borderRadius: 2,
              backgroundColor: isDarkMode ? currentTheme.palette.background.paper : '#f5f5f5',
              '& fieldset': {
                border: isDarkMode ? 'none' : '1px solid #e0e0e0',
              },
              '&:hover fieldset': {
                border: isDarkMode ? 'none' : '1px solid #1976d2',
              },
              '&.Mui-focused fieldset': {
                border: isDarkMode ? 'none' : '2px solid #1976d2',
              }
            }
          }}
        />
        <IconButton
          color="primary"
          onClick={handleChatSubmit}
          disabled={!chatInput.trim() || isQuerying}
          sx={{ 
            bgcolor: 'primary.main',
            color: 'white',
            '&:hover': { bgcolor: 'primary.dark' },
            '&:disabled': { 
              bgcolor: 'primary.main',
              color: 'white',
              opacity: 0.4
            },
            width: 48,
            height: 48
          }}
        >
          {isQuerying ? <CircularProgress size={20} color="inherit" /> : <SendIcon />}
        </IconButton>
        
        <Button
          variant="outlined"
          size="small"
          onClick={clearChatHistory}
          disabled={chatMessages.length === 0}
          sx={{ ml: 1 }}
        >
          Clear History
        </Button>
      </Box>
    </Box>
  );
};
