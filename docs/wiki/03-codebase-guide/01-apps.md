# Apps Directory Guide

This page walks through the three applications in the `apps/` directory of the AI Video Editor monorepo.

| App | Path | Technology | Role |
|-----|------|------------|------|
| API | `apps/api/` | Fastify + TypeScript | HTTP backend, job orchestration, storage |
| Web | `apps/web/` | Next.js 15 (App Router) | Primary user interface |
| Desktop | `apps/desktop/` | Tauri v2 (experimental) | Desktop wrapper around the web app |

---

## `apps/api/` — Fastify Backend

The backend is a Fastify application that exposes REST endpoints, coordinates long-running video work through Temporal, streams progress over SSE, and stores media in S3-compatible object storage.

### Entry Point

- `apps/api/src/index.ts` — Boots the server. Probes Postgres, R2/S3, and Redis on startup, then calls `buildApp()` and binds to `env.API_PORT`. Includes graceful shutdown and a dev-only port-cleanup helper.
- `apps/api/src/env.ts` — Centralised environment validation using Zod.
- `apps/api/src/db/index.ts` — Drizzle ORM client configured with `postgres-js` and the schema relations.

### App Factory

`apps/api/src/app.ts` exports `buildApp()`, which wires together plugins, global hooks, and route modules:

| Concern | Implementation |
|---------|----------------|
| CORS | `@fastify/cors` using `WEB_URL` |
| Multipart uploads | `@fastify/multipart` with 2 GB / 30 file limits |
| Rate limiting | `@fastify/rate-limit` (skipped in E2E mode) |
| Request metrics | `onRequest`/`onResponse` hooks measuring duration and emitting Prometheus counters |
| Request ID | `x-request-id` header via `onSend` |
| Auth bypass (dev only) | `DISABLE_CLERK_AUTH` / `E2E_TEST_USER_ID` |
| Global auth hook | `requireAuth` for all routes except health, metrics, internal, and billing webhook |
| Anomaly tracking | `recordMetric()` on every authenticated response |

### Route Modules

Routes are registered in `buildApp()` with prefixes. Each route file exports an async function that receives a `FastifyInstance`.

#### `apps/api/src/routes/health.ts` (`/api/health`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Liveness check |
| GET | `/db` | Postgres connectivity |
| GET | `/ready` | Readiness: Postgres, Redis, R2, Temporal (cached 5 s) |

Key helpers: `withTimeout()`.

#### `apps/api/src/routes/metrics.ts` (`/api/metrics`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Prometheus exposition; protected by `METRICS_AUTH_TOKEN` |

#### `apps/api/src/routes/internal.ts` (`/api/internal/*`, no prefix)

Worker-facing routes protected by `requireInternalToken`.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/internal/user-events` | Persist a user event from a worker |
| GET | `/api/internal/projects/:id` | Project + assets + active render for workers |
| POST | `/api/internal/assets` | Create an asset row for worker output |
| PATCH | `/api/internal/assets/:assetId/probe` | Update ffprobe metadata |
| PATCH | `/api/internal/assets/:assetId/metadata` | Merge asset metadata |
| PATCH | `/api/internal/assets/:assetId/complete` | Mark worker asset complete |
| POST | `/api/internal/progress/:jobId` | Publish progress for render/generation job |
| PATCH | `/api/internal/projects/:id/generated-cutlist` | Persist generated cut-list |
| POST | `/api/internal/generation-jobs/:jobId/fail` | Mark generation job failed |

#### `apps/api/src/routes/log.ts` (`/api/log`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/log` | Batch frontend log events to the server logger |

#### `apps/api/src/routes/projects.ts` (`/api/projects`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | List current user's projects (Redis-cached) |
| POST | `/` | Create a project |
| GET | `/:id` | Get project + assets |
| GET | `/:id/style` | Fetch cached/running style analysis |
| PATCH | `/:id` | Update project fields |
| PATCH | `/:id/cutlist` | Update cut-list and signal render workflow |
| POST | `/:id/generate` | Start AI cut-list generation from reference |
| GET | `/:id/generation` | Latest generation job |
| POST | `/:id/transcribe` | Transcribe an audio asset |
| POST | `/:id/prompt` | Natural-language prompt edit |
| DELETE | `/:id` | Delete project + storage cleanup |

