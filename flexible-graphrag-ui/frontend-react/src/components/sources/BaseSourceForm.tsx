import React from 'react';
import { Box, Typography } from '@mui/material';
import { Theme } from '@mui/material/styles';

export interface BaseSourceFormProps {
  currentTheme: Theme;
  onConfigurationChange: (config: any) => void;
  onValidationChange: (isValid: boolean) => void;
}

export interface BaseSourceFormConfig {
  isValid: boolean;
  config: any;
}

export const BaseSourceForm: React.FC<{
  title: string;
  description?: string;
  children: React.ReactNode;
}> = ({ title, description, children }) => {
  return (
    <Box>
      <Typography variant="h6" gutterBottom sx={{ mb: 1 }}>
        {title}
      </Typography>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {description}
        </Typography>
      )}
      {children}
    </Box>
  );
};
