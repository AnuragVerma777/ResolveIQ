# ResolveIQ Production Deployment Guide

**System:** ResolveIQ v3.0 (Autonomous PayPal Dispute Intelligence & Evidence Adjudication Workspace)  
**Revision:** Production Readiness Release  
**Target Environments:** Docker, Docker Compose, AWS ECS / Fargate, GCP Cloud Run, DigitalOcean, Linux VM (Ubuntu / Debian)

---

## 1. Architectural Overview & Topologies

ResolveIQ is architected for production-grade reliability, containerization, and zero-downtime deployment:

```
                            [ Reverse Proxy / Ingress ]
                            (Nginx / Traefik / AWS ALB)
                                        │
                         TLS 443 ───────┼─────── Strict HTTPS
                                        ▼
                   ┌─────────────────────────────────────────┐
                   │       ResolveIQ Docker Container        │
                   │                                         │
                   │   GET /        ─► StaticFiles (React 19)│
                   │   GET /health  ─► Health Probe          │
                   │   POST /api/*  ─► FastAPI ASGI Worker   │
                   └────────────────────┬────────────────────┘
                                        │
                         Mounted Persistent Volume
                                        ▼
                   ┌─────────────────────────────────────────┐
                   │             /app/storage                │
                   │  - resolveiq.db (SQLite WAL Mode)       │
                   │  - /uploads/ (Sanitized Documents)      │
                   └─────────────────────────────────────────┘
```

### Supported Topologies:
1. **Unified Single-Container (Recommended):** FastAPI serves both the optimized React 19 SPA (`/`) and API routes (`/api/*`). Zero cross-origin latency, zero CORS friction, minimal operational overhead.
2. **Decoupled CDN + API Server:** Frontend deployed to Vercel, Netlify, or AWS S3/CloudFront with `VITE_API_BASE=https://api.yourdomain.com/api`. Backend deployed independently on ECS or Cloud Run with CORS origin whitelisting.

---

## 2. Quickstart with Docker Compose

### Prerequisites
- Docker Engine 24.0+ and Docker Compose 2.20+
- Valid PayPal Developer credentials (Sandbox or Live)
- Gemini API Key (Google AI Studio)

### Step 1: Clone Repository & Create `.env`
```bash
git clone https://github.com/your-org/resolveiq.git
cd resolveiq
cp .env.example .env
```

### Step 2: Configure Environment Variables
Edit `.env` with your production values:
```env
ENVIRONMENT=production
LOG_LEVEL=INFO

# PayPal Live or Sandbox Credentials
PAYPAL_BASE_URL=https://api-m.paypal.com
PAYPAL_CLIENT_ID=your_paypal_client_id
PAYPAL_CLIENT_SECRET=your_paypal_client_secret

# Google Gemini AI Key
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

# Zapier Webhook (Optional)
ZAPIER_WEBHOOK_URL=https://hooks.zapier.com/hooks/catch/xxxx/yyyy

# CORS Whitelist for Production Domain
ALLOWED_ORIGINS=https://resolveiq.yourdomain.com
```

### Step 3: Build & Launch
```bash
# Build multi-stage image and start daemon
docker compose up -d --build

# Verify container status and healthcheck
docker compose ps
```

### Step 4: Verify Health
```bash
curl -f http://localhost:8000/health
```
Response:
```json
{
  "status": "healthy",
  "service": "ResolveIQ Intelligence Engine",
  "version": "2.0.0",
  "environment": "production",
  "database_connected": true,
  "storage_writeable": true,
  "gemini_configured": true,
  "gemini_model": "gemini-2.5-flash",
  "paypal_configured": true,
  "zapier_configured": true,
  "max_upload_size_mb": 15
}
```

---

## 3. Bare-Metal & Linux VM Deployment (Ubuntu 22.04 LTS / 24.04 LTS)

### Step 1: System Dependencies
```bash
sudo apt-get update && sudo apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    nodejs \
    npm \
    nginx \
    certbot \
    python3-certbot-nginx
```

