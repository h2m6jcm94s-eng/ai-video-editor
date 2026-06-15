# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Self-hosted LGTM observability stack: Grafana + Loki + Tempo + Prometheus + Promtail + OTel Collector ([#119](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/119)).
- 5 pre-provisioned Grafana dashboards: API Health, Temporal Workflows, AI Calls, Render Queue, User Activity.
- OpenTelemetry tracing for API (NodeSDK) and Python workers (OTLP HTTP exporter) ([#121](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/121)).
- Frontend structured logger with batching and `/api/log` ingestion endpoint ([#117](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/117)).
- GlitchTip (Sentry-compatible) error tracking for web client/edge/server.
- Worker logging unification with `configure_logging(service_name=...)` and Temporal correlation ID binding ([#118](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/118)).
- `pino-loki` transport for shipping API logs to Loki in production ([#119](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/119)).
- OpenAPI 3.0.3 specification at `apps/api/openapi.yaml` covering full API surface ([#120](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/120)).
- Shared schemas package (`packages/shared-types`) with Zod schemas, enums, errors, and effects.
- In-app provider key management with encrypted storage and test-connection endpoint.
- Settings page with sidebar tabs (Account, API Keys, Appearance, Shortcuts, Advanced).
- Command palette (Cmd+K / Ctrl+K) for editor actions.
- Effect library shared types with 15 effects (zoom, focus pull, freeze frame, speed ramp, shake, glitch, vignette, film grain, color pop, text kinetic, lower third, callout arrow, SFX).
- Multi-audio track types (`AudioTrack[]`) in cut list.
- Render completion webhook (`POST /api/renders/:jobId/complete`).
- Contract tests for all shared schemas and upload validation.
- Structured logging with request IDs and Fastify logger.
- Layered AGENTS.md and CONTEXT.md documentation.

### Changed
- API client split into server (`apiServer`) and browser (`useApi`) surfaces with shared `createAPI` factory.
- All editor forms migrated to `react-hook-form` + shared Zod schemas.
- AI model fixes: Claude → `claude-3-5-sonnet-20241022`, OpenAI → `gpt-4o`.
- AI service reads per-user provider keys from DB, falls back to env.
- SSE progress reconnects with exponential backoff on disconnect.
- Upload uses PUT raw file with XMLHttpRequest progress and mime gate.

### Fixed
- `projects.ts` cutList `any` cast replaced with typed `z.infer<typeof updateCutlistSchema>` ([#102](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/102)).
- `compiler.py` bare `except:` changed to typed `except OSError:` in temp-file cleanup ([#113](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/113)).
- `probe.py` and `shot_detect.py` `av.open()` leaks fixed with context managers + correct duration math ([#114](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/114)).
- Web empty `catch {}` blocks now log errors via `console.error` ([#115](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/115)).
- `guardrails.ts` `console.warn` replaced with `request.log.warn` + typed `GuardrailMessage` ([#116](https://github.com/h2m6jcm94s-eng/ai-video-editor/issues/116)).
- Clerk auth now syncs users to local DB and sets `request.userId` to local UUID.
- 401 errors return proper `UNAUTHORIZED` code with user-facing toasts.
- Upload no longer sends POST to a PUT presigned URL.
- Render route returns 409 when a render is already in progress.

## [0.4.0] — 2026-06-12

### Fixed
- Editor "Maximum update depth exceeded" render loop caused by unstable form-reset dependencies in `InspectorPanel`.
- `InspectorPanel` now memoizes fallback effect / slot / overlay defaults and only calls `react-hook-form` `reset` when the underlying data actually changes.

### Known limitations (deferred to Phase F / post-v0.4.0)
- M2 style-tier pipeline gating in `workflows.py` remains blocked until `feat/temporal-worker-entry-points` lands on `main`.
- CodeQL log-injection sanitization in `guardrails/main.py:97`.
- Dismiss 2 HIGH + 2 MEDIUM false-positive CodeQL alerts with documented reasoning.
- 97 code-quality CodeQL warnings (unused imports, etc.).
- PR #164 Clerk SDK upgrade (4 remaining CI failures).
- Any deeper hook rewrite (e.g. `PresenceCursors` → `useSyncExternalStore`) will be PR'd standalone for review after the v0.4.0 tag.

## [0.1.0] — 2025-06-01

### Added
- Initial monorepo setup with Next.js, Fastify, Temporal, Drizzle, MinIO.
- Project creation, asset upload, AI prompt editing, render pipeline.
- Basic editor with timeline, inspector, preview, and subtitles.
