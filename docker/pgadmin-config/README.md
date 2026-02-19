# pgAdmin Configuration

This directory contains pgAdmin configuration files that are automatically loaded when the pgAdmin container starts.

## Auto-Registered Servers

The `servers.json` file automatically registers the PostgreSQL server in pgAdmin, so you don't need to manually add it each time.

### Server Details:
- **Name**: Flexible GraphRAG PostgreSQL
- **Host**: `postgres-pgvector` (Docker service name)
- **Port**: 5432 (internal Docker port)
- **Username**: postgres
- **Password**: password (you'll be prompted on first connection)

## Accessing pgAdmin

1. Open: http://localhost:5050
2. Login:
   - **Email**: admin@flexible-graphrag.com
   - **Password**: admin
3. The PostgreSQL server should appear automatically in the left sidebar
4. Click on it and enter the password: `password`

## Databases Available:
- **flexible_graphrag** - Vector store with pgvector extension
- **flexible_graphrag_incremental** - State management for incremental updates

## Persistence

pgAdmin settings are stored in the `pgadmin_data` Docker volume, so your configurations and saved queries persist across container restarts.
