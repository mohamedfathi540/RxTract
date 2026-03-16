# RxTract -- Docker Deployment

> Complete containerized deployment with application server, databases, and reverse proxy.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 20+
- [Docker Compose](https://docs.docker.com/compose/install/) v2+

---

## Architecture Overview

### Production Stack (`docker-compose.yml`)

| Service | Container Name | Image | Host Port | Internal Port | Purpose |
|---------|---------------|-------|-----------|---------------|---------|
| FastAPI | `rxtract_fastapi` | Custom build | 8009 | 8000 | FastAPI application server |
| Frontend | `rxtract_frontend` | Custom build | 5174 | 80 | React 19 SPA (Nginx-served) |
| Nginx | `rxtract_nginx` | nginx:latest | 8899 | 80 | Reverse proxy (routes to frontend + API) |
| PostgreSQL | `rxtract_pgvector` | pgvector/pgvector:0.8.0-pg17 | 5436 | 5432 | PostgreSQL with vector similarity search |
| Qdrant | `rxtract_qdrant` | qdrant/qdrant:latest | 6337 (HTTP), 6338 (gRPC) | 6333, 6334 | Vector database (alternative to pgvector) |

### Development Stack (`docker-compose.dev.yml`)

For local development, databases and a lightweight Nginx gateway run in Docker:

| Service | Container Name | Host Port | Notes |
|---------|---------------|-----------|-------|
| pgvector | `pgvector` | 5436 | PostgreSQL 17 + pgvector 0.8.0 |
| qdrant | `qdrant` | 6337, 6338 | Vector database |
| Nginx (hybrid proxy) | `rxtract_nginx_dev` | 8899 | Proxies to local frontend (`5777`) and local backend (`8000`) |

Dev stack bind mounts:

- PostgreSQL data -> `/srv/mergerfs/2TB/rxtract_db`
- Qdrant storage -> `/srv/mergerfs/2TB/rxtract_qdrant`

> Use `bash dev.sh` from the project root to start the dev stack automatically.

---

## Quick Start

### Production Deployment

```bash
cd Docker

# 1. Configure environment files
#    Copy example files and edit:
cp env/.env.app.example env/.env.app
#    Edit files in Docker/env/ directory:
#    - .env.app        -> FastAPI settings (API keys, model config, auth, quotas)
#    - .env.postgres   -> PostgreSQL credentials

# 2. Start all services
docker compose up -d --build

# 3. Verify services are running
docker compose ps
```

### Development (Hybrid Infra)

```bash
docker compose -f docker-compose.dev.yml up -d
```

---

## Configuration

### Environment Files (`env/` directory)

| File | Purpose | Key Variables |
|------|---------|---------------|
| `.env.app` | FastAPI application | LLM/OCR backends, API keys, JWT, rate limits, quotas, Brevo email config |
| `.env.postgres` | PostgreSQL | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |

### Application Environment (`.env.app`)

Copy `.env.app.example` to `.env.app` and configure. Key sections:

| Category | Variables |
|----------|----------|
| LLM | `GENRATION_BACKEND`, `EMBEDDING_BACKEND`, `GENRATION_MODEL_ID`, `EMBEDDING_MODEL_ID`, API keys |
| OCR | `OCR_BACKEND`, `OCR_MODEL_ID`, `OCR_MAX_OUTPUT_TOKENS`, `OCR_TEMPERATURE` |
| Vector DB | `VECTORDB_BACKEND` (`PGVECTOR` or `QDRANT`) |
| Auth | `JWT_SECRET`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` |
| Email | `BREVO_API_KEY`, `SENDER_EMAIL`, `FRONTEND_URL` |
| Rate Limits | `RATE_LIMIT_AUTH`, `RATE_LIMIT_UPLOAD`, `RATE_LIMIT_QUERY`, `RATE_LIMIT_PRESCRIPTION` |
| Quotas | `QUOTA_DAILY_QUERIES`, `QUOTA_DAILY_PRESCRIPTIONS`, `QUOTA_DAILY_UPLOADS` |
| Hybrid Search | `HYBRID_SEARCH_ENABLED`, `HYBRID_SEARCH_ALPHA` |

See `SRC/.env.example` for the full variable reference with descriptions.

### Nginx Configuration (`Nginx/Default.conf`)

Routes incoming HTTP requests:

- `/api/v1/*`, `/docs`, `/openapi.json` -> FastAPI (`rxtract_fastapi:8000`)
- `/` (everything else) -> Frontend (`rxtract_frontend:80`)
- `/kfgndfkk4464_fubfd555` -> FastAPI Prometheus metrics endpoint (obfuscated path)

---

## Data Persistence

All data is stored in named Docker volumes:

| Volume | Service | Contains |
|--------|---------|----------|
| `rxtract_fastapi_data` | FastAPI | Uploaded assets (mounted at `/app/Assets`) |
| `rxtract_pgvector_data` | PostgreSQL | Database files, vector indexes |
| `rxtract_qdrant_data` | Qdrant | Vector collections |

### Backup & Restore

```bash
# Backup PostgreSQL volume
docker run --rm \
  -v rxtract_pgvector_data:/volume \
  -v $(pwd):/backup \
  alpine tar cvf /backup/pgvector_backup.tar /volume

# Restore PostgreSQL volume (overwrites existing data)
docker run --rm \
  -v rxtract_pgvector_data:/volume \
  -v $(pwd):/backup \
  alpine sh -c "cd /volume && tar xvf /backup/pgvector_backup.tar --strip 1"

# List all volumes
docker volume ls

# Remove unused volumes (data loss warning)
docker volume prune
```

---

## Container Entrypoints

### FastAPI (`minirag/entrypoint.sh`)

```bash
#!/bin/bash
set -e
echo "Running database migrations..."
cd /app/Models/DB_Schemes/minirag
alembic upgrade head       # Apply pending migrations
cd /app
echo "Starting uvicorn server..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
```

### PostgreSQL Healthcheck

```bash
pg_isready -U postgres     # Checks if database accepts connections
```

Configured with: interval=5s, timeout=5s, retries=10, start_period=60s

---

## Common Commands

### Service Management

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart rxtract_fastapi

# Rebuild after code changes
docker compose up -d --build rxtract_fastapi
```

### Debugging

```bash
# Follow all logs
docker compose logs -f

# Follow specific service logs
docker compose logs -f rxtract_fastapi

# Shell into application container
docker exec -it rxtract_fastapi /bin/bash

# Shell into PostgreSQL
docker exec -it rxtract_pgvector psql -U postgres

# Run migrations manually
docker exec -it rxtract_fastapi bash -c "cd /app/Models/DB_Schemes/minirag && alembic upgrade head"
```

---

## Access Points

### Production (docker-compose.yml)

| Service | URL |
|---------|-----|
| Application (via Nginx) | `http://localhost:8899` |
| Frontend (direct) | `http://localhost:5174` |
| FastAPI Docs | `http://localhost:8009/docs` |
| Qdrant Dashboard | `http://localhost:6337/dashboard` |

### Development (docker-compose.dev.yml)

| Service | URL |
|---------|-----|
| Application (via Nginx) | `http://localhost:8899` |
| PostgreSQL | `localhost:5436` |
| Qdrant Dashboard | `http://localhost:6337/dashboard` |

Backend and frontend run locally outside Docker in dev mode. See the [root README](../README.md) for the full dev setup.
