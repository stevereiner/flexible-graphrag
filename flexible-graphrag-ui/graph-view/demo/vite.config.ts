import { defineConfig } from 'vite';

// Demo page only (not part of the published package): npm run demo -> http://localhost:5180
export default defineConfig({
  root: __dirname,
  server: {
    port: 5180,
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
});
