
FROM ghcr.io/astral-sh/uv:0.9.26-python3.11-trixie

WORKDIR /app
#Install Additional system dependences for lxml and other packages

RUN apt-get update && apt-get install -y \
    build-essential \
    libavif-dev pkg-config \
    libjpeg-dev \
    gcc unzip zip \
    python3-dev \
    libxml2-dev \
    libxslt-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*
   
COPY SRC/pyproject.toml .

ENV UV_HTTP_TIMEOUT=120
ENV UV_PROJECT_ENVIRONMENT=/usr/local
RUN uv sync --no-dev --no-install-project

COPY SRC/ .

#create directory for alembic
RUN mkdir -p Models/DB_Schemes/minirag
 
COPY Docker/minirag/alembic.ini /app/Models/DB_Schemes/minirag/alembic.ini

COPY Docker/minirag/enterypoint.sh /enterypoint.sh
RUN chmod +x /enterypoint.sh

ENTRYPOINT ["/enterypoint.sh"]


#Command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
