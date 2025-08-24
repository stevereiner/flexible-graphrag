import { Theme } from '@mui/material/styles';

export interface AppTheme extends Theme {}

// Theme context type for components
export interface ThemeContextType {
  isDarkMode: boolean;
  currentTheme: AppTheme;
  toggleTheme: () => void;
}
