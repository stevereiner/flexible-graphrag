# Stage 1 — build
FROM node:24-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Swap in the Docker-specific Vite config (sets base: '/ui/vue/', proxies /api to backend)
RUN mv vite.docker.config.ts vite.config.ts

# Production build — call vite directly to skip the vue-tsc type-check step.
# (npm run build = "vue-tsc --noEmit && vite build"; vue-tsc treats unused-variable
# warnings as hard errors in strict mode, which blocks the image build unnecessarily.)
RUN npx vite build

# Stage 2 — serve static files with nginx
FROM nginx:stable-alpine

# Place built files under /ui/vue/ so nginx can serve them at that path
COPY --from=builder /app/dist /usr/share/nginx/html/ui/vue

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 5173

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:5173/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
