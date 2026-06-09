# AI Video Editor — Reference Style Matching

[![License: ELv2](https://img.shields.io/badge/License-Elastic_v2-blue.svg)](https://www.elastic.co/licensing/elastic-license)
[![CI](https://github.com/h2m6jcm94s-eng/ai-video-editor/actions/workflows/ci.yml/badge.svg)](https://github.com/h2m6jcm94s-eng/ai-video-editor/actions/workflows/ci.yml)
[![API Tests](https://img.shields.io/badge/API%20Tests-Vitest-brightgreen)](./apps/api/src/test)
[![Python Tests](https://img.shields.io/badge/Python%20Tests-pytest-brightgreen)](./tests)

> **Claude Code for video editing.** AI generates a working baseline from a reference video + song + clips + style tier. Newbies hit render and ship. Power users refine via prompts and manual controls.

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

# Python dependencies
uv venv
.venv\Scripts\python -m pip install -e services/shared-py -e services/ingest-worker -e services/style-worker -e services/reason-worker -e services/render-worker
```

### 2. Start Infrastructure

```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

This starts PostgreSQL, Redis, and Temporal.

### 3. Configure Environment

```bash
cp apps/api/.env.example apps/api/.env
# Edit apps/api/.env with your Clerk keys and database URL
```

### 4. Run Migrations

```bash
pnpm --filter @ai-video-editor/api db:migrate
```

### 5. Start Development

```bash
pnpm dev
```

Open `http://localhost:3000`, sign in with Clerk, and add your AI provider keys in **Settings → API Keys**.

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────────────────────────┐
│   Next.js   │────▶│   Fastify   │────▶│  PostgreSQL  │  Redis  │  Temporal  │
│   (Web)     │◀────│   (API)     │◀────│  (Drizzle)   │ (Cache) │ (Workflows)│
└─────────────┘     └──────┬──────┘     └─────────────────────────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Python Workers│
                    │ (FFmpeg, ML)  │
                    └──────────────┘
```

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
├── services/
│   ├── ingest-worker/    # Media probing, beat/shot detection
│   ├── style-worker/     # LUT, transition, text, camera analysis
│   ├── reason-worker/    # Cutlist generation, clip ranking
│   ├── render-worker/    # FFmpeg video compilation
│   ├── upscale-worker/   # Post-render upscaling
│   ├── shared-py/        # Shared Python library
│   └── orchestrator.py   # Standalone pipeline CLI
├── infra/
│   ├── docker/           # Docker Compose and Dockerfiles
│   ├── temporal/         # Temporal workflows and activities
│   ├── modal/            # Modal.com deployment scripts
│   └── terraform/        # Infrastructure as code
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
pnpm dev           # Start web + api + shared-types watch
pnpm typecheck     # Type-check all packages
```

### Running Tests

```bash
# API tests
pnpm --filter @ai-video-editor/api test
pnpm --filter @ai-video-editor/api test:coverage

# Web tests
pnpm --filter @ai-video-editor/web test

# Python tests
.venv\Scripts\python -m pytest tests/
```

### Code Quality

```bash
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

**Complete reference:** See [`docs/API.md`](./docs/API.md)

---

## Deployment

### Docker Compose (Recommended for Self-Hosted)

```bash
docker compose -f infra/docker/docker-compose.yml up -d
```

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
docker compose -f infra/docker/docker-compose.yml up -d postgres
pnpm --filter @ai-video-editor/api db:migrate
```

### "Temporal workflow failed to start"

```bash
docker compose -f infra/docker/docker-compose.yml up -d temporal
# Verify at http://localhost:8088
```

### "Rate limit exceeded during development"

```bash
NODE_ENV=test pnpm --filter @ai-video-editor/api dev
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
