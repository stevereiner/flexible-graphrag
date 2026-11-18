// The dev server's /api proxy (ng serve). VITE_API_PROXY_TARGET picks another backend
// (e.g. a second backend on port 8001); the same variable as the React and Vue dev servers.
export default {
  '/api': {
    target: process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000',
    secure: false,
    changeOrigin: true,
    logLevel: 'debug',
  },
};