Key helpers: `startGenerationAtomic()`, `buildInitialCutList()`.

#### `apps/api/src/routes/uploads.ts` (`/api/uploads`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/presigned` | Get single-PUT presigned URL |
| POST | `/:assetId/complete` | Confirm single upload, trigger probe workflow |
| POST | `/multipart/init` | Start multipart upload |
| POST | `/multipart/sign-part` | Presign a part |
| POST | `/multipart/complete` | Complete multipart upload |
| DELETE | `/multipart/abort` | Abort multipart upload |
| GET | `/:assetId` | Fetch asset row |
| POST | `/:assetId/probe` | Manually set probe metadata |

Key helpers: `attachAssetToProject()`, `normalizeClipAssetIds()`.

#### `apps/api/src/routes/renders.ts` (`/api/renders`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/` | Start a render job |
| GET | `/:jobId` | Get render job |
| GET | `/project/:projectId` | List renders for project |
| POST | `/:jobId/complete` | Worker webhook to complete/fail render |

Key helpers: `startRenderAtomic()`, `collectMaskAssetIds()`, `buildMaskSourceMap()`.

#### `apps/api/src/routes/segments.ts` (`/api/segments`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/` | Start segmentation workflow |
| GET | `/:workflowId` | Query segmentation result |

#### `apps/api/src/routes/progress.ts` (`/api/progress`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/:jobId/events` | SSE stream of job progress with replay buffer |

#### `apps/api/src/routes/templates.ts` (`/api/templates`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | List own + public templates (Redis-cached) |
| POST | `/` | Create template |
| GET | `/:id` | Get template |
| PATCH | `/:id` | Update template |
| DELETE | `/:id` | Delete template |
| POST | `/:id/apply` | Apply template cut-list |

#### `apps/api/src/routes/presence.ts` (`/api/presence`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/:id/presence` | Report cursor position |
| GET | `/:id/presence` | Get other users' cursor positions |

In-memory `presenceStore` with 15 s TTL cleanup.

#### `apps/api/src/routes/settings.ts` (`/api/settings`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/usage` | Daily AI token usage |
| GET | `/provider-keys` | List masked provider keys |
| POST | `/provider-keys` | Save/upsert provider key (AES-encrypted) |
| DELETE | `/provider-keys/:provider` | Remove provider key |
| POST | `/provider-keys/test` | Probe provider key with a cheap call |

Supported providers: `anthropic`, `openai`, `kimi`, `openrouter`, `groq`.

#### `apps/api/src/routes/notifications.ts` (`/api/notifications`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/events` | SSE live notification stream |
| GET | `/` | Paginated unacknowledged events |
| POST | `/:id/ack` | Acknowledge one event |
| POST | `/ack-all` | Acknowledge all events |
| POST | `/internal` | Worker endpoint to create a notification |

#### `apps/api/src/routes/billing.ts` (`/api/billing`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhook` | Stripe-compatible webhook seam (mock) |
| GET | `/plan` | Current subscription |
| GET | `/invoices` | Invoice history |
| POST | `/checkout` | Create checkout session |
| POST | `/portal` | Customer portal URL |

#### `apps/api/src/routes/admin.ts` (`/api/admin`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/overview` | KPIs (users, errors, renders) |
| GET | `/users` | Paginated user list |
| GET | `/users/:userId` | User detail + stats |
| GET | `/errors` | Paginated error events |
| GET | `/renders` | Render queue health |
| GET | `/audit` | Admin audit log |

#### `apps/api/src/routes/anomaly.ts` (`/api/anomalies`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Recent anomaly events (admin only) |

### Middleware

All middleware lives in `apps/api/src/middleware/`.

