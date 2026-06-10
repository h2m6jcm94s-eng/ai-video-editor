# Development Guide

> Step-by-step guide for setting up the AI Video Editor locally and contributing to the codebase.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [Service Dependencies](#service-dependencies)
- [Running the Application](#running-the-application)
- [Development Workflows](#development-workflows)
- [Debugging](#debugging)
- [Common Issues](#common-issues)
- [Project Structure Deep Dive](#project-structure-deep-dive)

---

## Prerequisites

### Required Software

| Tool | Version | Purpose |
|---|---|---|
| Node.js | 20.x LTS | JavaScript runtime |
| pnpm | 9.15.x | Package manager (enforced via `packageManager` field) |
| Python | 3.11+ | Worker runtime |
| uv | 0.4.x+ | Python package manager |
| Docker | 24.x+ | Local infrastructure |
| Docker Compose | 2.x+ | Multi-container orchestration |
| Git | 2.40+ | Version control |

### Verify Installation

```bash
node --version    # v20.x.x
pnpm --version    # 9.15.x
python --version  # 3.11.x
uv --version      # 0.4.x
docker --version  # 24.x.x
docker compose version  # 2.x.x
```

### Recommended Tools

- **IDE**: VS Code with extensions:
  - ESLint
  - Prettier
  - Tailwind CSS IntelliSense
  - Python (Microsoft)
  - Ruff
- **API Client**: Postman, Insomnia, or HTTPie (for manual API testing)
- **Database**: pgAdmin or DBeaver (for inspecting Postgres)
- **Redis**: Redis Insight or `redis-cli`

---

## Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd ai_video_editor
```

### 2. Install JavaScript Dependencies

```bash
pnpm install
```

This installs all packages across the monorepo using pnpm workspaces. The first install may take 2-3 minutes.

### 3. Install Python Dependencies

```bash
# Create Python virtual environment
uv venv

# Install all Python packages across services
.venv\Scripts\python -m pip install -e services/shared-py -e services/ingest-worker -e services/style-worker -e services/reason-worker -e services/render-worker -e services/upscale-worker
```

On macOS/Linux:
```bash
source .venv/bin/activate
python -m pip install -e services/shared-py -e services/ingest-worker -e services/style-worker -e services/reason-worker -e services/render-worker -e services/upscale-worker
```

### 4. Start Infrastructure Services

```bash
# Core infrastructure (Postgres, Redis, Temporal)
docker compose -f infra/docker/docker-compose.yml up -d

# Observability stack (Grafana, Loki, Tempo, Prometheus, OTel Collector, Promtail)
pnpm obs:up
```

Core services:
- PostgreSQL 16 (port 5432)
- Redis 7 (port 6379)
- Temporal Server (port 7233)
- Temporal UI (port 8088)

Observability services:
- Grafana (port 3001) — dashboards and exploration
- Prometheus (port 9090) — metrics storage
- Loki (port 3100) — log aggregation
- Tempo (port 3200) — distributed tracing
- OTel Collector (ports 4317/4318) — OTLP ingestion

### 5. Set Up Environment Variables

Copy the example environment file:

```bash
cp apps/api/.env.example apps/api/.env
```

Edit `apps/api/.env` with your values. See the [Environment Variables](#environment-variables) section for details.

**Minimum required for local development:**
```bash
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/aivideo
REDIS_URL=redis://localhost:6379
TEMPORAL_HOST=localhost:7233
WEB_URL=http://localhost:3000
CLERK_SECRET_KEY=sk_test_...
CLERK_PUBLISHABLE_KEY=pk_test_...
```

### 6. Run Database Migrations

```bash
pnpm --filter @ai-video-editor/api db:migrate
```

### 7. Start the Development Servers

```bash
pnpm dev
```

This starts:
- Web frontend at `http://localhost:3000`
- API backend at `http://localhost:4000`
- Shared types watch mode

### 8. Verify Everything Works

1. Open `http://localhost:3000`
2. Sign in with Clerk (or use test credentials)
3. Create a new project
4. Upload a test video clip
5. The API should return a presigned URL and process the upload

---

## Environment Variables

### API Environment (`apps/api/.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | — | Redis connection string |
| `TEMPORAL_HOST` | Yes | — | Temporal server address |
| `WEB_URL` | Yes | — | Frontend URL (for CORS) |
| `CLERK_SECRET_KEY` | Yes | — | Clerk backend API key |
| `CLERK_PUBLISHABLE_KEY` | Yes | — | Clerk frontend key (for JWT validation) |
| `R2_ENDPOINT` | No | — | S3-compatible storage endpoint |
| `R2_ACCESS_KEY_ID` | No | — | R2/MinIO access key |
| `R2_SECRET_ACCESS_KEY` | No | — | R2/MinIO secret key |
| `R2_BUCKET_NAME` | No | `aivideo-assets` | Storage bucket name |
| `ANTHROPIC_API_KEY` | No | — | Global Claude API key |
| `OPENAI_API_KEY` | No | — | Global OpenAI API key |
| `AI_PROVIDER` | No | `claude` | Primary AI provider |
| `PROVIDER_ENCRYPTION_SECRET` | No | `dev-secret` | Key encryption secret |
| `LOG_LEVEL` | No | `info` | Pino log level |
| `LOKI_URL` | No | `http://loki:3100` | Loki endpoint for pino-loki transport |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | `http://localhost:4318` | OpenTelemetry OTLP HTTP endpoint |
| `METRICS_AUTH_TOKEN` | No | — | Bearer token for `/api/metrics` access |
| `NODE_ENV` | No | `development` | Environment mode |

### Web Environment (`apps/web/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Yes | Clerk frontend key |
| `CLERK_SECRET_KEY` | Yes | Clerk backend key (for RSC auth) |
| `NEXT_PUBLIC_API_URL` | No | API base URL (defaults to same-origin) |

### Python Environment

Python workers read from the same `.env` file via `python-dotenv`. Key variables:

| Variable | Required | Description |
|---|---|---|
| `AI_PROVIDER` | No | Comma-separated provider priority |
| `ANTHROPIC_API_KEY` | No | Claude API key |
| `OPENAI_API_KEY` | No | OpenAI API key |
| `TEMPORAL_HOST` | No | Temporal server address |
| `R2_*` | No | Object storage credentials |

---

## Service Dependencies

### PostgreSQL

**Local connection:**
```bash
psql postgresql://postgres:postgres@localhost:5432/aivideo
```

**Key commands:**
```bash
# Reset database (DANGER: destroys all data)
pnpm --filter @ai-video-editor/api db:reset

# Generate migration from schema changes
pnpm --filter @ai-video-editor/api db:generate

# Run pending migrations
pnpm --filter @ai-video-editor/api db:migrate

# Open Drizzle Studio (GUI for DB)
pnpm --filter @ai-video-editor/api db:studio
```

**Default local config:**
- Host: `localhost`
- Port: `5432`
- Database: `aivideo`
- Username: `postgres`
- Password: `postgres`

### Redis

**Local connection:**
```bash
redis-cli -h localhost -p 6379
```

**Useful commands:**
```bash
# Check cache keys
KEYS projects:list:*

# Clear all cache (development only)
FLUSHALL

# Monitor Redis commands
MONITOR
```

### Temporal

**Temporal UI:** `http://localhost:8088`

**Useful commands:**
```bash
# List workflows
temporal workflow list

# Describe a workflow
temporal workflow describe --workflow-id <id>

# Query workflow progress
temporal workflow query --workflow-id <id> --query-type getProgress
```

**Temporal worker (local development):**
```bash
cd services
python orchestrator.py --reference ./test_assets/ref.mp4 --song ./test_assets/song.mp3 --clips ./test_assets/clips/ --output ./output.mp4 --tier full_remix
```

---

## Running the Application

### Development Mode

```bash
pnpm dev
```

Starts all packages in watch mode. Changes to TypeScript files are automatically recompiled.

### Running Individual Packages

```bash
# API only
pnpm --filter @ai-video-editor/api dev

# Web only
pnpm --filter @ai-video-editor/web dev

# Shared types watch
pnpm --filter @ai-video-editor/shared-types dev
```

### Running Python Workers Locally

```bash
# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows

# Run ingest worker
python -m ingest_worker

# Run render worker
python -m render_worker

# Or use the orchestrator for end-to-end pipeline
python services/orchestrator.py --reference <path> --song <path> --clips <dir> --output <path> --tier <tier>
```

### Running with Docker Compose (Full Stack)

```bash
docker compose -f infra/docker/docker-compose.yml up --build
```

This builds and runs the complete stack including:
- API (Node.js)
- Web (Next.js)
- PostgreSQL
- Redis
- Temporal
- Python workers (2 replicas each)

---

## Development Workflows

### Adding a New API Endpoint

1. **Define schema** in `packages/shared-types/src/schemas.ts`
2. **Add route handler** in `apps/api/src/routes/<module>.ts`
3. **Add tests** in `apps/api/src/test/<module>.test.ts`
4. **Export types** from `packages/shared-types/src/index.ts` if needed
5. **Update API docs** in `docs/API.md`

### Adding a New Database Table

1. **Define schema** in `apps/api/src/db/schema.ts`
2. **Generate migration**:
   ```bash
   pnpm --filter @ai-video-editor/api db:generate
   ```
3. **Run migration**:
   ```bash
   pnpm --filter @ai-video-editor/api db:migrate
   ```
4. **Update queries** in route handlers

### Adding a New Effect Type

Effects require changes across three layers:

1. **Shared schema** (`packages/shared-types/src/effects.ts`)
   - Add Zod schema for effect parameters
2. **Web preview** (`apps/web/src/components/editor/canvas/`)
   - Add React component for effect preview
3. **Python render** (`services/render-worker/src/render_worker/`)
   - Add FFmpeg filter chain implementation
4. **Tests** for all three layers

### Adding a New Worker

1. Create `services/<name>-worker/` with `pyproject.toml`
2. Add `shared-py` as a workspace dependency
3. Implement worker logic in `src/<name>_worker/`
4. Add Modal deployment in `infra/modal/`
5. Register Temporal activity in `infra/temporal/activities.py`
6. Register in `services/orchestrator.py`

---

## Debugging

### API Debugging

**Attach debugger to running API:**

```bash
# Start API with Node inspector
node --inspect apps/api/dist/index.js
```

Then attach in VS Code using the "Node.js: Attach" launch configuration.

**Enable verbose logging:**
```bash
LOG_LEVEL=debug pnpm --filter @ai-video-editor/api dev
```

**Trace database queries:**
Set `LOG_LEVEL=debug` and Drizzle will log all SQL queries.

### Web Debugging

**Next.js source maps:**
Source maps are enabled by default in development. Use Chrome DevTools or VS Code debugger.

**React DevTools:**
Install the React DevTools browser extension for component inspection.

**API request tracing:**
All API responses include `x-request-id` header. Search logs by request ID:
```bash
# If running with docker
docker compose logs api | grep "req_abc123"
```

### Python Debugging

**Run with pdb:**
```python
import pdb; pdb.set_trace()
```

**VS Code launch configuration:**
```json
{
  "name": "Python: Current File",
  "type": "python",
  "request": "launch",
  "program": "${file}",
  "console": "integratedTerminal"
}
```

**Structured logging:**
All Python workers use structured JSON logging. Filter by component:
```bash
python services/orchestrator.py ... | jq 'select(.component == "render_worker")'
```

### Temporal Debugging

**View workflow history in Temporal UI:**
1. Open `http://localhost:8088`
2. Find your workflow by ID
3. Examine each activity execution, inputs, and outputs

**Query running workflow:**
```bash
temporal workflow query --workflow-id <id> --query-type getProgress
```

**Signal workflow (for assisted mode):**
```bash
temporal workflow signal --workflow-id <id> --name cutlistApproved --input '{"cutList": {...}}'
```

---

## Common Issues

### "pnpm install" fails with EACCES

**Cause**: Permission issues with pnpm store.

**Fix**:
```bash
pnpm config set store-dir ~/.pnpm-store
pnpm install
```

### "CLERK_JWT_KEY is required" error

**Cause**: Missing Clerk secret key.

**Fix**: Ensure `CLERK_SECRET_KEY` is set in `apps/api/.env` and `CLERK_PUBLISHABLE_KEY` is set in both API and web `.env` files.

### Database connection refused

**Cause**: PostgreSQL container not running.

**Fix**:
```bash
docker compose -f infra/docker/docker-compose.yml up -d postgres
# Wait 10 seconds for initialization
pnpm --filter @ai-video-editor/api db:migrate
```

### "Temporal workflow failed to start"

**Cause**: Temporal server not running or worker not registered.

**Fix**:
```bash
# Check Temporal is running
docker compose -f infra/docker/docker-compose.yml ps temporal

# Check Temporal UI for worker registration
open http://localhost:8088
```

### Redis connection timeout

**Cause**: Redis container not running or wrong URL.

**Fix**:
```bash
docker compose -f infra/docker/docker-compose.yml up -d redis
redis-cli ping  # Should return PONG
```

### Python import errors

**Cause**: Virtual environment not activated or packages not installed.

**Fix**:
```bash
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
python -m pip install -e services/shared-py -e services/ingest-worker -e services/style-worker -e services/reason-worker -e services/render-worker
```

### "Rate limit exceeded" during development

**Cause**: Default rate limits are low for rapid testing.

**Fix**: Set `NODE_ENV=test` in `.env` to increase limits to 10,000/min:
```bash
NODE_ENV=test pnpm --filter @ai-video-editor/api dev
```

### TypeScript "Cannot find module" errors

**Cause**: Shared types package not built.

**Fix**:
```bash
pnpm --filter @ai-video-editor/shared-types build
```

### Uploads fail with 403 from R2

**Cause**: Presigned URL expired or CORS not configured.

**Fix**:
- Check `R2_ENDPOINT` is correct
- Verify CORS configuration on bucket (allow `PUT` from `http://localhost:3000`)
- Check that presigned URL is used within 5 minutes

### Slow request warnings in logs

**Cause**: Expected during development. The `SLOW_REQUEST_MS` threshold is 500ms.

**Fix**: No action needed in development. In production, investigate with:
- Database query analysis (`EXPLAIN ANALYZE`)
- Redis latency checks
- Temporal workflow duration metrics

---

## Project Structure Deep Dive

### Monorepo Organization

```
ai_video_editor/
├── apps/                          # Application packages
│   ├── api/                       # Fastify backend
│   │   ├── src/
│   │   │   ├── routes/            # HTTP route handlers
│   │   │   ├── middleware/        # Auth, validation
│   │   │   ├── services/          # Business logic (AI, queue, storage)
│   │   │   ├── lib/               # Utilities (cache, errors, redis)
│   │   │   ├── db/                # Drizzle schema and connection
│   │   │   └── test/              # Vitest test suite
│   │   ├── vitest.config.ts       # Test config with coverage thresholds
│   │   └── package.json
│   ├── web/                       # Next.js frontend
│   │   ├── src/
│   │   │   ├── app/               # App Router pages
│   │   │   ├── components/        # React components
│   │   │   │   ├── dashboard/     # Project list, create dialog
│   │   │   │   ├── editor/        # Main editor UI
│   │   │   │   ├── settings/      # Provider key manager
│   │   │   │   └── ui/            # shadcn/ui components
│   │   │   ├── hooks/             # Custom React hooks
│   │   │   ├── lib/               # API client, utilities
│   │   │   └── types/             # TypeScript type extensions
│   │   └── package.json
│   └── desktop/                   # Tauri desktop app (experimental)
├── packages/                      # Shared packages
│   ├── shared-types/              # Zod schemas, enums, effects
│   │   └── src/
│   │       ├── index.ts           # Re-exports
│   │       ├── enums.ts           # Constants and enums
│   │       ├── schemas.ts         # Zod validation schemas
│   │       ├── effects.ts         # Video effect definitions
│   │       └── errors.ts          # Error codes and helpers
│   ├── eslint-config/             # Shared ESLint configuration
│   └── ui/                        # Shared UI components (if any)
├── services/                      # Python workers
│   ├── ingest-worker/             # Media probing, beat/shot detection
│   ├── style-worker/              # LUT, transition, text, camera analysis
│   ├── reason-worker/             # Cutlist generation, clip ranking
│   ├── render-worker/             # FFmpeg video compilation
│   ├── upscale-worker/            # Post-render upscaling
│   ├── shared-py/                 # Shared Python library
│   │   └── src/shared_py/
│   │       ├── models.py          # Pydantic models
│   │       ├── logging_config.py  # Structured logging
│   │       └── ai_providers/      # AI provider abstraction
│   └── orchestrator.py            # Standalone pipeline CLI
├── infra/                         # Infrastructure
│   ├── docker/                    # Docker Compose and Dockerfiles
│   ├── temporal/                  # Temporal workflows and activities
│   ├── modal/                     # Modal.com deployment scripts
│   └── terraform/                 # Infrastructure as code (planned)
├── tests/                         # Python integration tests
├── docs/                          # Documentation
└── package.json                   # Root workspace configuration
```

### Key Files

| File | Purpose |
|---|---|
| `package.json` | Root workspace config, scripts, dependencies |
| `turbo.json` | Turborepo pipeline configuration |
| `pnpm-workspace.yaml` | Workspace package glob patterns |
| `apps/api/src/app.ts` | Fastify app factory — registers all plugins and routes |
| `apps/api/src/db/schema.ts` | Drizzle ORM schema definition |
| `apps/api/src/test/setup.ts` | Central Vitest mocks (Clerk, DB, Redis, etc.) |
| `apps/web/src/app/layout.tsx` | Root layout — ClerkProvider, ThemeProvider |
| `packages/shared-types/src/index.ts` | Shared types re-export barrel |
| `services/orchestrator.py` | Standalone pipeline for local testing |

---

## Next Steps

- Read [`ARCHITECTURE.md`](./ARCHITECTURE.md) for system design details
- Read [`TESTING.md`](./TESTING.md) for testing patterns and how to write tests
- Read [`API.md`](./API.md) for complete endpoint reference
- Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) for contribution guidelines
