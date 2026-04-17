# Setup Overview

There are three deployment scenarios:

| Scenario | Description | Best for |
|---|---|---|
| **A — Hybrid** | Databases in Docker, backend + UI standalone | Development, local testing |
| **B — Full Docker** | Everything in Docker | Production, shared deployments |
| **C — Fully Standalone** | Everything installed directly | Advanced / CI/CD |

See [Docker Deployment](DOCKER-DEPLOYMENT.md) for full instructions on Scenarios A and B.

## Quick Steps (Scenario A — Hybrid)

1. **Start databases** — `docker compose -f docker/docker-compose.yml up -d`
2. **Install backend** — `uv pip install flexible-graphrag`
3. **Configure** — copy `env-sample.txt` to `.env`, set your LLM API key
4. **Start backend** — `flexible-graphrag`
5. **Start a frontend** — `cd frontend-react && npm run dev`
