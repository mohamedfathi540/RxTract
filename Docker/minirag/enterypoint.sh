#!/bin/bash
set -e

echo "Runing database migrations..."
cd /app/Models/DB_Schemes/minirag
alembic upgrade head
cd /app

echo "Starting uvicorn server..."
exec "$@"



