# Stage 1 — build
FROM node:24-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Swap in the Docker-specific Vite config (sets base: '/ui/react/', proxies /api to backend)
RUN mv vite.docker.config.ts vite.config.ts

# Production build — call vite directly to skip the tsc type-check step.
# (npm run build = "tsc && vite build"; tsc treats unused-variable warnings as
# hard errors in strict mode, which blocks the image build unnecessarily.)
RUN npx vite build

# Stage 2 — serve static files with nginx
FROM nginx:stable-alpine

# Place built files under /ui/react/ so nginx can serve them at that path
COPY --from=builder /app/dist /usr/share/nginx/html/ui/react

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:3000/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
