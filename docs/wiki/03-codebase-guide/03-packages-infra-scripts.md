# Packages, Infrastructure, Scripts & Tests

This guide covers the shared code, infrastructure glue, automation scripts, root configuration, and test suites that sit outside the main applications and services.

- [Packages](#packages)
  - [`packages/shared-types/`](#packagesshared-types)
  - [`packages/eslint-config/`](#packageseslint-config)
- [Infrastructure](#infrastructure)
  - [Local stack](#local-stack)
  - [Production Dockerfiles](#production-dockerfiles)
  - [Modal.com deployments](#modalcom-deployments)
  - [Observability](#observability)
  - [Temporal](#temporal)
  - [R2 / S3 lifecycle](#r2--s3-lifecycle)
- [Scripts](#scripts)
- [Root configuration](#root-configuration)
- [End-to-end tests](#end-to-end-tests)
- [Root Python integration tests](#root-python-integration-tests)

---

## Packages

### `packages/shared-types/`

Path: `packages/shared-types/`

This is the only TypeScript package shared across the Node.js side of the repo. It is a plain Zod + TypeScript library built with `tsc`; its compiled output lands in `packages/shared-types/dist/` and is consumed by `apps/api` and `apps/web` via the workspace alias `@ai-video-editor/shared-types`.

Package manifest: `packages/shared-types/package.json`

Build / test commands:

- `pnpm --filter @ai-video-editor/shared-types build` — `tsc`
- `pnpm --filter @ai-video-editor/shared-types typecheck` — `tsc --noEmit`
- `pnpm --filter @ai-video-editor/shared-types test` — `vitest run`

#### Source files

| File | Responsibility |
|------|----------------|
| `packages/shared-types/src/index.ts` | Public barrel export. Re-exports every module and declares the canonical inferred `z.infer<>` types used by the API and web (`CutList`, `Slot`, `Overlay`, `Subtitle`, `AudioTrack`, `Effect`, `CreateProjectInput`, `RenderInput`, etc.). |
| `packages/shared-types/src/schemas.ts` | The central Zod schema definitions for API contracts and the cut-list document model. Defines `ALLOWED_MIMES`, `createProjectSchema`, `patchProjectSchema`, `presignedUploadSchema`, `cutListSchema`, `slotSchema`, `overlaySchema`, `subtitleSchema`, `audioTrackSchema`, `cutListGlobalsSchema`, `sectionMarkerSchema`, `promptEditSchema`, `createTemplateSchema`, `createRenderSchema`, `renderOptionsSchema`, `providerKeySchema`, `providerEncryptedKeySchema`, `styleGenomeSchema`, and friends. |
| `packages/shared-types/src/enums.ts` | Plain string-literal arrays for `STYLE_TIER`, `EDIT_MODE`, `ASSET_TYPE`, `PROJECT_STATUS`, `RENDER_STATUS`, plus the object array `EXPORT_PRESETS` with width/height metadata. |
| `packages/shared-types/src/effects.ts` | Discriminated-union Zod schemas for every supported visual / audio effect (`zoom_punch_in`, `focus_pull`, `freeze_frame`, `speed_ramp`, `shake`, `glitch`, `vignette`, `film_grain`, `color_pop`, `text_kinetic`, `lower_third`, `callout_arrow`, plus SFX variants). Each effect carries `id`, `startS`, `durationS` and a typed `params` object. |
| `packages/shared-types/src/errors.ts` | `API_ERROR_CODES` constant, `ApiErrorCode` / `ApiError` types, plus `isApiErrorCode()` and `createApiError()` helpers. Codes cover auth, validation, resource, conflict, provider, AI-specific, pipeline, and infrastructure categories. |
| `packages/shared-types/src/cutlist.ts` | `buildInitialCutList(assets)` — a pure function that builds a canonical starter cut list from a project's asset list. Clips become slots, a song (if present) drives duration and the music audio track, and sensible defaults (aspect ratio 9:16, tempo 120 BPM, etc.) are applied. |
| `packages/shared-types/src/schemas.test.ts` | Vitest tests validating `patchProjectSchema`, `providerEncryptedKeySchema`, and `providerKeySchema` behavior. |
| `packages/shared-types/tsconfig.json` | Composite project config; outputs declarations and JS to `dist/` with `NodeNext` resolution. |
| `packages/shared-types/vitest.config.ts` | Vitest config: Node environment, `src/**/*.test.ts` pattern. |

#### How schemas flow into API and web

1. `packages/shared-types/src/schemas.ts` defines a schema.
2. `packages/shared-types/src/index.ts` exports the schema and its inferred TypeScript type.
3. `apps/api/src/routes/*.ts` imports the schemas to parse request bodies (e.g. `createProjectSchema.safeParse(body)`).
4. `apps/web/src/hooks/useEditor.test.ts` and UI components such as `apps/web/src/components/editor/RenderOptionsDialog.tsx` import the inferred types or schemas for client-side validation and type safety.
5. `apps/api/src/test/contracts.test.ts` imports the same schemas to assert that API contracts never drift from the shared definitions.

Because the package is built with `composite: true`, both `apps/api` and `apps/web` reference it as a TypeScript project reference, giving fast incremental builds through `tsc --build` and `turbo`.

---

### `packages/eslint-config/`

Path: `packages/eslint-config/`

Shared ESLint preset used by the TypeScript apps and packages.

Files:

- `packages/eslint-config/package.json` — publishes `@ai-video-editor/eslint-config` with dependencies on `@typescript-eslint/eslint-plugin`, `@typescript-eslint/parser`, and `eslint-config-prettier`.
- `packages/eslint-config/index.js` — the actual config:
  - Parser: `@typescript-eslint/parser`
  - Extends: `eslint:recommended`, `plugin:@typescript-eslint/recommended`, `prettier`
  - Parser options: `ecmaVersion: 2022`, `sourceType: module`
  - Rules:
    - `@typescript-eslint/no-unused-vars`: warn, ignoring args starting with `_`
    - `@typescript-eslint/no-explicit-any`: warn
    - `prefer-const`: warn

Apps consume it by extending `@ai-video-editor/eslint-config` in their own ESLint config files (e.g. `packages/shared-types/.eslintrc.json`).

---

## Infrastructure

### Local stack

Path: `infra/local/docker-compose.yml`

The single-file local development dependency stack. It defines:

- `postgres` — PostgreSQL 16 (`ave/ave/ave`) on port `5432`
- `redis` — Redis 7 on port `6379`
- `temporal` — Temporal auto-setup (`1.29`) on ports `7233` (gRPC) and `8233` (metrics)
- `temporal-ui` — Temporal Web UI on port `8080`
- `minio` — S3-compatible object store on ports `9000` (API) and `9001` (console)
- `minio-init` — One-shot bucket creation / public-read policy for `ai-video-editor`

Start / stop via root `package.json` scripts:

- `pnpm infra:up`
- `pnpm infra:down`
- `pnpm infra:reset` (destroys volumes and recreates)
- `pnpm infra:logs`

---

### Production Dockerfiles

Path: `infra/docker/`

| Dockerfile | Builds |
|------------|--------|
| `infra/docker/Dockerfile.api` | Node 20 Alpine image for the Fastify API. Copies workspace metadata, builds `@ai-video-editor/shared-types` and `@ai-video-editor/api`, then runs `apps/api/dist/index.js` on port `4000`. |
| `infra/docker/Dockerfile.web` | Node 20 Alpine image for the Next.js frontend. Builds `@ai-video-editor/shared-types` and `@ai-video-editor/web`, then `pnpm start`. Accepts `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` build args. |
| `infra/docker/Dockerfile.ingest` | Python 3.10 slim image for the ingest worker. Installs FFmpeg + OpenCV system deps, then installs `shared-py` and `ingest-worker[real_structure]`. Entrypoint: `python -m ingest_worker`. |
| `infra/docker/Dockerfile.render` | Python 3.11 slim image for the render worker. Installs FFmpeg, fonts, `shared-py`, and `render-worker`. Entrypoint: `python -m render_worker`. |
| `infra/docker/Dockerfile.segment` | Python 3.11 slim image for the segment worker. Adds `git` for optional SAM3 installation (`INSTALL_SAM3=true` + `HF_TOKEN` at build time). Entrypoint: `python -m segment_worker`. |
| `infra/docker/Dockerfile.guardrails` | Python 3.11 slim image for the guardrails microservice. Installs from `services/guardrails/pyproject.toml`, sets `PYTHONPATH=/app/src`, and runs `uvicorn guardrails.main:app` on port `8000`. |

Compose orchestration: `infra/docker/docker-compose.yml` wires API, web, Redis, PostgreSQL, Temporal, Temporal UI, ingest-worker (2 replicas), render-worker (2 replicas), and segment-worker (1 replica) together with the environment variables they need.

Monitoring-only compose: `infra/docker/monitoring/docker-compose.yml` provides a standalone Prometheus + Grafana stack on ports `9090` and `3001`.

---

### Modal.com deployments

Path: `infra/modal/`

These scripts package Python workers as Modal apps for GPU/CPU cloud execution. Each one constructs a `modal.Image`, mounts the `services/shared-py/src` and relevant worker source directories, and exposes functions with Modal decorators.

| Script | Modal app | Purpose |
|--------|-----------|---------|
| `infra/modal/ingest_modal.py` | `ave-ingest` | `process_video_upload` (probe + shot detection on GPU) and `process_audio_upload` (beat detection + energy curve). Runs on `gpu="L4"`. |
| `infra/modal/render_modal.py` | `ave-render` | `render_video_job(cutlist_json, clip_paths, output_key, ...)` compiles a timeline using `render_worker.compiler`. Configured with `cpu=8`, `memory=16384`, 10-minute timeout. |
| `infra/modal/style_modal.py` | `ave-style` | `analyze_style(reference_path, tier)` extracts LUT, classifies transitions, extracts text overlays, and analyzes camera motion based on the requested `STYLE_TIER`. |
| `infra/modal/upscale_modal.py` | `ave-upscale` | `upscale_video(input_path, output_path, scale)` downloads and runs Real-ESRGAN on a Modal `L4` GPU. |

All Modal functions attach a shared `modal.Volume` named `ave-data` mounted at `/data` for intermediate files.

---

### Observability

Path: `infra/observability/`

Self-hosted LGTM + Promtail + OTel stack, documented in `infra/observability/README.md`.

Compose: `infra/observability/docker-compose.yml`

- Grafana — port `3001` (default admin/admin)
- Prometheus — port `9090`
- Loki — port `3100`
- Tempo — port `3200`, OTLP gRPC `4317`
- OTel Collector — OTLP gRPC `4317` + HTTP `4318`
- Promtail — ships Docker logs from containers labeled `logging=promtail`

Configuration files:

- `infra/observability/prometheus.yml` — scrape Prometheus itself and the API via `host.docker.internal:4000/metrics`
- `infra/observability/loki-config.yaml` — filesystem-backed Loki with 7-day retention
- `infra/observability/tempo-config.yaml` — local-disk Tempo with OTLP receivers and 7-day block retention
- `infra/observability/promtail-config.yaml` — Docker service discovery, relabels container name / stream / job
- `infra/observability/otel-collector-config.yaml` — OTLP receiver; routes traces to Tempo, logs to Loki, metrics to Prometheus remote-write

Quick start:

```bash
pnpm obs:up
```

Dashboards live in `infra/grafana/dashboards/`; `infra/grafana/dashboards/api-overview.json` is the primary API health dashboard (request rates, status codes, etc.).

---

### Temporal

There is no separate `infra/temporal/` directory. Temporal configuration is embedded in the Docker Compose files:

- `infra/local/docker-compose.yml` — `temporalio/auto-setup:1.29` + `temporalio/ui:2.32.0`
- `infra/docker/docker-compose.yml` — production-oriented `temporalio/auto-setup:1.24` + `temporalio/ui:2.26`

Both point Temporal at the PostgreSQL seed host and expose ports `7233` and `8080`.

---

### R2 / S3 lifecycle

Path: `infra/r2/`

- `infra/r2/README.md` — instructions for applying and verifying the bucket lifecycle configuration.
- `infra/r2/lifecycle.json` — aborts incomplete multipart uploads after 1 day (`abort-stale-multipart`).

---

## Scripts

Path: `scripts/`

These are developer, demo, and diagnostic utilities. They are not part of the runtime services.

| Script | Purpose |
|--------|---------|
| `scripts/dev-stack.py` | One-command local full-stack launcher. Starts Docker infrastructure, runs DB migrations, then supervises Python Temporal workers, the Fastify API dev server, and the Next.js web dev server. Handles Windows process groups and graceful shutdown. |
| `scripts/run-workers.py` | Cross-platform supervisor that runs all five Python Temporal worker modules (`ingest_worker`, `reason_worker`, `render_worker`, `style_worker`, `segment_worker`) with auto-restart and crash-rate limiting. |
| `scripts/manage-local-workers.py` | Windows-specific worker manager used by `start-local-workers.sh`; tracks `python.exe` PIDs spawned by `uv run` so they can be terminated cleanly. |
| `scripts/start-local-workers.sh` | Bash wrapper that sources `.env`, sets `AI_PROVIDER=programmatic`, and delegates to `manage-local-workers.py`. |
| `scripts/stop-local-workers.ps1` | PowerShell one-liner to kill local Python worker processes matching the AI Video Editor path or worker module names. |
| `scripts/stop-dev-stack.py` | Stops a stack launched by `dev-stack.py` using the PID file in `.tmp/dev-stack.pid`, with a safety-net kill for listeners on ports `4000` and `3000`. |
| `scripts/verify-env.py` | Validates required environment variables and checks connectivity to Marengo/Twelve Labs, Temporal, Redis, R2/S3, and the local API health endpoint. |
| `scripts/check_external_apis.py` | Lightweight auth/status probes for every third-party API key used in the project (ElevenLabs, Gemini, Groq, Kimi, Kling, Pexels, Seedance, TwelveLabs, Freesound, Clerk, R2, Redis, Temporal). |
| `scripts/e2e-smoke-api.py` | API-only end-to-end smoke test: creates a project, uploads reference + song + clips, waits for ingest/style, triggers reference-driven generation, renders, downloads the output, and validates it with ffprobe. |
| `scripts/batch2-offline-render.py` | Standalone offline render for the "batch 2" fixture set. Runs probe, beat detection, shot detection, heatmap computation, programmatic cut-list generation, clip ranking, transition selection, adaptive audio mix, and FFmpeg rendering without needing the API or Temporal. |
| `scripts/cutlist_scorer.py` | Heuristic scorer for cut lists: measures pacing, beat sync, clip/shot diversity, energy arc, and transition variety. Cheap enough to use inside an iterative edit-improvement loop. |
| `scripts/prompt-sweep.py` | Runs a set of prompt edits against a baseline cut list and scores each result. Modes: `sweep` (log all) and `improve` (hill-climb, keeping only edits that raise the score, and writes `docs/prompt-edit-changelog.md`). |
| `scripts/download_models.py` | Pre-downloads long-lead models (SAM3/SAM3.1, RVM) from Hugging Face and PyTorch Hub, checking gated-repo access first. |
| `scripts/select-fixtures.mjs` | Queries Pexels and Freesound for portrait videos + CC0 audio and writes `e2e/fixtures/manifest.json`. |
| `scripts/download-from-manifest.mjs` | Downloads fixtures from `e2e/fixtures/manifest.json`, verifies magic bytes, and caches them. Strict host allowlist and path-escape checks. |
| `scripts/select-car-meet.mjs` | Same as `select-fixtures.mjs` but targets `docs/assets/car-meet/` for README demo media. |
| `scripts/download-car-meet.mjs` | Downloads the car-meet demo assets from `docs/assets/car-meet/manifest.json`. |
| `scripts/download-fixtures.sh` | Convenience bash wrapper that runs `select-fixtures.mjs` then `download-from-manifest.mjs`; requires `PEXELS_API_KEY` and `FREESOUND_API_TOKEN`. |
| `scripts/clean-branches.sh` | Deletes merged local/remote branches and lists stale local branches older than 30 days. |

---

## Root configuration

| File | Responsibility |
|------|----------------|
| `package.json` | Root monorepo manifest. Defines `pnpm` scripts (`build`, `dev`, `lint`, `typecheck`, `obs:*`, `infra:*`, `workers`, `dev:*`, `verify:env`, `e2e`, etc.), dev dependencies (Biome, Playwright, Prettier, Husky, lint-staged, tsx, turbo), and `packageManager: pnpm@9.15.9`. |
| `pnpm-workspace.yaml` | Workspace glob definition: `apps/*` and `packages/*`. |
| `turbo.json` | Turborepo pipeline. `build` depends on `^build` and outputs `.next/**` and `dist/**`. `dev` is persistent and uncached. `lint` and `typecheck` depend on `^build`. |
| `pyproject.toml` | Python project / workspace configuration for the test suite and services. Declares test dependencies (`pytest`, `httpx`, `pydantic`, etc.), pytest paths, markers, coverage sources, and the `tool.uv.workspace` with members under `services/*`. Local services (`shared-py`, `ingest-worker`, etc.) are declared as workspace sources. |
| `uv.lock` | uv-generated lockfile pinning the full Python dependency graph across all workspace members. Do not hand-edit; regenerate with `uv lock`. |

---

## End-to-end tests

Path: `e2e/`

Playwright-based end-to-end tests covering user journeys, smoke tests, and chaos-style misuse tests.

Configuration:

- `e2e/playwright.config.ts` — `testDir` is `e2e/specs`, single worker, 15-minute test timeout, `fullyParallel: false` because tests share a single test user. Projects: `setup` (`auth.setup.ts`), `chromium`, and `mobile-safari`. Includes a `webServer` block that runs `pnpm dev` when `CI` is not set.
- `e2e/.env.e2e` — environment file loaded first by Playwright for `E2E_TEST_USER_EMAIL`, `E2E_TEST_USER_PASSWORD`, `E2E_BASE_URL`, etc.

Fixtures:

- `e2e/fixtures/` — sample media: `clip-1.mp4`, `clip-2.mp4`, `clip-3.mp4`, `reference.mp4`, `song.mp3`, plus `manifest.json` used by the fixture-selection scripts.

Helpers:

- `e2e/helpers/auth.ts` — `signIn(page)` for Clerk-based authentication using `E2E_TEST_USER_EMAIL/PASSWORD`.
- `e2e/helpers/authBypass.ts` — no-op helper for the `DISABLE_CLERK_AUTH=1` mode where middleware injects the test user.
- `e2e/helpers/upload.ts` — `uploadFixture(page, type, relativePath)` selects a file input by `data-testid="upload-${type}"`.
- `e2e/helpers/ffprobe.ts` — runs `ffprobe` and `ffmpeg` to extract codec, duration, dimensions, file size, and average luma from rendered outputs.
- `e2e/helpers/wedge.ts` — `computeWedge(cutListA, cutListB)` implements the WEDGE assertion used in scenario B: compares cut-count parity, pacing correlation, effect-count parity, and shot-length KL divergence.
- `e2e/helpers/chaos.ts` — helpers for chaotic-user tests: label-based clicking, dialog closing, random editor clicks, and back/forward navigation.

Specs:

- `e2e/specs/auth.setup.ts` — setup project that signs in once and saves storage state to `e2e/.auth/user.json`.
- `e2e/specs/smoke/` — short smoke tests for dashboard, editor mount, mobile dashboard, new project, upload, and reference/song upload.
- `e2e/specs/chaos/` — adversarial navigation, editor-action, and upload-misuse tests.
- `e2e/specs/pipeline.spec.ts` — full render pipeline tests:
  - Scenario A: prompt + song only → validates downloaded MP4.
  - Scenario B: reference-driven render → compares output to scenario A using WEDGE metrics.
  - Scenario C: export preset selection → asserts YouTube 16:9 dimensions (`1280x720`).

Run commands (from root `package.json`):

- `pnpm e2e`
- `pnpm e2e:headed`
- `pnpm e2e:smoke`
- `pnpm e2e:pipeline`

---

## Root Python integration tests

Path: `tests/`

A pytest suite that exercises the Python services and shared library from outside the service boundaries. The suite is configured in `pyproject.toml`.

Configuration:

- `tests/conftest.py` — shared pytest hooks:
  - Auto-skips tests marked `@pytest.mark.ffmpeg` when `ffmpeg` is unavailable.
  - Auto-skips provider-specific tests (`requires_anthropic`, `requires_google`, `requires_groq`, etc.) when the corresponding API key is not set.

Key test files (by name/domain):

- `tests/test_ai_providers.py` — AI provider clients.
- `tests/test_api_routes.py` — API route-level integration.
- `tests/test_beat_detect.py` — audio beat detection.
- `tests/test_clip_rank.py` — clip ranking logic.
- `tests/test_config.py` — configuration handling.
- `tests/test_cutlist.py` / `tests/test_cutlist_gen.py` — cut-list data model and generation.
- `tests/test_edge_cases.py` — edge-case coverage.
- `tests/test_generative_activity.py` / `tests/test_generative_client.py` — generative AI activities.
- `tests/test_guardrails_output.py` — guardrails output validation.
- `tests/test_integration.py` / `tests/test_integration_pipeline.py` — cross-service integration and full pipeline.
- `tests/test_marengo_client.py` — Twelve Labs / Marengo client.
- `tests/test_models.py` — shared Python models.
- `tests/test_probe.py` — video probing.
- `tests/test_rank_clips_activity.py` — ranking activity.
- `tests/test_render.py` / `tests/test_render_compiler.py` — render service and timeline compiler.
- `tests/test_shot_detect.py` — shot boundary detection.
- `tests/test_style_analysis.py` / `tests/test_style_worker_download.py` — style analysis worker.
- `tests/test_upscale.py` — upscale worker.
- `tests/test_user_events.py` — user event handling.

Run:

```bash
uv run pytest
# or
uv run pytest -m "not slow"
```

`pyproject.toml` also defines `tool.coverage.run` sources covering each `services/*/src` directory, with reports showing missing lines.
