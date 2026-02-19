# PostgreSQL Database Architecture

## Three Databases Explained

The PostgreSQL container hosts **3 databases**, each with a specific purpose:

### 1. `postgres` (System Database)
**Purpose**: PostgreSQL default/system database
**Created By**: PostgreSQL automatically
**Extensions**: None needed
**Tables**: System tables only
**Usage**: Connection default, admin operations
**Your Use**: Not directly used by flexible-graphrag

---

### 2. `flexible_graphrag` (Main Vector Database)
**Purpose**: Vector embeddings and pgvector operations
**Created By**: Docker environment variable `POSTGRES_DB=flexible_graphrag`
**Extensions**: ✅ **pgvector** (for vector similarity search)
**Tables**: 
- Vector embeddings (LlamaIndex creates these)
- Sample_vectors (demo/testing)
**Init Script**: `01-init-pgvector.sql`
**Usage**: Stores document embeddings for semantic search

**Why pgvector here?**
- Vector similarity operations require pgvector extension
- Stores high-dimensional embeddings (1536 dimensions)
- Enables efficient nearest neighbor search

---

### 3. `flexible_graphrag_incremental` (State Management)
**Purpose**: Incremental update state tracking
**Created By**: `02-init-incremental.sql`
**Extensions**: ❌ **No pgvector** (not needed - just regular tables)
**Tables**:
- `datasource_config` - Datasource configurations
- `document_state` - Document processing state
**Init Scripts**: 
- `02-init-incremental.sql` - Creates database
- `03-init-incremental-schema.sh` - Creates tables
**Usage**: Tracks which documents are synced, content hashes, timestamps

**Why NO pgvector?**
- Only stores metadata (text, numbers, timestamps)
- No vector embeddings or similarity operations
- Regular PostgreSQL tables are sufficient
- Keeps database lightweight and focused

---

## Database Comparison

| Feature | postgres | flexible_graphrag | flexible_graphrag_incremental |
|---------|----------|-------------------|-------------------------------|
| **Purpose** | System DB | Vector Storage | State Tracking |
| **pgvector** | ❌ No | ✅ **YES** | ❌ **NO** |
| **Vector Embeddings** | No | Yes | No |
| **State Tables** | No | No | Yes |
| **Size (typical)** | Small | Large | Small |
| **Your Use** | None | Vector Search | Sync State |

---

## Init Script Summary

### 01-init-pgvector.sql
- **Target**: `flexible_graphrag` database (POSTGRES_DB env var)
- **Action**: Installs pgvector extension
- **Creates**: Sample_vectors table (demo)
- **When**: On fresh container creation

### 02-init-incremental.sql
- **Target**: Creates new database `flexible_graphrag_incremental`
- **Action**: CREATE DATABASE statement
- **Creates**: Empty database
- **When**: On fresh container creation

### 03-init-incremental-schema.sh
- **Target**: `flexible_graphrag_incremental` database
- **Action**: Creates state management tables
- **Creates**: `datasource_config`, `document_state`
- **Note**: NO pgvector extension - not needed!
- **When**: On fresh container creation

---

## Why This Architecture?

### Separation of Concerns
1. **Vector Operations** → `flexible_graphrag`
   - Heavy I/O for embeddings
   - Requires special indexing (pgvector)
   - Large storage footprint

2. **State Management** → `flexible_graphrag_incremental`
   - Lightweight metadata only
   - Fast transactional updates
   - Small storage footprint

### Benefits
- ✅ **Isolation**: Vector crashes don't affect state tracking
- ✅ **Performance**: No vector overhead in state queries
- ✅ **Backup**: Can backup separately (state is critical!)
- ✅ **Scaling**: Can move to different servers if needed
- ✅ **Clarity**: Clear separation of data types

---

## Connection Strings

### For flexible-graphrag (main vector DB)
```env
# Development (external app)
postgresql://postgres:password@localhost:5433/flexible_graphrag

# Docker (app in container)
postgresql://postgres:password@postgres-pgvector:5432/flexible_graphrag
```

### For incremental (state management)
```env
# Development (external app)
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental

# Docker (app in container)
POSTGRES_INCREMENTAL_URL=postgresql://postgres:password@postgres-pgvector:5432/flexible_graphrag_incremental
```

---

## Verification Commands

### Check all databases
```bash
docker exec -i flexible-graphrag-postgres psql -U postgres -c "\l"
```

### Check pgvector extension (should be in flexible_graphrag ONLY)
```bash
# flexible_graphrag - should show pgvector
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag -c "\dx"

# flexible_graphrag_incremental - should NOT show pgvector
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental -c "\dx"
```

### Check tables
```bash
# Vector database tables
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag -c "\dt"

# State management tables
docker exec -i flexible-graphrag-postgres psql -U postgres -d flexible_graphrag_incremental -c "\dt"
```

---

## Common Questions

**Q: Why not use one database?**
A: Separation of concerns - vector operations are heavy, state is lightweight. Keeps things clean and performant.

**Q: Can I merge them?**
A: Yes technically, but not recommended. Defeats the purpose of separation.

**Q: Do I need pgvector in incremental DB?**
A: **NO!** The incremental DB only stores text/numbers/timestamps. No vector operations needed.

**Q: Which database do I backup first?**
A: `flexible_graphrag_incremental` - state is critical for sync consistency. Vector data can be regenerated.

**Q: Can they be on different servers?**
A: Yes! That's a benefit of this architecture. You could scale them independently.

---

## Summary

- 🗄️ **postgres**: System database (ignore)
- 📊 **flexible_graphrag**: Vector embeddings + pgvector extension
- 📋 **flexible_graphrag_incremental**: State tracking, NO pgvector

Keep them separate, keep them focused, keep them performant! 🚀
