# AVE Observability Stack (LGTM)

Self-hosted observability: **L**oki + **G**rafana + **T**empo + **P**rometheus + Promtail + OTel Collector.

## Quick Start

```bash
# From repo root
docker compose -f infra/observability/docker-compose.yml up -d
```

Or via pnpm script (add to root `package.json`):

```bash
pnpm obs:up
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| Grafana | 3001 | Dashboards & exploration |
| Prometheus | 9090 | Metrics storage |
| Loki | 3100 | Log aggregation |
| Tempo | 3200 | Distributed tracing |
| OTel Collector | 4317 (gRPC), 4318 (HTTP) | OTel ingestion |
| Promtail | — | Docker log shipping |

## Defaults

- **Grafana**: `admin` / `admin`
- All services bind to `127.0.0.1` (no public exposure)
- Log retention: 7 days
- Trace retention: 7 days
- Metrics retention: 15 days

## Datasources

Provisioned automatically on startup:
- **Prometheus** (default)
- **Loki** — with traceID derived field linked to Tempo
- **Tempo** — with traces-to-logs linking back to Loki

## Dashboards

| Dashboard | UID | Source |
|-----------|-----|--------|
| API Health | `ave-api-health` | Prometheus |
| Temporal Workflows | `ave-temporal-workflows` | Prometheus + Loki |
| AI Calls | `ave-ai-calls` | Prometheus |
| Render Queue | `ave-render-queue` | Prometheus + Loki |
| User Activity | `ave-user-activity` | Loki + Prometheus |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OBS_GRAFANA_PORT` | `3001` | Host port for Grafana |
| `LOKI_URL` | `http://loki:3100` | Loki endpoint for pino-loki transport |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4318` | OTel HTTP exporter endpoint |

## Production Notes

- Tempo uses local disk; switch to S3/R2 for production.
- Loki filesystem backend is fine for single-node; use tsdb + object storage for HA.
- Promtail scrapes containers labeled `logging=promtail`. Add labels to services:
  ```yaml
  labels:
    logging: promtail
    logging_jobname: api
  ```
