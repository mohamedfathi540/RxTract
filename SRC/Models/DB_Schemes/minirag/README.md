<![CDATA[# RxTract — Database Migrations

This directory contains the [Alembic](https://alembic.sqlalchemy.org/) migration scripts for managing the PostgreSQL database schema.

## Quick Reference

```bash
# Apply all pending migrations
alembic upgrade head

# Show current migration version
alembic current

# Generate a new migration after model changes
alembic revision --autogenerate -m "description of change"

# Rollback the last migration
alembic downgrade -1
```

## Notes

- Migrations run automatically on Docker container startup via `entrypoint.sh`
- For local development (`dev.sh`), run migrations manually before first use:
  ```bash
  cd SRC/Models/DB_Schemes/minirag
  uv run alembic upgrade head
  ```
]]>
