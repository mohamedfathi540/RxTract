<![CDATA[# RxTract — Docker Deployment

> Complete containerized deployment with application server, databases, reverse proxy, and monitoring stack.

---

## 📋 Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 20+
- [Docker Compose](https://docs.docker.com/compose/install/) v2+

---

## 🏗️ Architecture Overview

### Production Stack (`docker-compose.yml`)

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| **fastapi** | Custom build | `8000` | FastAPI application server |
| **nginx** | nginx:latest | `80` | Reverse proxy (routes to frontend + API) |
| **pgvector** | pgvector/pgvector:0.8.0-pg17 | `5433` | PostgreSQL with vector similarity search |
| **qdrant** | qdrant/qdrant:latest | `6333`, `6334` | Vector database (alternative to pgvector) |
| **prometheus** | prom/prometheus | `9090` | Metrics collection |
| **grafana** | grafana/grafana | `3000` | Monitoring dashboards |
| **node_exporter** | prom/node-exporter | `9100` | Host hardware/OS metrics |
| **postgres_exporter** | prometheuscommunity/postgres-exporter | `9187` | PostgreSQL performance metrics |

### Development Stack (`docker-compose.dev.yml`)

For local development, only the databases run in Docker:

| Service | Port | Notes |
|---------|------|-------|
| **pgvector** | `5433` | PostgreSQL 17 + pgvector 0.8.0 |
| **qdrant** | `6333` | Vector database |

> Use `bash dev.sh` from the project root to start the dev stack automatically.

---

## 🚀 Quick Start

### Production Deployment

```bash
cd Docker

# 1. Configure environment files
#    Edit files in Docker/env/ directory:
#    - .env.app        → FastAPI settings (API keys, model config)
#    - .env.postgres   → PostgreSQL credentials
#    - .env.grafana    → Grafana admin credentials
#    - .env.postgres-exporter → Exporter credentials (must match postgres)

# 2. Start all services
docker compose up -d --build

# 3. Verify services are running
docker compose ps
```

### Development (Databases Only)

```bash
docker compose -f docker-compose.dev.yml up -d
```

---

## 🔧 Configuration

### Environment Files (`env/` directory)

| File | Purpose | Key Variables |
|------|---------|---------------|
| `.env.app` | FastAPI application | `GENRATION_BACKEND`, `EMBEDDING_BACKEND`, `OCR_BACKEND`, API keys |
| `.env.postgres` | PostgreSQL | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` |
| `.env.grafana` | Grafana | `GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD` |
| `.env.postgres-exporter` | Exporter | Must match PostgreSQL credentials |

### Nginx Configuration (`Nginx/Default.conf`)

Routes incoming HTTP requests:
- `/` → Frontend static files or FastAPI application
- `/kfgndfkk4464_fubfd555` → FastAPI Prometheus metrics endpoint (obfuscated)

### Prometheus Configuration (`Prometheus/prometheus.yml`)

Scrape targets:
| Job | Target | Metrics |
|-----|--------|---------|
| `fastapi` | `fastapi:8000/kfgndfkk4464_fubfd555` | Application metrics |
| `postgres` | `postgres_exporter:9187` | Database metrics |
| `node_exporter` | `node_exporter:9100` | System metrics |
| `qdrant` | `qdrant:6333/metrics` | Vector DB metrics |
| `prometheus` | `localhost:9090` | Self-monitoring |

> [!IMPORTANT]
> **Case Sensitivity**: The file is named `Prometheus.yml` but referenced as `prometheus.yml` in docker-compose. On Linux, rename to lowercase or update the volume mount path.

---

## 🗃️ Data Persistence

All data is stored in named Docker volumes:

| Volume | Service | Contains |
|--------|---------|----------|
| `pgvector` | PostgreSQL | Database files, vector indexes |
| `qdrant_data` | Qdrant | Vector collections |
| `prometheus_data` | Prometheus | Time-series metrics |
| `grafana_data` | Grafana | Dashboards, data sources |

### Backup & Restore

```bash
# Backup PostgreSQL volume
docker run --rm \
  -v docker_pgvector:/volume \
  -v $(pwd):/backup \
  alpine tar cvf /backup/pgvector_backup.tar /volume

# Restore PostgreSQL volume (⚠️ overwrites existing data)
docker run --rm \
  -v docker_pgvector:/volume \
  -v $(pwd):/backup \
  alpine sh -c "cd /volume && tar xvf /backup/pgvector_backup.tar --strip 1"

# List all volumes
docker volume ls

# Remove unused volumes (⚠️ data loss)
docker volume prune
```

> **Note:** Docker Compose prefixes volume names with the directory name (e.g., `docker_pgvector`). Run `docker volume ls` to confirm exact names.

---

## 🐳 Container Entrypoints

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

Configured with: interval=5s, timeout=5s, retries=10, start_period=30s

---

## 🛠️ Common Commands

### Service Management

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart fastapi

# Rebuild after code changes
docker compose up -d --build fastapi
```

### Debugging

```bash
# Follow all logs
docker compose logs -f

# Follow specific service logs
docker compose logs -f fastapi

# Shell into application container
docker exec -it fastapi /bin/bash

# Shell into PostgreSQL
docker exec -it pgvector psql -U postgres

# Run migrations manually
docker exec -it fastapi bash -c "cd /app/Models/DB_Schemes/minirag && alembic upgrade head"
```

---

## 🌐 Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| **Application** | http://localhost | — |
| **FastAPI Docs** | http://localhost:8000/docs | — |
| **Grafana** | http://localhost:3000 | Set in `.env.grafana` |
| **Prometheus** | http://localhost:9090 | — |
| **Qdrant Dashboard** | http://localhost:6333/dashboard | — |
]]>
