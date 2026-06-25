# AI Video Editor — Reference Style Matching

[![License: ELv2](https://img.shields.io/badge/License-Elastic_v2-blue.svg)](https://www.elastic.co/licensing/elastic-license)
[![CI](https://github.com/h2m6jcm94s-eng/ai-video-editor/actions/workflows/ci.yml/badge.svg)](https://github.com/h2m6jcm94s-eng/ai-video-editor/actions/workflows/ci.yml)
[![API Tests](https://img.shields.io/badge/API%20Tests-Vitest-brightgreen)](./apps/api/src/test)
[![Python Tests](https://img.shields.io/badge/Python%20Tests-pytest-brightgreen)](./tests)

> **Claude Code for video editing.** AI generates a working baseline from a reference video + song + clips + style tier. Newbies hit render and ship. Power users refine via prompts and manual controls.

## See it in action

### Dashboard

<div align="center">
  <img src="./docs/assets/dashboard-car-meet.png" alt="Glassmorphic dashboard with the Car Meet Promo project" width="720" />
  <br />
  <em>Dark glass cards, animated stats, and a focused project list — here with the Car Meet Promo example.</em>
</div>

### Start a project

<div align="center">
  <img src="./docs/assets/create-project-dialog.png" alt="Create project dialog" width="520" />
  <br />
  <em>Pick a name, style tier, and edit mode; the AI builds the first cut in seconds.</em>
</div>

### Car meet example — reference → result

This is a real run through the pipeline: a car-meet reference video, three raw clips, and a CC0 song from Freesound. The AI built the cutlist and rendered the 9:16 result below.

<div align="center">
  <table>
    <tr>
      <td align="center">
        <video src="./docs/assets/car-meet/reference.mp4" controls width="320" />
        <br />
        <strong>Reference video</strong>
      </td>
      <td align="center">
        <video src="./docs/assets/car-meet/result.mp4" controls width="320" />
        <br />
        <strong>AI-edited result</strong>
      </td>
    </tr>
  </table>
  <p>
    The AI studies the reference's beat grid, cuts, and motion, then compiles your clips into a matching 9:16 video.
  </p>
</div>

> The source clips and song are in <a href="./docs/assets/car-meet">docs/assets/car-meet</a> so you can reproduce the pipeline locally.

## Table of Contents

- [What It Does](#what-it-does)
- [5-Tier StyleTier Ladder](#5-tier-styletier-ladder)
- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Development](#development)
- [Testing](#testing)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [In-App Key Entry](#in-app-key-entry)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## What It Does

1. Upload a **reference video** — the style you want to match (cuts, color, text, transitions).
2. Upload your **clips** — the footage to edit.
3. Upload a **song** — the music to sync to.
4. Pick a **style tier** from the 5-tier ladder.
5. Hit render, or prompt-edit the cut list until it's perfect.

The AI analyzes the reference video to extract:
- **Beat grid** — Musical beats, downbeats, and sections
- **Shot boundaries** — Cut points and transition types
- **Color grading** — LUT extraction for color matching
- **Text overlays** — Title styles and positioning
- **Camera motion** — Pan, tilt, push patterns
- **Effects** — Transitions, zooms, shakes

Then it generates a **cutlist** — a structured editing timeline — and compiles the final video with FFmpeg.

---

## 5-Tier StyleTier Ladder

| Tier | What Runs | When to Use |
|------|-----------|-------------|
| `cuts_only` | Beat detect + shot detect → AI cut list | "Just sync my clips to the beat" |
| `color_grade` | + LUT extraction from reference | "Match the reference's color only" |
| `with_text` | + Text overlay extraction (PaddleOCR) | "Ad-style titles like the reference" |
| `with_effects` | + Transition classifier + camera motion + SFX | "Borrow the reference's edit feel" |
| `full_remix` | All above + manual effects, multi-song, prompt edits | "AI baseline, now I'm directing" |

---

## Quick Start

### Prerequisites

- Node.js 20+ and pnpm 9.15+
- Python 3.11+ and uv
- Docker and Docker Compose

### 1. Install Dependencies

```bash
# Clone
git clone <repo-url>
cd ai_video_editor

# JavaScript dependencies
pnpm install

# Python dependencies (uv workspace)
uv sync
```

### 2. Start Infrastructure

```bash
pnpm infra:up
```

This starts PostgreSQL, Redis, Temporal, Temporal UI, and MinIO with the `ai-video-editor` bucket pre-created.

Services:
- PostgreSQL 16: `localhost:5432`
- Redis 7: `localhost:6379`
- Temporal gRPC: `localhost:7233`
- Temporal UI: `http://localhost:8080`
- MinIO S3 API: `localhost:9000`
- MinIO Console: `http://localhost:9001`

### 3. Configure Environment

Create `apps/api/.env.local` with at least the following values:

```bash
DATABASE_URL=postgresql://ave:ave@localhost:5432/ave
REDIS_URL=redis://localhost:6379
TEMPORAL_HOST=localhost:7233
WEB_URL=http://localhost:3000
CLERK_SECRET_KEY=sk_test_...
CLERK_PUBLISHABLE_KEY=pk_test_...
INTERNAL_WORKER_TOKEN=dev-internal-token
R2_ENDPOINT=http://localhost:9000
R2_ACCESS_KEY_ID=minioadmin
R2_SECRET_ACCESS_KEY=minioadmin
R2_BUCKET_NAME=ai-video-editor
```

### 4. Run Migrations

```bash
pnpm --filter @ai-video-editor/api db:migrate
```

### 5. Start the Full Dev Stack

One command starts the workers, API, and web frontend in a single terminal. It also brings up Docker infrastructure and runs migrations if they haven't been done yet.

```bash
pnpm dev:full
```

- API: http://localhost:4000
- Web: http://localhost:3000
- Temporal UI: http://localhost:8080

Press `Ctrl+C` to stop everything gracefully. If you ever need to force-stop:

```bash
pnpm dev:stop
```

> **Why one command?** Previously you had to open separate terminals for workers (`pnpm workers`) and the dev server (`pnpm dev`). `pnpm dev:full` runs everything together, color-codes the logs, and writes per-service logs to `.tmp/dev-logs/` for quiet inspection.

Open `http://localhost:3000`, sign in with Clerk, and add your AI provider keys in **Settings → API Keys**.

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────────────────────────────┐
│   Next.js   │────▶│   Fastify   │────▶│  PostgreSQL  │  Redis  │  Temporal      │
│   (Web)     │◀────│   (API)     │◀────│  (Drizzle)   │ (Cache) │  (Workflows)   │
└─────────────┘     └──────┬──────┘     └─────────────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │  Ingest  │ │  Render  │ │  Future  │
        │  Worker  │ │  Worker  │ │  Workers │
        │(Temporal)│ │(Temporal)│ │(Temporal)│
        └──────────┘ └──────────┘ └──────────┘
```

Workers connect to Temporal on `localhost:7233`:
- **Ingest Worker** listens on task queue `ingest` — probes uploaded media and reports metadata back to the API.
- **Render Worker** listens on task queue `video-render-queue` — downloads clips, compiles the timeline with FFmpeg, uploads the output MP4, and finalizes the render job.

All worker→API calls use the internal route prefix `/api/internal` protected by `x-internal-token`.

**Detailed architecture:** See [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)

### Key Design Principles

1. **Issue-first development** — Every change starts with a GitHub issue
2. **Small PRs** — One concern per PR, reviewable in under 15 minutes
3. **Shared schemas** — Zod schemas in `packages/shared-types` are the single source of truth
4. **No state management library** — Vanilla React `useState`/`useReducer` is sufficient
5. **Durable execution** — Temporal workflows survive crashes and resumes

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, Tailwind CSS, shadcn/ui, Clerk |
| Backend | Fastify 4, Drizzle ORM, PostgreSQL, Redis, MinIO/R2 |
| Orchestration | Temporal |
| AI | Claude 3.5 Sonnet, GPT-4o, Whisper, Gemini, Groq |
| Render | FFmpeg, PyAV |
| Workers | Python 3.11, librosa, PySceneDetect, TransNet V2 |
| Observability | Grafana, Loki, Tempo, Prometheus, OTel Collector, GlitchTip |
| Language | TypeScript 5.4, Python 3.11 |
| Package Manager | pnpm 9.15 (JS), uv (Python) |
| Testing | Vitest (JS), pytest (Python) |
| CI/CD | GitHub Actions |

---

## Project Structure

```
ai_video_editor/
├── apps/
│   ├── api/              # Fastify 4 backend
│   ├── web/              # Next.js 15 frontend
│   └── desktop/          # Tauri desktop app (experimental)
├── packages/
│   ├── shared-types/     # Zod schemas, enums, effects
│   └── eslint-config/    # Shared lint rules
├── services/             # Python uv workspace
│   ├── ingest-worker/    # Temporal worker — media probing
│   ├── style-worker/     # LUT, transition, text, camera analysis
│   ├── reason-worker/    # Cutlist generation, clip ranking
│   ├── render-worker/    # Temporal worker — FFmpeg compilation
│   ├── upscale-worker/   # Post-render upscaling
│   ├── shared-py/        # Shared Python library
│   └── orchestrator.py   # Standalone pipeline CLI
├── infra/
│   ├── local/            # Local Docker Compose stack
│   ├── docker/           # Production Dockerfiles
│   ├── observability/    # LGTM stack: Grafana + Loki + Tempo + Prometheus
│   ├── temporal/         # Temporal server config
│   ├── modal/            # Modal.com deployment scripts
│   └── terraform/        # Infrastructure as code
├── e2e/                  # Playwright end-to-end tests
├── tests/                # Python integration tests
├── docs/                 # Documentation
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DEVELOPMENT.md
│   ├── TESTING.md
│   └── DEPLOYMENT.md
└── package.json
```

---

## Development

### Running the Application

```bash
pnpm dev:full      # Start infrastructure, workers, API, and web in one command
pnpm dev:stop      # Stop the full stack
pnpm obs:up        # Start observability stack (Grafana, Loki, Tempo, etc.)
```

`pnpm dev:full` also handles `pnpm infra:up` and migrations if they haven't been run yet.

### Running Workers

The full dev stack already starts all workers. To run them separately:

```bash
# Start all workers under one supervisor (recommended)
pnpm workers

# Or run individual workers
uv run python -m ingest_worker
uv run python -m reason_worker
uv run python -m render_worker
uv run python -m style_worker
uv run python -m segment_worker
```

### Running Tests

```bash
# API tests
pnpm --filter @ai-video-editor/api test
pnpm --filter @ai-video-editor/api test:coverage

# Web tests
pnpm --filter @ai-video-editor/web test

# Python tests
uv run pytest tests/

# E2E tests (infrastructure + workers must be running)
pnpm e2e:headed
```

### Code Quality

```bash
pnpm typecheck     # Type-check all packages
pnpm lint          # ESLint all packages
pnpm format        # Prettier format
```

**Detailed setup:** See [`docs/DEVELOPMENT.md`](./docs/DEVELOPMENT.md)

---

## Testing

### Test Philosophy

- **Unit tests** for API routes, services, and middleware (Vitest)
- **Component tests** for critical UI paths (Vitest + jsdom)
- **Integration tests** for Python worker pipelines (pytest)
- **E2E tests** for critical user journeys (Playwright)

### E2E Runbook

Local E2E tests cover two scenarios:
- **Scenario A**: prompt + song only renders a valid 9:16 MP4.
- **Scenario B**: reference-driven render produces a measurably different cut-list than Scenario A.

Run order:
```bash
pnpm infra:up
pnpm workers
pnpm e2e:headed
```

A `NOT_PROVEN` wedge verdict is logged but does **not** fail the test — it is a product finding. Do not tag `v0.4.0` until the reference pipeline produces measurably different cut-lists.

### Coverage Thresholds (Enforced in CI)

| Metric | Threshold |
|---|---|
| Statements | 70% |
| Branches | 55% |
| Functions | 60% |
| Lines | 70% |

Current API coverage: **86.79% statements, 76.67% branches**

**Testing guide:** See [`docs/TESTING.md`](./docs/TESTING.md)

---

## API Reference

The API is a RESTful HTTP API built on Fastify 4. All endpoints (except health checks) require Clerk JWT authentication.

**Key endpoints:**

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List user projects |
| `POST` | `/api/projects` | Create project |
| `GET` | `/api/projects/:id` | Get project |
| `POST` | `/api/projects/:id/prompt` | AI prompt edit |
| `POST` | `/api/uploads/presigned` | Generate upload URL |
| `POST` | `/api/renders` | Start render |
| `GET` | `/api/progress/:jobId/events` | SSE progress stream |
| `POST` | `/api/log` | Frontend log ingestion |

**OpenAPI 3.0.3 spec:** [`apps/api/openapi.yaml`](./apps/api/openapi.yaml)  
**Complete reference:** See [`docs/API.md`](./docs/API.md)

---

## Deployment

### Docker Compose (Recommended for Self-Hosted)

```bash
# Local / staging stack (Postgres, Redis, Temporal, MinIO)
pnpm infra:up

# Observability stack (Grafana, Loki, Tempo, Prometheus, OTel Collector, Promtail)
pnpm obs:up
```

Production builds use the Dockerfiles in `infra/docker/`.

### Modal.com (Serverless Workers)

```bash
modal deploy infra/modal/render_modal.py
modal deploy infra/modal/ingest_modal.py
```

### Production Checklist

- [ ] Replace XOR encryption with AES-256-GCM
- [ ] Use secrets manager for provider keys
- [ ] Enable PostgreSQL SSL
- [ ] Configure CDN for video delivery
- [ ] Set up monitoring and alerting
- [ ] Enable database backups

**Deployment guide:** See [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md)

---

## In-App Key Entry

AI provider keys are stored per-user in the `provider_keys` table, encrypted at rest. The app falls back to env vars for admin/global keys. If a feature needs a missing key, the UI shows a "Connect [Provider]" CTA instead of crashing.

Supported providers: Anthropic (Claude), OpenAI (GPT-4o, Whisper), Gemini, Groq, Kimi, Qwen, OpenRouter.

---

## Troubleshooting

### "pnpm install fails with EACCES"

```bash
pnpm config set store-dir ~/.pnpm-store
pnpm install
```

### "Database connection refused"

```bash
pnpm infra:up
pnpm --filter @ai-video-editor/api db:migrate
```

### "Temporal workflow failed to start"

```bash
pnpm infra:up
# Verify Temporal UI at http://localhost:8080
```

Make sure the workers are running and registered on their task queues:
```bash
pnpm workers
```

### "Rate limit exceeded during development"

```bash
NODE_ENV=test pnpm --filter @ai-video-editor/api dev
```

### "Worker fails with missing environment variables"

Make sure `apps/api/.env.local` is sourced before starting workers. Required variables include:
- `TEMPORAL_HOST`
- `INTERNAL_WORKER_TOKEN`
- `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`
- `API_BASE` or inferred API URL

Start workers with the supervisor (loads `apps/api/.env.local` automatically):
```bash
pnpm workers
```

**More issues:** See [`docs/DEVELOPMENT.md`](./docs/DEVELOPMENT.md)

---

## Contributing

We welcome contributions! Please read our [Contributing Guide](./CONTRIBUTING.md) for details on:

- Development setup
- Code style and conventions
- Testing requirements
- Pull request process
- Issue-first workflow

### Quick Contributing Workflow

1. **Open an issue** describing the bug/feature
2. **Branch from main**: `feat/123-short-description`
3. **Write code + tests**
4. **Run checks**: `pnpm typecheck`, `pnpm test`
5. **Open PR** referencing the issue: `Closes #123`
6. **Merge when CI is green**

---

## License

Elastic License 2.0. Commercial SaaS use requires written permission.

See [LICENSE](./LICENSE) for full terms.

---

## Resources

- [Architecture Deep Dive](./docs/ARCHITECTURE.md)
- [API Reference](./docs/API.md)
- [Development Guide](./docs/DEVELOPMENT.md)
- [Testing Guide](./docs/TESTING.md)
- [Deployment Guide](./docs/DEPLOYMENT.md)
- [Contributing Guide](./CONTRIBUTING.md)
- [Security Policy](./SECURITY.md)
