import React, { useEffect, useMemo } from 'react';
import { TextField } from '@mui/material';
import { BaseSourceForm, BaseSourceFormProps } from './BaseSourceForm';

interface WebSourceFormProps extends BaseSourceFormProps {
  url: string;
  onUrlChange: (url: string) => void;
}

export const WebSourceForm: React.FC<WebSourceFormProps> = ({
  currentTheme,
  url,
  onUrlChange,
  onConfigurationChange,
  onValidationChange,
}) => {
  const isValid = useMemo(() => {
    return url.trim() !== '' && url.startsWith('http');
  }, [url]);

  const config = useMemo(() => ({
    url: url
  }), [url]);

  useEffect(() => {
    onValidationChange(isValid);
    onConfigurationChange(config);
  }, [isValid, config, onValidationChange, onConfigurationChange]);

  return (
    <BaseSourceForm
      title="Web Page"
      description="Extract content from any web page"
    >
      <TextField
        fullWidth
        label="Website URL"
        variant="outlined"
        value={url}
        onChange={(e) => onUrlChange(e.target.value)}
        size="small"
        sx={{ mb: 2 }}
        placeholder="https://example.com"
        helperText="Enter a valid website URL to extract content from"
      />
    </BaseSourceForm>
  );
};
