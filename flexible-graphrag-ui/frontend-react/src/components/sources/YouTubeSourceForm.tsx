import React, { useEffect, useMemo } from 'react';
import { TextField } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface YouTubeSourceFormProps extends BaseSourceFormProps {
  url: string;
  onUrlChange: (url: string) => void;
}

export const YouTubeSourceForm: React.FC<YouTubeSourceFormProps> = ({
  currentTheme,
  url,
  onUrlChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const isValid = useMemo(() => {
    return url.trim() !== '' && (url.includes('youtube.com') || url.includes('youtu.be'));
  }, [url]);

  const config = useMemo(() => ({
    url: url,
    chunk_size_seconds: 60  // Default 1 minute
  }), [url]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="YouTube Video"
      description="Extract transcript from YouTube videos"
    >
      <TextField
        fullWidth
        label="YouTube URL"
        variant="outlined"
        value={url}
        onChange={(e) => onUrlChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        helperText="Enter a YouTube video URL to extract transcript"
      />
    </BaseSourceForm>
  );
};
