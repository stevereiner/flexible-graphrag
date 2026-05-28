import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Standalone development configuration
const CMIS_BASE_URL = process.env.VITE_CMIS_BASE_URL || 'http://localhost:8080';
const ALFRESCO_BASE_URL = process.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  define: {
    'import.meta.env.VITE_CMIS_BASE_URL': JSON.stringify(CMIS_BASE_URL),
    'import.meta.env.VITE_ALFRESCO_BASE_URL': JSON.stringify(ALFRESCO_BASE_URL),
  }
});
