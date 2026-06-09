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
# Production compose
docker compose -f infra/docker/docker-compose.yml up -d

# With rebuild
docker compose -f infra/docker/docker-compose.yml up -d --build

# Scale workers
docker compose -f infra/docker/docker-compose.yml up -d --scale ingest-worker=4 --scale render-worker=4
```

### Docker Compose Services

| Service | Image | Ports | Replicas |
|---|---|---|---|
| `api` | `aivideo/api` | 4000 | 2 |
| `web` | `aivideo/web` | 3000 | 2 |
| `postgres` | `postgres:16` | 5432 | 1 |
| `redis` | `redis:7` | 6379 | 1 |
| `temporal` | `temporalio/auto-setup` | 7233, 8088 | 1 |
| `ingest-worker` | `aivideo/ingest` | — | 2 |
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

```bash
# Register Temporal worker
python infra/temporal/worker.py
```

The worker connects to Temporal server and registers all activities:
- `probe_inputs`
- `detect_beats`
- `detect_shots`
- `analyze_reference_style`
- `embed_user_clips`
- `generate_cutlist_claude`
- `rank_clips_per_slot`
- `render_720p`
- `upload_to_r2`
- `notify_user`

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

### Metrics

Recommended metrics to track:

| Metric | Source | Alert Threshold |
|---|---|---|
| API request latency (p99) | Fastify | > 500ms |
| API error rate | Fastify | > 1% |
| Active renders | Temporal | — |
| Render failure rate | Temporal | > 5% |
| Queue depth | Redis | > 100 |
| Worker processing time | Temporal | > 10 min |
| Database connections | PostgreSQL | > 80% of max |
| Redis memory usage | Redis | > 80% |
| Storage costs | R2/MinIO | Monthly budget |

### Alerting Rules

```yaml
# Example Prometheus alerting rules
- alert: HighErrorRate
  expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.01
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "High error rate on {{ $labels.route }}"

- alert: WorkerQueueBacklog
  expr: redis_queue_depth > 100
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Worker queue backlog detected"
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
