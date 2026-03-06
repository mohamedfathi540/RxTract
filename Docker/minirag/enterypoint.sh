#!/bin/bash
set -e

# Seed CSV data files into the volume if they don't exist yet
if [ -d /seed/Assets/Files ]; then
  echo "Seeding data files into volume..."
  cp -rn /seed/Assets/Files/. /app/Assets/Files/ 2>/dev/null || true
fi

echo "Runing database migrations..."
cd /app/Models/DB_Schemes/minirag
alembic upgrade head
cd /app

echo "Starting uvicorn server..."
exec "$@"



