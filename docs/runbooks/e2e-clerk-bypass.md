# Runbook: Clerk-Free Local Engine + E2E Pipeline Replication

> Reproduce the end-to-end pipeline that produces `output-A.mp4` and `output-B.mp4` without signing into Clerk.

This runbook covers the **Clerk auth bypass** path used for local E2E development. When `DISABLE_CLERK_AUTH=1` is set, the API and web middleware inject a fixed E2E test user so Playwright can drive the UI without a real Clerk account.

---

## Table of Contents

- [Goal](#goal)
- [Prerequisites](#prerequisites)
- [Required Environment Variables](#required-environment-variables)
- [Step 1 — Start Infrastructure](#step-1--start-infrastructure)
- [Step 2 — Start the Dev Server with Auth Bypass](#step-2--start-the-dev-server-with-auth-bypass)
- [Step 3 — Start the Workers](#step-3--start-the-workers)
- [Step 4 — Run the Pipeline Spec](#step-4--run-the-pipeline-spec)
- [Expected Artifacts](#expected-artifacts)
- [Troubleshooting](#troubleshooting)
- [How the Bypass Works](#how-the-bypass-works)

---

## Goal

Run `e2e/specs/pipeline.spec.ts` headlessly (or headed) and produce two valid rendered MP4s:

- `e2e/output-A.mp4` — prompt + song render.
- `e2e/output-B.mp4` — reference-driven render that should differ measurably from Scenario A.

The run is considered successful when:

1. Playwright reports all pipeline tests passing.
2. Both MP4s exist, have a positive duration, and are valid H.264/AAC videos.
3. `e2e/wedge-report.json` is written (verdict may be `PROVEN` or `NOT_PROVEN`; the test passes either way).
4. `e2e/ffmpeg-stderr.log` is empty or absent after a clean run.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Node.js | 20.x LTS |  |
| pnpm | 9.15.x | Enforced by `packageManager` |
| Python | 3.11+ | Worker runtime |
| Docker + Docker Compose | 24.x+ / 2.x+ | For Postgres, Redis, Temporal, MinIO |
| FFmpeg | Latest | Used by workers and the E2E ffprobe helper |
| Groq API key | — | Set `AI_PROVIDER=groq` and `GROQ_API_KEY` |

Install JS dependencies once:

```bash
pnpm install
```

Create the Python virtual environment and install worker packages:

```bash
# On macOS / Linux
uv sync

# On Windows (the repository uses a committed .venv)
# .venv/Scripts/python -m ingest_worker  # shown in worker steps below
```

Download E2E fixtures once:

```bash
pnpm fixtures
```

This populates `e2e/fixtures/` with `reference.mp4`, `clip-1.mp4`, `clip-2.mp4`, `clip-3.mp4`, and `song.mp3`.

---

## Required Environment Variables

Auth bypass requires the flag in **three** places so that API routes, server components, client components, and Playwright all agree.

### 1. Root `.env` (workers read this)

```bash
# AI provider used by the cutlist generator
AI_PROVIDER=groq
GROQ_API_KEY=<your-groq-key>

# Shared infrastructure
DATABASE_URL=postgresql://ave:ave@localhost:5432/ave
REDIS_URL=redis://localhost:6379
TEMPORAL_HOST=localhost:7233
INTERNAL_WORKER_TOKEN=dev-internal-token

# Object storage (local MinIO)
R2_ENDPOINT=http://localhost:9000
R2_ACCESS_KEY_ID=minioadmin
R2_SECRET_ACCESS_KEY=minioadmin
R2_BUCKET_NAME=ai-video-editor
```

### 2. `apps/api/.env.local`

```bash
DATABASE_URL=postgresql://ave:ave@localhost:5432/ave
REDIS_URL=redis://localhost:6379
TEMPORAL_HOST=localhost:7233
WEB_URL=http://localhost:3000
INTERNAL_WORKER_TOKEN=dev-internal-token
R2_ENDPOINT=http://localhost:9000
R2_ACCESS_KEY_ID=minioadmin
R2_SECRET_ACCESS_KEY=minioadmin
R2_BUCKET_NAME=ai-video-editor
LOG_LEVEL=info

# Auth bypass
DISABLE_CLERK_AUTH=1
```

> Note: `CLERK_SECRET_KEY` and `CLERK_PUBLISHABLE_KEY` are not required when `DISABLE_CLERK_AUTH=1`.

### 3. `apps/web/.env.local`

```bash
NEXT_PUBLIC_API_URL=http://localhost:4000

# Auth bypass — must be public so the client-side new-project flow can read it
NEXT_PUBLIC_DISABLE_CLERK_AUTH=1
DISABLE_CLERK_AUTH=1
```

### 4. `e2e/.env.e2e`

```bash
DISABLE_CLERK_AUTH=1
E2E_BASE_URL=http://localhost:3000
```

> `E2E_TEST_USER_EMAIL` and `E2E_TEST_USER_PASSWORD` are ignored when `DISABLE_CLERK_AUTH=1`.

---

## Step 1 — Start Infrastructure

```bash
pnpm infra:up
```

This starts the core local stack from `infra/local/docker-compose.yml`:

| Service | Endpoint |
|---|---|
| PostgreSQL 16 | `localhost:5432` (db `ave`, user `ave`, password `ave`) |
| Redis 7 | `localhost:6379` |
| Temporal gRPC | `localhost:7233` |
| Temporal Web UI | `http://localhost:8233` |
| MinIO S3 API | `localhost:9000` |
| MinIO Console | `http://localhost:9001` (default `minioadmin` / `minioadmin`) |

Verify the bucket exists:

```bash
# MinIO mc example
mc alias set local http://localhost:9000 minioadmin minioadmin
mc ls local/ai-video-editor
```

Run DB migrations if the schema has changed:

```bash
pnpm --filter @ai-video-editor/api db:migrate
```

---

## Step 2 — Start the Dev Server with Auth Bypass

Export the bypass flag and start the dev server. The `E2E=1` flag is required because the web server and tests rely on E2E-specific behavior.

```bash
# On macOS / Linux
export E2E=1
export DISABLE_CLERK_AUTH=1
pnpm dev
```

```powershell
# On Windows PowerShell
$env:E2E=1
$env:DISABLE_CLERK_AUTH=1
pnpm dev
```

Wait until you see:

- API ready on `http://localhost:4000`
- Web ready on `http://localhost:3000`

You can sanity-check the bypass by opening `http://localhost:3000/dashboard` in an incognito window — it should load without redirecting to `/sign-in`.

---

## Step 3 — Start the Workers

Start the ingest and render workers in **separate** terminals. Both need the root `.env` sourced.

### Ingest worker

```bash
# On macOS / Linux
set -a && source .env && set +a
uv run python -m ingest_worker
```

```powershell
# On Windows
.venv\Scripts\python.exe -m ingest_worker
```

### Render worker

```bash
# On macOS / Linux
set -a && source .env && set +a
uv run python -m render_worker
```

```powershell
# On Windows
.venv\Scripts\python.exe -m render_worker
```

Verify both workers register with Temporal at `http://localhost:8233`.

---

## Step 4 — Run the Pipeline Spec

With infrastructure, the dev server, and both workers running, run the pipeline spec in a fourth terminal.

### Headless (default)

```bash
# On macOS / Linux
export DISABLE_CLERK_AUTH=1
pnpm e2e:pipeline:headless
```

```powershell
# On Windows
$env:DISABLE_CLERK_AUTH=1
pnpm e2e:pipeline:headless
```

### Headed (useful for debugging)

```bash
# On macOS / Linux
export DISABLE_CLERK_AUTH=1
export E2E_HEADED=1
pnpm e2e:pipeline
```

```powershell
# On Windows
$env:DISABLE_CLERK_AUTH=1
$env:E2E_HEADED=1
pnpm e2e:pipeline
```

The spec has a 15-minute timeout per scenario because AI cutlist generation and FFmpeg rendering are slow.

---

## Expected Artifacts

After a successful run you will find:

| File | Purpose |
|---|---|
| `e2e/output-A.mp4` | Rendered output for Scenario A (prompt + song) |
| `e2e/output-B.mp4` | Rendered output for Scenario B (reference-driven) |
| `e2e/wedge-report.json` | Wedge comparison between A and B |
| `e2e/report.json` | Playwright JSON report |
| `e2e/ffmpeg-stderr.log` | FFmpeg stderr captured on failures (should be empty) |

Verify the outputs quickly:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 e2e/output-A.mp4
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 e2e/output-B.mp4
```

Both files should report a positive duration and no errors.

### Wedge verdict

`e2e/wedge-report.json` contains a `verdict` field:

| Verdict | Meaning |
|---|---|
| `PROVEN` | Scenario B produced a measurably different cut-list than Scenario A. |
| `NOT_PROVEN` | Differences are within tolerance — the pipeline still passes, but the reference-driven differentiation is not yet strong enough for a release tag. |

A `NOT_PROVEN` result does **not** fail the E2E test; it is a product signal, not a regression.

---

## Troubleshooting

### Browser opens to `/sign-in` instead of the dashboard

- Confirm `DISABLE_CLERK_AUTH=1` is exported in the terminal running `pnpm dev`.
- Confirm `apps/web/.env.local` contains `NEXT_PUBLIC_DISABLE_CLERK_AUTH=1`.
- Restart the dev server after adding the env var.

### API returns 401 in Playwright

- Confirm `apps/api/.env.local` contains `DISABLE_CLERK_AUTH=1`.
- Confirm the dev server and API share the same env context.

### Tests time out waiting for render

- Check that both workers are running and registered in Temporal UI.
- Check `e2e/ffmpeg-stderr.log` for FFmpeg errors.
- Check the API logs for cutlist-generation errors (often an AI provider key issue).

### Stale `node.exe`, Python workers, or ports in use

After a failed or aborted run, leftover processes can hold ports 3000, 4000, 5432, 6379, 7233, 9000, or 9001.

On Windows:

```powershell
# Kill Node dev servers
Get-Process node | Stop-Process -Force

# Kill Python workers
Get-Process python | Stop-Process -Force

# Or by port
netstat -ano | findstr :3000
# taskkill /PID <pid> /F
```

On macOS / Linux:

```bash
# Kill dev servers
pkill -f "pnpm dev"
pkill -f "next dev"
pkill -f "tsx.*apps/api"

# Kill workers
pkill -f "python -m ingest_worker"
pkill -f "python -m render_worker"
```

Reset infrastructure if containers are wedged:

```bash
pnpm infra:reset
```

> `infra:reset` destroys Docker volumes and recreates the database.

### `output-A.mp4` or `output-B.mp4` is missing

- Check `e2e/reports/` for Playwright trace files.
- Inspect the render worker logs for FFmpeg failures.
- Look at `e2e/ffmpeg-stderr.log` for the most recent error.

### Wedge report shows `effectCountParity: 0`

This is a known non-blocking follow-up. The pipeline still passes as long as both videos are valid and the overall verdict is written.

---

## How the Bypass Works

1. `apps/api/src/middleware/auth.ts` checks `DISABLE_CLERK_AUTH === "1"`. If set, it skips Clerk JWT verification and assigns `request.user = { id: "e2e-test-user", email: "e2e@example.com" }`.
2. `apps/web/src/middleware.ts` and `apps/web/src/lib/auth.ts` do the same for server-side rendering.
3. `apps/web/src/app/editor/new/page.tsx` reads `NEXT_PUBLIC_DISABLE_CLERK_AUTH` to hide Clerk-dependent UI on the client.
4. `e2e/specs/auth.setup.ts` detects the flag and writes an empty `e2e/.auth/user.json` instead of performing a real sign-in.
5. Playwright then loads pages with the storage state, and the server treats every request as the same E2E test user.

Because the test user is shared, the pipeline spec runs with `workers: 1` and `fullyParallel: false` so Scenarios A and B do not race against each other.
