import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Standalone development configuration
const API_BASE_URL = '/api'
const NODE_ENV = 'development'
const CMIS_BASE_URL = process.env.VITE_CMIS_BASE_URL || 'http://localhost:8080'  // Default for standalone
const ALFRESCO_BASE_URL = process.env.VITE_ALFRESCO_BASE_URL || 'http://localhost:8080'  // Default for standalone
const NUXEO_BASE_URL = process.env.VITE_NUXEO_BASE_URL || 'http://localhost:8081/nuxeo'  // Default for standalone
// The backend the dev server's /api proxy goes to (e.g. a second backend on port 8001)
const API_PROXY_TARGET = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

// `vite build --mode desktop` (npm run build:desktop): the desktop app's build
// (flexible-graphrag-ui/desktop, `npm run dev:vue` / `build:vue`), served by Tauri from
// dist-desktop with relative asset paths
export default defineConfig(({ mode }) => ({
  plugins: [vue()],
  ...(mode === 'desktop' ? { base: './', build: { outDir: 'dist-desktop', emptyOutDir: true } } : {}),
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 3000,
    strictPort: true,
    proxy: {
      '^/api': {
        target: API_PROXY_TARGET,
        changeOrigin: true,
        secure: false,
        // Don't rewrite the path, keep /api in the URL
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, _res) => {
            console.log('Proxy error:', err);
          });
          proxy.on('proxyReq', (proxyReq, req, _res) => {
            console.log('Sending request to backend:', req.method, req.url);
          });
          proxy.on('proxyRes', (proxyRes, req, _res) => {
            console.log('Received response from backend:', req.url, 'Status:', proxyRes.statusCode);
          });
        }
      }
    }
  },
  // Define environment variables that will be available in the Vue app
  define: {
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(API_BASE_URL),
    'import.meta.env.VITE_CMIS_BASE_URL': JSON.stringify(CMIS_BASE_URL),
    'import.meta.env.VITE_ALFRESCO_BASE_URL': JSON.stringify(ALFRESCO_BASE_URL),
    'import.meta.env.VITE_NUXEO_BASE_URL': JSON.stringify(NUXEO_BASE_URL),
    'process.env.NODE_ENV': JSON.stringify(NODE_ENV)
  }
}))