# Deployment Guide

> Guide for deploying the AI Video Editor to various environments.

## Table of Contents

- [Deployment Options](#deployment-options)
- [Docker Deployment](#docker-deployment)
- [Modal.com Deployment](#modalcom-deployment)
- [Temporal Setup](#temporal-setup)
- [Production Checklist](#production-checklist)
- [Environment Configuration](#environment-configuration)
- [Monitoring and Observability](#monitoring-and-observability)
- [Backup and Disaster Recovery](#backup-and-disaster-recovery)

---

## Deployment Options

| Environment | Method | Best For |
|---|---|---|
| **Local Dev** | Docker Compose | Development, testing |
| **Staging** | Docker Compose on VPS | Pre-production validation |
| **Production** | Docker on cloud VM (ECS, GKE, DOKS) | Live traffic |
| **Serverless Workers** | Modal.com | GPU-intensive tasks (render, upscale) |
| **Edge** | Cloudflare Pages (web) + Workers (API) | Low-latency global distribution |

---

## Docker Deployment

### Building Images

```bash
# API image
docker build -f infra/docker/Dockerfile.api -t aivideo/api:latest .

# Web image
docker build -f infra/docker/Dockerfile.web -t aivideo/web:latest .

# Worker images
docker build -f infra/docker/Dockerfile.ingest -t aivideo/ingest:latest .
docker build -f infra/docker/Dockerfile.render -t aivideo/render:latest .
```

### Docker Compose (Full Stack)

```bash
# Local / staging stack
pnpm infra:up

# With rebuild
docker compose -f infra/local/docker-compose.yml up -d --build

# Scale workers
docker compose -f infra/local/docker-compose.yml up -d --scale ingest-worker=4 --scale segment-worker=2 --scale render-worker=4
```

Production images are built from Dockerfiles in `infra/docker/`.

### Docker Compose Services

| Service | Image | Ports | Replicas |
|---|---|---|---|
| `api` | `aivideo/api` | 4000 | 2 |
| `web` | `aivideo/web` | 3000 | 2 |
| `postgres` | `postgres:16` | 5432 | 1 |
| `redis` | `redis:7` | 6379 | 1 |
| `temporal` | `temporalio/auto-setup` | 7233, 8233 | 1 |
| `temporal-ui` | `temporalio/ui` | 8080 | 1 |
| `ingest-worker` | `aivideo/ingest` | — | 2 |
| `segment-worker` | `aivideo/segment` | — | 1 |
| `render-worker` | `aivideo/render` | — | 2 |

### Health Checks

All services expose health endpoints:

```bash
# API health
curl http://api:4000/api/health

# Database health
curl http://api:4000/api/health/db

# Temporal health
temporal operator cluster health

# Redis health
redis-cli ping
```

### Reverse Proxy (nginx/Caddy)

Example Caddyfile:

```
aivideo.example.com {
    reverse_proxy /api/* api:4000
    reverse_proxy /* web:3000
}
```

---

## Modal.com Deployment

Modal.com provides serverless GPU/CPU compute for workers.

### Deploy Ingest Worker

```bash
modal deploy infra/modal/ingest_modal.py
```

### Deploy Render Worker

```bash
modal deploy infra/modal/render_modal.py
```

### Modal Configuration

Each Modal script defines:
- **Image** — Docker image with dependencies
- **GPU** — `T4`, `A10G`, `A100` for ML tasks
- **Memory** — RAM allocation
- **Timeout** — Max execution time
- **Concurrency** — Max parallel containers

### Modal Secrets

Store sensitive values in Modal secrets:

```bash
modal secret create aivideo-secrets \
  ANTHROPIC_API_KEY=sk-ant-... \
  OPENAI_API_KEY=sk-openai-... \
  R2_ACCESS_KEY_ID=... \
  R2_SECRET_ACCESS_KEY=...
```

---

## Temporal Setup

### Self-Hosted Temporal

The Docker Compose setup includes Temporal server and UI:

```yaml
temporal:
  image: temporalio/auto-setup:1.22
  environment:
    - DB=postgresql
    - DB_PORT=5432
    - POSTGRES_USER=postgres
    - POSTGRES_PWD=postgres
    - POSTGRES_SEEDS=postgres
    - DYNAMIC_CONFIG_FILE_PATH=config/dynamicconfig/development.yaml
  ports:
    - "7233:7233"
```

### Temporal Cloud (Production)

For production, use Temporal Cloud:

```bash
# Set environment variables
TEMPORAL_HOST=your-namespace.tmprl.cloud:7233
TEMPORAL_NAMESPACE=your-namespace
TEMPORAL_TLS_CERT=/path/to/cert.pem
TEMPORAL_TLS_KEY=/path/to/key.pem
```

### Worker Registration

Run workers directly from the repo root:

```bash
# Ingest worker
uv run python -m ingest_worker

# Segment worker
uv run python -m segment_worker

# Render worker
uv run python -m render_worker
```

Workers register the following activities:
- **Ingest**: `probe_asset`
- **Segment**: `segment_subject`
- **Render**: `fetch_project`, `download_clips`, `compile_video`, `upload_render`, `finalize_render`

### Workflow Retention

Set retention policy to keep workflow history:

```bash
temporal namespace update --retention 30  # Keep 30 days of history
```

---

## Production Checklist

### Security

- [ ] Replace XOR encryption with AES-256-GCM for provider keys
- [ ] Use a secrets manager (HashiCorp Vault, AWS Secrets Manager, 1Password Secrets Automation)
- [ ] Enable Clerk webhook verification
- [ ] Configure CORS to allow only production domains
- [ ] Set up WAF (Cloudflare, AWS WAF) for DDoS protection
- [ ] Enable HTTPS with valid TLS certificates
- [ ] Rotate database credentials regularly
- [ ] Enable PostgreSQL SSL connections
- [ ] Set up Redis AUTH password
- [ ] Review and minimize Docker image attack surface

### Performance

- [ ] Configure Redis persistence (RDB + AOF)
- [ ] Set up PostgreSQL connection pooling (PgBouncer)
- [ ] Enable API response caching for static data
- [ ] Configure CDN for video delivery (Cloudflare Stream, Mux)
- [ ] Set up auto-scaling for workers based on queue depth
- [ ] Monitor and optimize slow database queries
- [ ] Enable PostgreSQL query logging for analysis

### Reliability

- [ ] Set up database backups (daily automated)
- [ ] Configure Redis backup
- [ ] Set up log aggregation (Datadog, Grafana Loki, CloudWatch)
- [ ] Configure alerting (PagerDuty, Opsgenie, Slack)
- [ ] Set up health check endpoints for load balancers
- [ ] Configure graceful shutdown for all services
- [ ] Test disaster recovery procedures

### Monitoring

- [ ] API request latency and error rate
- [ ] Worker queue depth and processing time
- [ ] Temporal workflow success/failure rates
- [ ] Database connection pool usage
- [ ] Redis memory usage and hit rate
- [ ] Storage (R2) usage and egress costs
- [ ] AI provider API costs and rate limit usage

---

## Environment Configuration

### Production Environment Variables

```bash
# API
NODE_ENV=production
DATABASE_URL=postgresql://user:pass@prod-db:5432/aivideo?sslmode=require
REDIS_URL=redis://:password@prod-redis:6379/0
TEMPORAL_HOST=prod-temporal:7233
TEMPORAL_NAMESPACE=production
INTERNAL_WORKER_TOKEN=<random-secret>
WEB_URL=https://app.aivideo.example.com
CLERK_SECRET_KEY=sk_live_...
CLERK_PUBLISHABLE_KEY=pk_live_...

# Storage
R2_ENDPOINT=https://account.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=aivideo-assets-prod

# AI Providers (global fallback keys)
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-openai-...
AI_PROVIDER=claude

# Encryption (replace with proper key management)
PROVIDER_ENCRYPTION_SECRET=<32-byte-random-hex>

# Logging
LOG_LEVEL=warn
```

### Web Environment

```bash
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
NEXT_PUBLIC_API_URL=https://api.aivideo.example.com
```

---

## Monitoring and Observability

### Logging

**API Logs:**
- Structured JSON logging via Pino
- Correlation IDs on all requests (`x-request-id` header)
- Log levels: `trace`, `debug`, `info`, `warn`, `error`, `fatal`

**Python Worker Logs:**
- Structured JSON via `shared_py.logging_config`
- Component tags for filtering
- Workflow ID correlation

### Prometheus Metrics

The API exposes built-in Prometheus metrics at `GET /api/metrics`. Protect the endpoint in production with `METRICS_AUTH_TOKEN`.

#### Available Metrics

| Metric | Type | Labels | Description |
|---|---|---|---|
| `ave_http_requests_total` | Counter | `method`, `route`, `status_code` | Total HTTP requests |
| `ave_http_request_duration_seconds` | Histogram | `method`, `route` | Request latency distribution |
| `ave_renders_active` | Gauge | — | Renders currently queued or running |
| `ave_renders_total` | Counter | `status` (started/complete/failed) | Render lifecycle events |
| `ave_ai_calls_total` | Counter | `provider`, `status` | AI provider API calls |
| `ave_ai_call_duration_seconds` | Histogram | `provider` | AI call latency distribution |
| `ave_cache_operations_total` | Counter | `operation`, `result` | Cache hits and misses |
| `ave_queue_depth` | Gauge | — | Current Redis job queue depth |
| `ave_errors_total` | Counter | `code`, `route` | Application errors |
| `ave_rate_limit_hits_total` | Counter | `route` | Rate limit triggers |
| `ave_startup_timestamp_seconds` | Gauge | — | Last app startup Unix timestamp |

#### Running Prometheus + Grafana Locally

```bash
# Start the monitoring stack
pnpm obs:up

# Access:
# Prometheus UI: http://localhost:9090
# Grafana UI:    http://localhost:3001 (admin/admin)
```

Grafana is pre-provisioned with:
- **Prometheus datasource** at `http://prometheus:9090`
- **AVE API Overview dashboard** (`infra/grafana/dashboards/api-overview.json`)

Import the dashboard in Grafana via **Dashboards → Import** and paste the JSON, or copy it to `/var/lib/grafana/dashboards/` if using the Docker Compose setup.

### Alerting Rules

```yaml
# Prometheus alerting rules (save as infra/observability/alerts.yml)
groups:
  - name: ave
    rules:
      - alert: HighErrorRate
        expr: rate(ave_http_requests_total{status_code=~"4..|5.."}[5m]) / rate(ave_http_requests_total[5m]) > 0.01
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High error rate on {{ $labels.route }}"

      - alert: SlowRequests
        expr: histogram_quantile(0.99, rate(ave_http_request_duration_seconds_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P99 latency > 500ms on {{ $labels.route }}"

      - alert: QueueBacklog
        expr: ave_queue_depth > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Job queue backlog: {{ $value }} jobs"

      - alert: RenderFailureRate
        expr: rate(ave_renders_total{status="failed"}[5m]) / rate(ave_renders_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Render failure rate > 5%"

      - alert: AIProviderErrors
        expr: rate(ave_ai_calls_total{status!="success"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High AI provider error rate for {{ $labels.provider }}"
```

---

## Backup and Disaster Recovery

### Database Backups

```bash
# Automated daily backup
pg_dump $DATABASE_URL | gzip > backup-$(date +%Y%m%d).sql.gz

# Restore from backup
gunzip -c backup-20250115.sql.gz | psql $DATABASE_URL
```

### Asset Storage Backups

R2/MinIO should have:
- Versioning enabled
- Cross-region replication for critical assets
- Lifecycle rules to move old versions to cold storage

### Redis Backups

```bash
# Enable RDB persistence in redis.conf
save 900 1
save 300 10
save 60 10000

# Or AOF
appendonly yes
appendfsync everysec
```

### Disaster Recovery Plan

1. **Identify failure** — Monitoring alert triggers
2. **Assess scope** — Which services are affected?
3. **Switch to standby** — If multi-region, failover
4. **Restore data** — Database from latest backup, assets from replica
5. **Verify integrity** — Run health checks on all services
6. **Post-mortem** — Document incident and preventive measures

**RTO (Recovery Time Objective):** 1 hour
**RPO (Recovery Point Objective):** 24 hours (daily backups)

---

## Scaling Guidelines

### Horizontal Scaling

| Component | Scale Trigger | Method |
|---|---|---|
| API | CPU > 70% | Add containers behind load balancer |
| Web | CPU > 70% | Add containers behind CDN |
| Ingest Worker | Queue depth > 50 | Add worker replicas |
| Render Worker | Queue depth > 20 | Add GPU workers (Modal) |
| PostgreSQL | Connection pool > 80% | Add read replicas |
| Redis | Memory > 80% | Upgrade instance or shard |

### Vertical Scaling

| Component | Bottleneck | Solution |
|---|---|---|
| Render Worker | Slow FFmpeg | GPU instances (T4, A10G) |
| Ingest Worker | Slow ML models | GPU for TransNet V2 |
| API | CPU-bound | More cores |
| PostgreSQL | Query performance | More RAM for cache |

---

## Related Documentation

- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — System architecture overview
- [`DEVELOPMENT.md`](./DEVELOPMENT.md) — Local development setup
- [`API.md`](./API.md) — API endpoint reference
