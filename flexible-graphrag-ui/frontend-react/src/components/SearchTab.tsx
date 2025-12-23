import React, { useState } from 'react';
import {
  Box,
  Typography,
  Button,
  TextField,
  Paper,
  CircularProgress,
  Tabs,
  Tab,
} from '@mui/material';
import { TabContext, TabPanel } from '@mui/lab';
import { Theme } from '@mui/material/styles';
import axios from 'axios';
import { QueryRequest, ApiResponse } from '../types/api';

interface SearchTabProps {
  currentTheme: Theme;
  activeTab: string;
  question: string;
  searchResults: any[];
  qaAnswer: string;
  hasSearched: boolean;
  lastSearchQuery: string;
  isQuerying: boolean;
  onActiveTabChange: (activeTab: string) => void;
  onQuestionChange: (question: string) => void;
  onSearchResultsChange: (results: any[]) => void;
  onQaAnswerChange: (answer: string) => void;
  onHasSearchedChange: (hasSearched: boolean) => void;
  onLastSearchQueryChange: (query: string) => void;
  onIsQueryingChange: (isQuerying: boolean) => void;
}

export const SearchTab: React.FC<SearchTabProps> = ({ 
  currentTheme,
  activeTab,
  question,
  searchResults,
  qaAnswer,
  hasSearched,
  lastSearchQuery,
  isQuerying,
  onActiveTabChange,
  onQuestionChange,
  onSearchResultsChange,
  onQaAnswerChange,
  onHasSearchedChange,
  onLastSearchQueryChange,
  onIsQueryingChange,
}) => {
  // Local state (only for UI-specific state that doesn't need persistence)
  // Search state now comes from props for persistence
  const [error, setError] = useState<string>(''); // Error doesn't need persistence

  const handleSearch = async (): Promise<void> => {
    if (!question.trim() || isQuerying) return;
    
    try {
      onIsQueryingChange(true);
      setError('');
      onSearchResultsChange([]);
      onQaAnswerChange('');
      onLastSearchQueryChange(question);
      
      const queryType = activeTab === 'search' ? 'hybrid' : 'qa';
      const request: QueryRequest = {
        query: question,
        query_type: queryType,
        top_k: 10
      };
      
      const response = await axios.post<ApiResponse>('/api/search', request);
      
      if (response.data.success) {
        onHasSearchedChange(true);
        if (activeTab === 'search' && response.data.results) {
          onSearchResultsChange(response.data.results);
        } else if (activeTab === 'qa' && response.data.answer) {
          onQaAnswerChange(response.data.answer);
        }
      } else {
        onHasSearchedChange(true);
        setError(response.data.error || 'Error executing query');
      }
    } catch (err) {
      console.error('Error querying:', err);
      const errorMessage = axios.isAxiosError(err)
        ? err.response?.data?.detail || err.response?.data?.error || 'Error executing query'
        : 'An unknown error occurred';
      setError(errorMessage);
      onHasSearchedChange(true);
    } finally {
      onIsQueryingChange(false);
    }
  };

  const handleTabChange = (_: any, newValue: string) => {
    onActiveTabChange(newValue);
    onSearchResultsChange([]);
    onQaAnswerChange('');
    setError('');
    onHasSearchedChange(false);
    onLastSearchQueryChange('');
  };

  return (
    <Box sx={{ p: 3 }}>
      <TabContext value={activeTab}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
          <Tabs value={activeTab} onChange={handleTabChange}>
            <Tab label="Hybrid Search" value="search" />
            <Tab label="AI Query" value="qa" />
          </Tabs>
        </Box>
        
        <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
          <TextField
            fullWidth
            label={activeTab === 'search' ? 'Search terms' : 'Ask a question'}
            variant="outlined"
            value={question}
            onChange={(e) => onQuestionChange(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            size="small"
            placeholder={activeTab === 'search' 
              ? 'e.g., machine learning algorithms' 
              : 'e.g., What are the key findings?'
            }
            sx={{
              '& .MuiOutlinedInput-root': {
                backgroundColor: currentTheme.palette.background.paper,
                '& fieldset': {
                  borderColor: currentTheme.palette.divider,
                },
                '&:hover fieldset': {
                  borderColor: currentTheme.palette.primary.main,
                },
                '&.Mui-focused fieldset': {
                  borderColor: currentTheme.palette.primary.main,
                }
              }
            }}
          />
          <Button
            variant="contained"
            color="primary"
            onClick={handleSearch}
            disabled={isQuerying || !question.trim()}
            sx={{ minWidth: 150 }}
          >
            {isQuerying ? <CircularProgress size={24} /> : (activeTab === 'search' ? 'Search' : 'Ask')}
          </Button>
        </Box>
        
        <TabPanel value="search" sx={{ p: 0 }}>
          {searchResults.length > 0 && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="h6" gutterBottom>
                Search Results ({searchResults.length})
              </Typography>
              {searchResults.map((result, index) => (
                <Paper key={index} sx={{ p: 2, mb: 2 }} elevation={1}>
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    <strong>Source:</strong> {result.metadata?.source || 'Unknown'} | 
                    <strong> Score:</strong> {result.score?.toFixed(3) || 'N/A'}
                  </Typography>
                  <Typography variant="body1">
                    {result.text || result.content || 'No content available'}
                  </Typography>
                </Paper>
              ))}
            </Box>
          )}
          {hasSearched && searchResults.length === 0 && !isQuerying && (
            <Paper sx={{ p: 3, mt: 2, textAlign: 'center' }} elevation={1}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                No results found
              </Typography>
              <Typography variant="body1" color="text.secondary">
                No results found for "{lastSearchQuery}". Try different search terms.
              </Typography>
            </Paper>
          )}
        </TabPanel>
        
        <TabPanel value="qa" sx={{ p: 0 }}>
          {qaAnswer && (
            <Paper sx={{ p: 2, mt: 2, bgcolor: 'background.paper' }} elevation={1}>
              <Typography variant="body1" component="div">
                <strong>Answer:</strong> {qaAnswer}
              </Typography>
            </Paper>
          )}
        </TabPanel>

        {error && (
          <Paper sx={{ p: 2, mt: 2, bgcolor: 'error.light' }} elevation={1}>
            <Typography variant="body1" color="error">
              <strong>Error:</strong> {error}
            </Typography>
          </Paper>
        )}
      </TabContext>
    </Box>
  );
};