| File | Export | Role |
|------|--------|------|
| `auth.ts` | `requireAuth()` | Clerk JWT verification, local user resolution via `services/users.ts` |
| `validate.ts` | `validateBody()` + shared schemas | Zod body parsing; re-exports schemas from `@ai-video-editor/shared-types` |
| `guardrails.ts` | `evaluateGuardrails()`, `validateAIResponse()`, `validatePromptGuardrails()` | Calls guardrails sidecar for prompt/output safety (fail-open) |
| `tokenBudget.ts` | `enforceTokenBudget()`, `incrementTokenUsage()`, `getUsageForUser()` | Per-user daily token tracking in Redis |
| `requireAdmin.ts` | `requireAdmin()` | Checks Clerk `publicMetadata.role === "admin"` and logs to `admin_audit` |
| `requireInternalToken.ts` | `requireInternalToken()` | Validates `x-internal-token` against `INTERNAL_WORKER_TOKEN` |
| `ownership.ts` | `requireProjectOwnership()` | Loads project and attaches to request after verifying ownership |

### Database Schema

`apps/api/src/db/schema.ts` defines the Drizzle/Postgres tables and relations.

| Table | Purpose |
|-------|---------|
| `users` | Local user mapped from Clerk (`clerkId`, email, name) |
| `projects` | Editing project (status, style tier, mode, asset refs, cut-list, style analysis) |
| `assets` | Uploaded/generated files (type, key, URL, probe metadata) |
| `renders` | Render jobs (status, stage, progress, workflow ID, output asset) |
| `generationJobs` | AI cut-list generation jobs |
| `templates` | Reusable cut-list templates (own + public) |
| `providerKeys` | Encrypted per-user AI provider API keys |
| `userEvents` | Error/notification events with acknowledgement state |
| `adminAudit` | Admin access audit log |

Migrations are in `apps/api/src/db/migrations/`.

### Services

`apps/api/src/services/` contains integrations with external systems and heavier business logic.

| File | Key Exports | Purpose |
|------|-------------|---------|
| `ai.ts` | `applyPromptEdit()`, `transcribeAudio()` | Calls LLM providers (Claude, OpenAI, Kimi, OpenRouter, Groq), applies JSON Patch diffs, handles refusals/output guardrails |
| `queue.ts` | `enqueueJob()`, `dequeueJob()`, `publishProgress()`, `setJobStatus()`, `getBufferedEvents()`, `publishNotification()` | Redis-backed priority job queue and SSE event buffering |
| `storage.ts` | `createPresignedUploadUrl()`, `createPresignedDownloadUrl()`, `downloadAsset()`, `deleteProjectAssets()`, multipart helpers | S3/R2 client (`@aws-sdk/client-s3`) |
| `temporal.ts` | `getTemporalClient()`, `startRenderWorkflow()`, `startGenerateCutlistWorkflow()`, `startProbeWorkflow()`, `startAnalyzeStyleWorkflow()`, `startSegmentSubjectWorkflow()`, `getStyleAnalysisFromWorkflow()`, `sendCutlistApprovedSignal()` | Temporal workflow client with reconnect logic |
| `users.ts` | `upsertUser()`, `getUserByClerkId()` | Maps Clerk IDs to local UUID users |
| `anomaly.ts` | `recordMetric()`, `listRecentAnomalies()` | Z-score anomaly detection over Redis sliding windows |

### Lib Utilities

`apps/api/src/lib/` holds smaller shared utilities.

| File | Purpose |
|------|---------|
| `cache.ts` | Redis get/set/delete with hit/miss metrics |
| `errors.ts` | `sendError()` — uniform error responses and per-user event recording |
| `rateLimit.ts` | Redis-backed sliding-window rate limiter |
| `redis.ts` | Shared `ioredis` client |
| `tokens.ts` | Token counting via `js-tiktoken` |
| `crypto.ts` | AES-256-GCM encryption for provider keys; HMAC completion tokens for workers |
| `cutlist.ts` | `normalizeCutList()` and re-export of `buildInitialCutList()` |
| `metrics.ts` | Prometheus registry and metric definitions |
| `logger.ts` | Pino logger, request ID/context helpers |
| `userEvents.ts` | `recordUserEvent()` persistence |
| `aiFallbacks.ts` | Safe fallback builders for AI failures |
| `tracing.ts` | Request tracing utilities |

