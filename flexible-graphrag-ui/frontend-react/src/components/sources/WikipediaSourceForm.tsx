import React, { useEffect, useMemo } from 'react';
import { TextField } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface WikipediaSourceFormProps extends BaseSourceFormProps {
  url: string;
  onUrlChange: (url: string) => void;
}

export const WikipediaSourceForm: React.FC<WikipediaSourceFormProps> = ({
  currentTheme: _currentTheme, // Renamed to avoid unused variable warning
  url,
  onUrlChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const isValid = useMemo(() => {
    return url.trim() !== '' && url.includes('wikipedia.org');
  }, [url]);

  const config = useMemo(() => {
    // Extract query from Wikipedia URL
    let query = '';
    if (url.includes('wikipedia.org/wiki/')) {
      query = url.split('/wiki/')[1] || '';
      query = decodeURIComponent(query);
      // Only replace underscores with spaces if the title doesn't contain hyphens
      // This preserves titles like "Nasdaq-100" while still handling "Albert_Einstein"
      if (!query.includes('-')) {
        query = query.replace(/_/g, ' ');
      }
    }
    return {
      query: query,
      language: 'en',
      max_docs: 1
    };
  }, [url]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Wikipedia Article"
      description="Extract content from Wikipedia articles"
    >
      <TextField
        fullWidth
        label="Wikipedia URL"
        variant="outlined"
        value={url}
        onChange={(e) => onUrlChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="https://en.wikipedia.org/wiki/Artificial_intelligence"
        helperText="Enter a Wikipedia article URL"
      />
    </BaseSourceForm>
  );
};
