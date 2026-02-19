# PostgreSQL Initialization Scripts

This directory contains initialization scripts that run automatically when the PostgreSQL container is first created.

## Three Databases

The PostgreSQL container hosts 3 databases:
1. **postgres** - System database (PostgreSQL default)
2. **flexible_graphrag** - Main vector database (WITH pgvector extension)
3. **flexible_graphrag_incremental** - State management (NO pgvector - just regular tables)

See `DATABASE-ARCHITECTURE.md` for detailed explanation.

## Scripts (in execution order)

1. **01-init-pgvector.sql** - Initializes pgvector extension in `flexible_graphrag` database ONLY
2. **02-init-incremental.sql** - Creates the `flexible_graphrag_incremental` database
3. **03-init-incremental-schema.sh** - Applies schema to incremental database (NO pgvector needed)

## When Scripts Run

These scripts **only run once** when the PostgreSQL container is first created (i.e., when the volume is empty). They will NOT run if:
- The container is restarted
- The container is stopped and started again
- The database volume already exists

## Manual Database Creation (if needed)

If you already have a running PostgreSQL container and need to create the incremental database manually, you can use the provided scripts:

### Windows
```cmd
cd docker\postgres-init
manual-setup-incremental.bat
```

### Linux/Mac
```bash
cd docker/postgres-init
./manual-setup-incremental.sh
```

### Or run commands manually:
```bash
# 1. Create the database
docker exec -i flexible-graphrag-postgres psql -U postgres -c "CREATE DATABASE flexible_graphrag_incremental;"

# 2. Apply the schema
cd /path/to/flexible-graphrag
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental < flexible-graphrag/incremental_updates/schema.sql
```

## Rebuilding from Scratch

To force the init scripts to run again:

```bash
# WARNING: This will delete all PostgreSQL data!

cd docker
docker-compose -f docker-compose.yaml -p flexible-graphrag down -v  # Remove volumes
docker-compose -f docker-compose.yaml -p flexible-graphrag up -d postgres-pgvector  # Recreate with fresh volumes
```

## Verifying Setup

Check if databases exist:
```bash
docker exec -i flexible-graphrag-postgres psql -U postgres -c "\l"
```

Check tables in incremental database:
```bash
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental -c "\dt"
```

## Database Configuration

The incremental updates system expects this connection string in your `.env` file:

```env
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental
```

For Docker deployment (app running in container):
```env
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@postgres-pgvector:5432/flexible_graphrag_incremental
```