### Cross-Cutting Concerns

| Concern | Files / How it works |
|---------|----------------------|
| **Authentication** | `middleware/auth.ts` verifies Clerk JWTs; `services/users.ts` creates a local DB user; `request.userId` is typed in `types/fastify.d.ts`. `DISABLE_CLERK_AUTH` is available for E2E only. |
| **Validation** | `middleware/validate.ts` uses Zod schemas; most shared schemas live in `packages/shared-types/src/schemas.ts` (cut-list, project, render, prompt, upload, template, etc.). |
| **Rate Limiting** | Global `@fastify/rate-limit` in `app.ts`, plus per-route `config.rateLimit`. Expensive endpoints (`/api/projects/:id/prompt`, `/api/projects/:id/transcribe`, `/api/renders`, `/api/log`) have stricter limits. `lib/rateLimit.ts` adds a Redis sliding-window limiter for AI prompts. |
| **Caching** | `lib/cache.ts` wraps Redis with 30 s default TTL; used for project lists and template lists. Cache keys are invalidated on writes. |
| **Queue / Progress** | `services/queue.ts` stores jobs in `ave:jobs:queue` (Redis sorted set), publishes progress to `job:{jobId}`, and buffers the last 50 events for SSE replay. |
| **Temporal** | `services/temporal.ts` starts workflows on task queues: `video-render-queue`, `style`, `ingest`, `generate`, `segment`. The API signals workflows (e.g. `cutlist_approved`) and queries results. |
| **Storage** | `services/storage.ts` targets the R2 bucket configured by `R2_ENDPOINT`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`. Objects are keyed as `projects/{projectId}/{type}/{assetId}-{filename}`. |

### Tests

API tests live in `apps/api/src/test/`. They use Vitest and mock external services (DB, Redis, S3, Temporal) via `apps/api/src/test/setup.ts`.

Notable test files:

- `projects.test.ts`, `projects-generation.test.ts`, `projects-prompt.test.ts`, `projects-transcribe.test.ts`
- `renders.test.ts`, `renders-completion.test.ts`
- `uploads.test.ts`, `uploads-multipart.test.ts`, `uploads-contract.test.ts`
- `auth.test.ts`, `billing.test.ts`, `templates.test.ts`, `settings.test.ts`
- `guardrails.test.ts`, `token-budget.test.ts`, `cache.test.ts`, `crypto.test.ts`
- `routes/notifications.test.ts`, `routes/projects.contract.test.ts`
- `app-coverage.test.ts` — ensures every route file has at least a smoke test.

---

## `apps/web/` — Next.js 15 Frontend

The web app is the primary user interface. It uses the App Router, server components for initial data fetch, and client components for interactive editing.

### App Router Pages

Pages are in `apps/web/src/app/`.

| File | Route | Role |
|------|-------|------|
| `layout.tsx` | root | `ClerkProvider`, dark theme, ambient background, notification bell, toaster |
| `page.tsx` | `/` | Redirects to `/dashboard` |
| `dashboard/page.tsx` | `/dashboard` | Server component: loads projects, renders dashboard sections |
| `editor/[projectId]/page.tsx` | `/editor/{projectId}` | Server component: loads project + assets, renders `EditorLayout` |
| `editor/new/page.tsx` | `/editor/new` | New-project flow |
| `settings/page.tsx`, `settings/billing/page.tsx`, `settings/keys/page.tsx` | `/settings/*` | Settings UI |
| `admin/page.tsx`, `admin/users/page.tsx`, `admin/renders/page.tsx`, etc. | `/admin/*` | Admin dashboard pages |
| `pricing/page.tsx` | `/pricing` | Pricing page |
| `sign-in/[[...sign-in]]/page.tsx`, `sign-up/[[...sign-up]]/page.tsx` | `/sign-in`, `/sign-up` | Clerk auth pages |
| `middleware.ts` | N/A | Clerk middleware; protects non-public routes |

`apps/web/src/middleware.ts` uses `clerkMiddleware` and redirects unauthenticated users to `/sign-in`.

### Key Components

#### Dashboard (`apps/web/src/components/dashboard/`)

| Component | Purpose |
|-----------|---------|
| `DashboardHeader.tsx` | Top nav with logo, pricing/settings links, `CreateProjectDialog` |
| `HeroSection.tsx` | Hero banner on dashboard |
| `ProjectList.tsx` | Grid of `ProjectCard`s or empty state |
| `ProjectCard.tsx` | Single project summary card |
| `CreateProjectDialog.tsx` | Dialog to create a project (style tier + mode) |
| `StatsSection.tsx` | Project/render statistics |
| `SubscriptionCard.tsx` | Billing/subscription summary |
| `AmbientBackground.tsx` | Animated background |

#### Editor (`apps/web/src/components/editor/`)

| Component | Purpose |
|-----------|---------|
| `EditorLayout.tsx` | Main editor shell: top bar, media/inspector/segment panels, timeline, prompt panel, command palette |
| `EditorErrorBoundary.tsx` | Error boundary around the editor |
| `RenderButton.tsx` | Validates required assets and opens render options dialog |
| `RenderOptionsDialog.tsx` | Export preset + duration options before render |
| `RenderDownload.tsx` | Download link for completed renders |
| `ProgressBar.tsx` | Live progress overlay for active jobs |
| `SaveStatusBadge.tsx` | Autosave state indicator |
| `PresenceCursors.tsx` | Live collaborator cursor overlay |
| `SegmentPanel.tsx` | Start segmentation workflows and preview masks |
| `TemplateSaveDialog.tsx` / `TemplateLoadDialog.tsx` | Save/load reusable cut-lists |

#### Editor Panels (`apps/web/src/components/editor/panels/`)

| Component | Purpose |
|-----------|---------|
| `MediaPanel.tsx` | Asset upload + drag-and-drop library |
| `PreviewPanel.tsx` | Video preview, overlays, subtitles |
| `TimelinePanel.tsx` | Timeline toolbar + drag-to-seek + asset drops |
| `InspectorPanel.tsx` | Edit slot timing/transitions/shot type, global preview effects, overlay text |
| `PromptPanel.tsx` | Natural-language AI prompt input and history |
| `PromptHistory.tsx` | Previous prompts and undo action |

#### Editor Timeline (`apps/web/src/components/editor/timeline/`)

| Component | Purpose |
|-----------|---------|
| `Timeline.tsx` | Renders slot tracks, playhead, waveforms |
| `TimelineClip.tsx` | Individual slot clip |
| `Playhead.tsx` | Current-time indicator |
| `WaveformTrack.tsx` | Audio waveform display |

#### Shared / UI

- `apps/web/src/components/ui/` — shadcn/ui primitive components (button, dialog, form, select, slider, tabs, etc.).
- `apps/web/src/components/NotificationBell.tsx` / `NotificationPanel.tsx` — Notification UI.
- `apps/web/src/components/cmdk/CommandPalette.tsx` — `Cmd/Ctrl+K` command palette.
- `apps/web/src/components/theme-provider.tsx` — Next-themes provider.

### Hooks

Hooks are split between `apps/web/src/hooks/` and `apps/web/src/lib/hooks/`.

| Hook | Path | Purpose |
|------|------|---------|
| `useEditor` | `src/hooks/useEditor.ts` | Reducer-based editor state: cut-list, undo/redo, slots/overlays/effects, selection |
| `useTimeline` | `src/hooks/useTimeline.ts` | Playback time, play/pause, seek, zoom |
| `useSSE` | `src/hooks/useSSE.ts` | Reconnecting EventSource wrapper with replay/polling fallback |
| `useProgress` | `src/hooks/useProgress.ts` | SSE progress stream for a job |
| `useRenderStatus` | `src/hooks/useRenderStatus.ts` | Poll render list for active/latest renders |
| `useUpload` | `src/hooks/useUpload.ts` | Single + multipart upload with progress, cancellation |
| `useNotifications` | `src/hooks/useNotifications.ts` | Fetch/ack notifications and subscribe to live SSE |
| `useAssetPoller` | `src/hooks/useAssetPoller.ts` | Poll asset metadata until ingestion completes |
| `useStyleAnalysis` | `src/hooks/useStyleAnalysis.ts` | Poll/fetch project style analysis |
| `useSegmentJob` | `src/hooks/useSegmentJob.ts` | Start and poll segmentation workflows |
| `useCountUp` | `src/hooks/useCountUp.ts` | Animated number counter |
| `use-toast` | `src/hooks/use-toast.ts` | Legacy toast hook (most code uses `sonner`) |
| `use-mobile` | `src/hooks/use-mobile.tsx` / `src/components/ui/use-mobile.tsx` | Mobile breakpoint detection |
| `useAutosave` | `src/lib/hooks/useAutosave.ts` | Debounced cut-list autosave with conflict rollback |

### API Client

`apps/web/src/lib/api/` centralises backend calls.

| File | Role |
|------|------|
| `core.ts` | `createAPI()` builds typed API methods; `fetchWithRetry()` handles Clerk tokens, 401 refresh, 5xx retries, and `APIError` |
| `client.ts` | `useApi()` hook for client components (stable across Clerk re-renders) |
| `server.ts` | `apiServer` singleton for server components using `getServerAuth()` |
| `error.ts` | `APIError` class with `userMessage` mapping for every backend error code |
| `formErrors.ts` | Maps validation errors into React Hook Form `setError` |

`createAPI()` exposes typed groups: `projects`, `uploads`, `renders`, `segments`, `templates`, `presence`, `progress`, `billing`, `settings`, `notifications`, `admin`.

### Auth

`apps/web/src/lib/auth.ts` exports `getServerAuth()` using `@clerk/nextjs/server`. It also supports `DISABLE_CLERK_AUTH` for E2E. Client-side auth uses `@clerk/nextjs` `useAuth()` and `useUser()`.

### Types

`apps/web/src/types/api.ts` defines web-facing TypeScript types, mostly re-exported from `@ai-video-editor/shared-types` plus UI-specific shapes (`CanvasOverlay`, `PreviewEffects`, `BeatGrid`, etc.).

### Tests

Web tests use Vitest + React Testing Library.

- `apps/web/src/test/smoke.test.tsx` — Basic render smoke test.
- Component tests: `CreateProjectDialog.test.tsx`, `StatsSection.test.tsx`, `EditorLayout.test.tsx`, `PresenceCursors.test.tsx`, `RenderButton.test.tsx`.
- Hook tests: `useEditor.test.ts`, `useSSE.test.ts`, `useCountUp.test.ts`, `useAutosave.test.ts`.
- `apps/web/src/lib/api/error.test.ts` — Error mapping tests.
- `apps/web/tests/render-options-dialog.test.tsx` — Additional component test.

---

## `apps/desktop/` — Tauri Experimental App

The desktop app is a thin Tauri v2 wrapper around `apps/web`.

| File | Purpose |
|------|---------|
| `apps/desktop/src-tauri/tauri.conf.json` | Tauri config: window size, dev/build commands pointing at `apps/web`, bundle targets (`msi`, `dmg`, `appimage`, `nsis`) |
| `apps/desktop/src-tauri/src/lib.rs` | `run()` — initialises `tauri_plugin_shell`, opens devtools in debug builds |
| `apps/desktop/src-tauri/src/main.rs` | Entry point; calls `ai_video_editor_desktop::run()` |
| `apps/desktop/src-tauri/Cargo.toml` | Rust package metadata and Tauri dependencies |

In dev mode Tauri serves `http://localhost:3000` from the web app; in production it loads the built `apps/web/dist` folder. No custom Rust commands are implemented yet.