### Step 2: Build Frontend
```bash
cd /opt/resolveiq/frontend
npm ci
npm run build
```

### Step 3: Set up Backend Virtual Environment
```bash
cd /opt/resolveiq
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Systemd Service Configuration
Create `/etc/systemd/system/resolveiq.service`:
```ini
[Unit]
Description=ResolveIQ Dispute Intelligence Service
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/resolveiq
EnvironmentFile=/opt/resolveiq/.env
ExecStart=/opt/resolveiq/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5s

# Security sandboxing
ProtectSystem=full
ProtectHome=true
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Reload and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now resolveiq
sudo systemctl status resolveiq
```

### Step 5: Nginx Reverse Proxy & SSL
Create `/etc/nginx/sites-available/resolveiq`:
```nginx
server {
    server_name resolveiq.yourdomain.com;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 15s;
    }
}
```

Enable site and acquire SSL certificate:
```bash
sudo ln -s /etc/nginx/sites-available/resolveiq /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d resolveiq.yourdomain.com
```

---

## 4. Cloud Container Deployment (AWS ECS / GCP Cloud Run / Render)

### Google Cloud Run:
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/resolveiq
gcloud run deploy resolveiq \
    --image gcr.io/PROJECT_ID/resolveiq \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --port 8000 \
    --memory 1Gi \
    --set-env-vars ENVIRONMENT=production,PAYPAL_BASE_URL=https://api-m.paypal.com \
    --set-secrets PAYPAL_CLIENT_ID=paypal_client_id:latest,PAYPAL_CLIENT_SECRET=paypal_client_secret:latest,GEMINI_API_KEY=gemini_api_key:latest
```

---

## 5. Storage Persistence & SQLite WAL Backups

ResolveIQ stores dispute records and audit trails in SQLite utilizing **Write-Ahead Logging (WAL)**:
- `PRAGMA journal_mode=WAL;`
- `PRAGMA foreign_keys=ON;`

### Backup Procedure (Hot Backup without Downtime)
SQLite WAL mode allows online backups while active writes occur:
```bash
# Automated daily backup script
BACKUP_DIR="/backups/resolveiq"
mkdir -p "$BACKUP_DIR"
sqlite3 /app/storage/resolveiq.db ".backup '$BACKUP_DIR/resolveiq_$(date +%Y%m%d_%H%M%S).db'"
# Sync uploaded files
rsync -av /app/storage/uploads/ "$BACKUP_DIR/uploads/"
```

---

## 6. Health & Liveness Probes

| Endpoint | Probe Type | Purpose | Recommended Interval |
|---|---|---|---|
| `GET /health` | Liveness / Readiness | Checks API responsiveness, SQLite read/write, and upload directory permissions. Returns HTTP 200 with status `"healthy"`. | 15s–30s |
| `GET /api/health` | Client Health | Same payload, mapped under `/api` for frontend inspection. | On-demand / app boot |
| `GET /api/paypal/status` | Integration Health | Verifies PayPal OAuth token validity and connectivity mode. | On-demand |

---

## 7. Security Hardening Checklist

- [x] **No hardcoded secrets:** All credentials loaded strictly via environment variables.
- [x] **MIME type verification:** Binary magic-byte checking prevents disguised executable uploads.
- [x] **Path traversal protection:** Strict resolution inside sandboxed base directories.
- [x] **Request payload caps:** 20MB max request size (HTTP 413) blocks payload bomb attacks.
- [x] **Origin-whitelisted CORS:** Browsers restricted to authorized domains.
- [x] **Rate limiting:** Sensitive endpoints throttled with token-bucket limiter (HTTP 429).
- [x] **Double-submission guard:** In-flight concurrency locks prevent duplicate PayPal submissions.
- [x] **Prompt injection isolation:** Uploaded OCR strings wrapped in XML quarantine blocks before Gemini analysis.
- [x] **Generic error responses:** Unhandled exceptions sanitized (HTTP 500) to prevent trace leakage.
