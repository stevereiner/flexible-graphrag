import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// Docker-specific configuration
const API_BASE_URL = '/api'
const NODE_ENV = 'development'
const CMIS_BASE_URL = 'http://host.docker.internal:8080'  // Docker networking
const ALFRESCO_BASE_URL = 'http://host.docker.internal:8080'  // Docker networking

export default defineConfig({
  plugins: [vue()],
  base: '/ui/vue/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    host: '0.0.0.0',
    strictPort: true,
    // Add proxy for direct access (port 5173)
    proxy: {
      '/api': {
        target: 'http://flexible-graphrag-backend:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  define: {
    'import.meta.env.VITE_API_BASE_URL': JSON.stringify(API_BASE_URL),
    'import.meta.env.VITE_CMIS_BASE_URL': JSON.stringify(CMIS_BASE_URL),
    'import.meta.env.VITE_ALFRESCO_BASE_URL': JSON.stringify(ALFRESCO_BASE_URL),
    'process.env.NODE_ENV': JSON.stringify(NODE_ENV)
  }
})
