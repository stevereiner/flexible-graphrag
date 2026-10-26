import React, { useState, useEffect } from 'react';
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
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { QueryRequest, ApiResponse, SourceDocument } from '../types/api';
import { SourceDocs, sourceTypeLabel, storeLabel } from './SourceDocs';
import { SourcePicker } from '../auth/SourcePicker';

const MARKDOWN_SX = {
  '& h1': { fontSize: '1.3rem', fontWeight: 600, mt: 1.5, mb: 0.5 },
  '& h2': { fontSize: '1.15rem', fontWeight: 600, mt: 1.5, mb: 0.5 },
  '& h3': { fontSize: '1.05rem', fontWeight: 600, mt: 1.25, mb: 0.5 },
  '& p': { my: 0.75, lineHeight: 1.6 },
  '& ul, & ol': { my: 0.5, pl: 3 },
  '& li': { mb: 0.25 },
  '& code': { bgcolor: 'rgba(0,0,0,0.06)', px: 0.5, py: 0.1, borderRadius: 0.5, fontSize: '0.85em', fontFamily: 'monospace' },
  '& pre': { bgcolor: 'rgba(0,0,0,0.06)', p: 1.5, borderRadius: 1, overflowX: 'auto' },
  '& pre code': { bgcolor: 'transparent', p: 0 },
  '& table': { borderCollapse: 'collapse', width: '100%', my: 1 },
  '& th, & td': { border: '1px solid rgba(0,0,0,0.15)', p: 0.75, fontSize: '0.875rem', textAlign: 'left' as const },
  '& th': { bgcolor: 'rgba(0,0,0,0.04)', fontWeight: 600 },
  '& a': { color: 'primary.main' },
  '& blockquote': { borderLeft: '3px solid rgba(0,0,0,0.15)', pl: 1.5, ml: 0, color: 'text.secondary' },
};

const IMAGE_PLACEHOLDER = /<!--\s*image\s*-->/gi;

const Thumb: React.FC<{ src: string }> = ({ src }) => (
  <a href={src} target="_blank" rel="noopener noreferrer">
    <img src={src} alt="" style={{ maxHeight: 160, maxWidth: 260, borderRadius: 4, border: '1px solid rgba(0,0,0,0.12)', display: 'block', margin: '8px 0' }} />
  </a>
);

/** Local POC viewer: docling collapses each embedded image to a generic "<!-- image -->"
    placeholder in the chunk text, with no file reference kept. This fetches every image
    sitting next to the source document and drops them inline, in order, at each placeholder
    the text had -- an approximation (first image found = first placeholder in the chunk),
    not a true per-image match. Leftover images beyond the placeholder count are appended
    at the end instead of guessed into a wrong spot. */
const ContentWithImages: React.FC<{ content: string; path?: string }> = ({ content, path }) => {
  const [images, setImages] = useState<string[]>([]);
  useEffect(() => {
    if (!path) { setImages([]); return; }
    let cancelled = false;
    axios.get('/api/local-images', { params: { file_path: path } })
      .then((res) => { if (!cancelled) setImages(res.data?.images || []); })
      .catch(() => { if (!cancelled) setImages([]); });
    return () => { cancelled = true; };
  }, [path]);

  const segments = content.split(IMAGE_PLACEHOLDER);
  const placeholderCount = segments.length - 1;
  const leftoverImages = images.slice(placeholderCount);

  return (
    <>
      {segments.map((segment, i) => (
        <React.Fragment key={i}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{segment}</ReactMarkdown>
          {i < placeholderCount && images[i] && <Thumb src={images[i]} />}
        </React.Fragment>
      ))}
      {leftoverImages.length > 0 && (
        <Box sx={{ mt: 1, display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {leftoverImages.map((src) => <Thumb key={src} src={src} />)}
        </Box>
      )}
    </>
  );
};

interface SearchTabProps {
  currentTheme: Theme;
  activeTab: string;
  question: string;
  searchResults: any[];
  qaAnswer: string;
  qaSources: SourceDocument[];
  hasSearched: boolean;
  lastSearchQuery: string;
  isQuerying: boolean;
  onActiveTabChange: (activeTab: string) => void;
  onQuestionChange: (question: string) => void;
  onSearchResultsChange: (results: any[]) => void;
  onQaAnswerChange: (answer: string) => void;
  onQaSourcesChange: (sources: SourceDocument[]) => void;
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
  qaSources,
  hasSearched,
  lastSearchQuery,
  isQuerying,
  onActiveTabChange,
  onQuestionChange,
  onSearchResultsChange,
  onQaAnswerChange,
  onQaSourcesChange,
  onHasSearchedChange,
  onLastSearchQueryChange,
  onIsQueryingChange,
}) => {
  // Local state (only for UI-specific state that doesn't need persistence)
  // Search state now comes from props for persistence
  const [error, setError] = useState<string>(''); // Error doesn't need persistence
  // Why a search found nothing, when the backend says (e.g. the matches are in Alfresco and
  // the user continued without signing in)
  const [emptyMessage, setEmptyMessage] = useState<string>('');

  const handleSearch = async (): Promise<void> => {
    if (!question.trim() || isQuerying) return;
    
    try {
      onIsQueryingChange(true);
      setError('');
      setEmptyMessage('');
      onSearchResultsChange([]);
      onQaAnswerChange('');
      onQaSourcesChange([]);
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
        setEmptyMessage(response.data.message || '');
        if (activeTab === 'search' && response.data.results) {
          onSearchResultsChange(response.data.results);
        } else if (activeTab === 'qa' && response.data.answer) {
          onQaAnswerChange(response.data.answer);
          onQaSourcesChange(response.data.sources || []);
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
    onQaSourcesChange([]);
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

        <SourcePicker />

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
                    <strong>Source:</strong>{' '}
                    {result.documents?.length ? (
                      <>
                        <SourceDocs docs={result.documents} />
                        {sourceTypeLabel(result.documents) && ` | ${sourceTypeLabel(result.documents)}`}
                        {storeLabel(result.source) && ` | ${storeLabel(result.source)}`}
                      </>
                    ) : (result.file_name || result.metadata?.source || result.source || 'Unknown')} | 
                    <strong> Score:</strong> {result.score?.toFixed(3) || 'N/A'}
                  </Typography>
                  <Box sx={MARKDOWN_SX}>
                    <ContentWithImages
                      content={result.text || result.content || 'No content available'}
                      path={result.documents?.[0]?.path}
                    />
                  </Box>
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
                {emptyMessage || `No results found for "${lastSearchQuery}". Try different search terms.`}
              </Typography>
            </Paper>
          )}
        </TabPanel>
        
        <TabPanel value="qa" sx={{ p: 0 }}>
          {qaAnswer && (
            <Paper sx={{ p: 2, mt: 2, bgcolor: 'background.paper' }} elevation={1}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                <strong>Answer:</strong>
              </Typography>
              <Box sx={MARKDOWN_SX}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{qaAnswer}</ReactMarkdown>
              </Box>
              {qaSources.length > 0 && (
                <Typography variant="body2" color="text.secondary" component="div" sx={{ mt: 1.5 }}>
                  <SourceDocs docs={qaSources} label="Sources:" />
                </Typography>
              )}
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
