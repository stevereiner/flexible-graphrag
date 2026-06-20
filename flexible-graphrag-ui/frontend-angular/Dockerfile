# Stage 1 — build
FROM node:24-alpine AS builder
WORKDIR /app

# ts-node is needed to run generate-env-config.ts
RUN npm install -g ts-node

COPY package*.json ./
RUN npm ci

COPY . .

# Generate src/assets/env-config.json with Docker networking defaults before build.
# The Angular app fetches this file at runtime, allowing URL overrides per deployment.
RUN DOCKER_MODE=true npx ts-node --esm generate-env-config.ts

# Production build — base href baked in at build time, consistent with React/Vue approach.
# Angular 17+ outputs to dist/<project>/browser/
RUN npx ng build --configuration=production --base-href /ui/angular/

# Stage 2 — serve static files with nginx
FROM nginx:stable-alpine

# Place built files under /ui/angular/ so nginx serves them at that path,
# consistent with React (/ui/react/) and Vue (/ui/vue/).
# Uses legacy @angular-devkit/build-angular:browser builder → output is at
# dist/flexible-graphrag-ui/ directly (no browser/ subdirectory).
COPY --from=builder /app/dist/flexible-graphrag-ui /usr/share/nginx/html/ui/angular

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 4200

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:4200/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
