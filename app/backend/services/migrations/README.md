# Database Migrations

This directory contains database migration scripts for schema evolution.

## Usage

### Create a new migration

```bash
python -m services.migrate create add_new_column
```

This creates a timestamped migration file in `migrations/`.

### Apply pending migrations

Migrations are automatically applied on server startup via `lifespan` in `main.py`.

Or run manually:

```python
from services.migrate import MigrationRunner
from services.migrations import migration_001

runner = MigrationRunner()
runner.run_migrations([migration_001.Migration001()])
runner.close()
```

## Migration Files

| Version | Description | Status |
|---------|-------------|--------|
| 001 | Phase 2 schema (estimated_hours, RAG, archived_contexts) | ✅ Ready |

## Schema Tracking

The `schema_migrations` table tracks which migrations have been applied:

```sql
SELECT * FROM schema_migrations;
```

## Notes

- Migrations run in version order (001, 002, 003, ...)
- Each migration can be reverted with `down()`
- SQLite has limited ALTER TABLE support - complex changes may require table recreation
