# Frontend Setup

## Default URLs

| Frontend | URL |
|---|---|
| Backend API | http://localhost:8000 |
| React | http://localhost:5173 (`npm run dev`) |
| Angular | http://localhost:4200 (`npm start`) |
| Vue | http://localhost:3000 (`npm run dev`) |

## Standalone Installation

```bash
# React
cd flexible-graphrag-ui/frontend-react
npm install
npm run dev

# Angular
cd flexible-graphrag-ui/frontend-angular
npm install
npm start

# Vue
cd flexible-graphrag-ui/frontend-vue
npm install
npm run dev
```

## Docker Deployment

When using full Docker deployment, the frontends are served through the NGINX reverse proxy.
See [Docker Deployment](DOCKER-DEPLOYMENT.md) for full details.
