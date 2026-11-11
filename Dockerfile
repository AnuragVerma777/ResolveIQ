# ==============================================================================
# ResolveIQ Production Multi-Stage Dockerfile
# Builds React 19 Frontend and packages into hardened FastAPI Python runtime.
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build React 19 Frontend
# ------------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder
WORKDIR /build

# Install dependencies with lockfile caching
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy frontend source files and compile Vite production bundle
COPY frontend/ ./
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Production Python Runtime
# ------------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Metadata
LABEL maintainer="ResolveIQ Engineering Team"
LABEL version="3.0.0"
LABEL description="ResolveIQ Autonomous PayPal Dispute Intelligence & Evidence Adjudication Platform"

# Prevent Python from writing bytecode and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    DB_PATH=/app/storage/resolveiq.db \
    UPLOAD_DIR=/app/storage/uploads

# Install minimal OS dependencies for health checking & document processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN groupadd -g 1001 resolveiq && \
    useradd -u 1001 -g resolveiq -s /bin/bash -m resolveiq

WORKDIR /app

# Install Python production dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY backend ./backend

# Copy compiled frontend distribution from Stage 1
COPY --from=frontend-builder /build/dist ./frontend/dist

# Prepare storage directories with proper permissions
RUN mkdir -p /app/storage/uploads && \
    chown -R resolveiq:resolveiq /app/storage

# Persist SQLite WAL database and uploaded merchant documents across restarts
VOLUME ["/app/storage"]

# Run as non-privileged service user
USER resolveiq

EXPOSE 8000

# Automated container healthcheck hitting native /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Launch ASGI application server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
