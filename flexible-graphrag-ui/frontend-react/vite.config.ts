import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Node's process.env (vite.config.ts runs in Node; @types/node isn't a dependency)
declare const process: { env: Record<string, string | undefined> };

// Standalone development configuration
const CMIS_BASE_URL = process.env.VITE_CMIS_BASE_URL || 'http://localhost:8080';
const ALFRESCO_BASE_URL = process.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080';
const NUXEO_BASE_URL = process.env.VITE_NUXEO_BASE_URL || 'http://localhost:8081/nuxeo';
// The backend the dev server's /api proxy goes to (e.g. a second backend on port 8001)
const API_PROXY_TARGET = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000';

// `vite build --mode desktop` (npm run build:desktop): the desktop app's build
// (flexible-graphrag-ui/desktop), served by Tauri from dist-desktop with relative asset paths
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  ...(mode === 'desktop' ? { base: './', build: { outDir: 'dist-desktop', emptyOutDir: true } } : {}),
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: API_PROXY_TARGET,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  define: {
    'import.meta.env.VITE_CMIS_BASE_URL': JSON.stringify(CMIS_BASE_URL),
    'import.meta.env.VITE_ALFRESCO_BASE_URL': JSON.stringify(ALFRESCO_BASE_URL),
    'import.meta.env.VITE_NUXEO_BASE_URL': JSON.stringify(NUXEO_BASE_URL),
  }
}));
