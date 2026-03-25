#!/bin/bash
# Manual setup script for flexible_graphrag_incremental database
# Run this from Linux/Mac if you need to manually create the incremental database
# (Not for Docker init - that uses 03-init-incremental-schema.sh automatically)

echo "========================================"
echo "Incremental Database - Manual Setup"
echo "========================================"
echo ""

# Check if Docker is running
if ! docker ps > /dev/null 2>&1; then
    echo "ERROR: Docker is not running or not in PATH"
    echo "Please start Docker and try again."
    exit 1
fi

# Check if PostgreSQL container is running
if ! docker ps --filter "name=flexible-graphrag-postgres" --format "{{.Names}}" | grep -q "flexible-graphrag-postgres"; then
    echo "ERROR: PostgreSQL container is not running"
    echo ""
    echo "Please start the container with:"
    echo "  cd docker"
    echo "  docker-compose -f docker-compose.yaml -p flexible-graphrag up -d postgres-pgvector"
    echo ""
    exit 1
fi

echo "PostgreSQL container found. Proceeding..."
echo ""

# Step 1: Create the database
echo "Step 1: Creating database flexible_graphrag_incremental..."
docker exec -i flexible-graphrag-postgres psql -U postgres -c "CREATE DATABASE flexible_graphrag_incremental;"

if [ $? -eq 0 ]; then
    echo "  SUCCESS: Database created"
else
    echo "  Note: Database may already exist (this is OK)"
fi
echo ""

# Step 2: Apply the schema
echo "Step 2: Applying schema from incremental_updates/schema.sql..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental < "$SCRIPT_DIR/../../flexible-graphrag/incremental_updates/schema.sql"

if [ $? -eq 0 ]; then
    echo "  SUCCESS: Schema applied"
else
    echo "  ERROR: Failed to apply schema"
    exit 1
fi
echo ""

# Step 3: Verify
echo "Step 3: Verifying tables..."
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental -c "\dt"
echo ""

echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "Database: flexible_graphrag_incremental"
echo "Tables: datasource_config, document_state"
echo ""
echo "Connection string for .env file:"
echo "POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental"
echo ""
