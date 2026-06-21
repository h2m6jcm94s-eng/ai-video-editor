# Audit Follow-Up Report — 2026-06-21

> This report covers the second non-auth hardening pass and a general code-cleanup sweep of `ai_video_editor`. All fixes are on `main` (commit `3ddeddb`).

## 1. What was fixed in this pass

The following original audit items from `docs/AUDIT-2026-06-21.md` are now addressed:

- **API routes**
  - `anomaly.ts` — now admin-only via `requireAdmin`.
  - `log.ts` — authenticated, capped to 100 events / 256 KB, rate-limited, returns 422 on bad input.
  - `renders.ts /:jobId/complete` — sanity-checks that the render belongs to a real project before mutating status.
  - `settings.ts` — provider-key test sanitized/timeouted; delete returns 404 when missing; encrypted key validated.
  - `metrics.ts` — empty/unset `METRICS_AUTH_TOKEN` fails closed (401).
  - `presence.ts` — endpoints require auth and verify project ownership.
  - `internal.ts` — metadata patch has strict Zod schema, size limits, and body-limit.
  - `projects.ts` — asserts `userId` before cache keys; invalidates cache on mutations.
  - `admin.ts` — correlated subquery replaced with a correct aggregate.
  - `notifications.ts` — internal endpoint validates body; `details` is stored raw.
- **Core infra**
  - `cache.ts` — blocking `redis.keys()` replaced with `scanStream`.
  - `rateLimit.ts` — added `failClosed` option for expensive/mutating endpoints.
  - `errors.ts` — `sendError` recording failures are now logged/metric'd.
  - `services/ai.ts` — prompt token budget, strict JSON-patch validation, retry on `AbortError`/`TimeoutError`.
  - `shared-types/schemas.ts` — explicit `patchProjectSchema` and encrypted-key validation.
- **Web**
  - `useAutosave.ts` — surfaces errors, allows retry, only rolls back on conflict.
  - `useSSE.ts` — reconnect timeout reliably cleared.
  - `PresenceCursors.tsx` — aborts in-flight reports and debounces mousemove.
  - `EditorLayout.tsx` — uses shared `buildInitialCutList`.
  - `CreateProjectDialog.tsx` — controlled `open` state closes on submit.
- **Python workers**
  - `beat_detect.py` — temp WAV cleanup on FFmpeg failure, librosa runs before cleanup, `_HAS_LIBROSA` guard.
  - `shared_py/user_events.py` — async `areport()` helper for async contexts.
  - `segment_worker/activities.py` — base64 decode guarded, mask count/size limits.
- **DB**
  - Migration `0008_add_mask_asset_type.sql` adds `mask` to `assets_type_chk`.
- **Code cleanup**
  - Removed a large number of unused imports/variables across API and Web; `pnpm lint` now reports **0 warnings**.

## 2. Verification

| Suite | Result |
|-------|--------|
| Root `pnpm typecheck` | ✅ clean |
| Root `pnpm lint` | ✅ clean |
| API tests | **35 files, 293 passed** |
| Web tests | **10 files, 57 passed** |
| Shared-types tests | **1 file, 7 passed** |
| Python tests | **321 passed, 27 skipped** |
| Render-compiler tests | **21 passed** |

## 3. Remaining issues from the original audit

Excluding the intentionally deferred auth bypass (`DISABLE_CLERK_AUTH`), the following items are still open.

### Critical

| # | File | Issue | Why it remains |
|---|------|-------|----------------|
| 5 | `apps/api/src/routes/renders.ts` | Render-complete webhook only verifies worker token, not render ownership | We added a project-existence sanity check, but the worker request carries no user context. A leaked/misconfigured internal token can still mutate any render. Fix: project-scoped signed token or propagate ownership in the workflow.
| 13 | `apps/api/src/routes/renders.ts` | `rendersActive` gauge is in-process only and can drift | Decrement is now guarded by `wasActive`, but the gauge is still process-local. In a multi-replica deployment it is inaccurate. Fix: derive active count from DB/Redis.
| 14 | `apps/api/src/routes/progress.ts` | SSE handler has no outer try/catch after headers are sent | Individual writes are guarded, but an unhandled exception after `writeHead` can leave the raw connection dangling. Fix: wrap the route body in `try/finally` and call `reply.raw.end()`.
| 18 | `apps/api/src/lib/crypto.ts` | Provider keys use a single KEK with no rotation/versioning | Still a single `PROVIDER_KEK`. Fix: envelope encryption with version header or KMS integration.

### High

| # | File | Issue | Why it remains |
|---|------|-------|----------------|
| 36 | `apps/api/src/db/schema.ts` | `clerkId` is nullable; upsert assumes string | Deferred because it touches auth/data model. Fix: make `clerkId` `notNull()` and validate before upsert.

### Medium

| # | File | Issue | Why it remains |
|---|------|-------|----------------|
| 40 | `apps/web/src/types/api.ts` | Web `Overlay` conflicts with shared `Overlay` | Type still named `Overlay`; runtime impact is low because the shape is compatible, but the name collision remains.
| 54 | `apps/api/src/routes/templates.ts` | `PATCH /:id` has no body validation | Still casts `request.body` to `Partial<typeof templates.$inferInsert>`. Fix: add a Zod schema.
| 55 | `apps/api/src/routes/uploads.ts` | Multipart complete does not verify assembled file size | Uses client-supplied `sizeBytes` without `headObject` check. Fix: validate after assembly.
| 56 | `apps/api/src/routes/uploads.ts` | Probe triggers differ between simple and multipart complete | Simple complete probes `song`; multipart complete does not. Fix: align probe logic.
| 58 | `apps/web/src/hooks/useNotifications.ts` | Silently swallows 401/403 token errors | Fetch failures only log to console. Fix: surface auth error / trigger re-login.
| 59 | `apps/web/src/components/NotificationBell.tsx` / `NotificationPanel.tsx` | No error boundary | Components can crash the dashboard. Fix: add React error boundary.
| 60 | `apps/web/src/app/dashboard/page.tsx` | Project-list fetch failures show empty state | Error is caught and logged; UI shows no projects. Fix: show error message / retry.

### Low

| # | File | Issue |
|---|------|-------|
| 61 | `apps/api/src/routes/admin.ts` | Overview KPI queries not wrapped in try/catch |
| 63 | `apps/api/src/middleware/requireInternalToken.ts` | Internal token read once at module load |
| 64 | `services/shared-py/src/shared_py/tracing.py` | No SIGINT flush for `BatchSpanProcessor` |
| 65 | `services/reason-worker/src/reason_worker/cutlist_gen.py` | Hand-written JSON schema duplicates shared types |
| 66 | `services/render-worker/src/render_worker/compiler.py` | FFmpeg stderr still writes to a hardcoded temp log name |
| 67 | `services/orchestrator.py` | CLI paths not validated |
| 68 | `services/shared-py/src/shared_py/config.py` | `AVE_` prefix misleading; many env vars unprefixed |
| 69 | `services/guardrails/src/guardrails/engine.py` | Static keyword list for toxicity |
| 70 | `apps/api/src/routes/metrics.ts` | Prometheus registry errors return generic 500 |

## 4. New issues observed during cleanup

These were not in the original audit but surfaced while reading the code.

| # | File | Issue | Severity |
|---|------|-------|----------|
| N1 | `apps/web/src/hooks/useNotifications.ts` | `ack` / `ackAll` ignore fetch errors; UI state can diverge | Medium |
| N2 | `apps/api/src/routes/progress.ts` | Global `subscriberMap` shared across requests can leak or unsubscribe a channel while another request is using it | Medium |
| N3 | `apps/api/src/routes/renders.ts` | `completeRenderSchema` allows `outputAssetId` to be optional even when `status === "complete"` | Low |
| N4 | `apps/api/src/services/storage.ts` | `downloadAsset` does not remove partial file on write-stream error | Low |
| N5 | `apps/web/src/lib/api/core.ts` | `fetchWithRetry` does not refresh Clerk token on 401 | Medium |
| N6 | `apps/api/src/routes/internal.ts` | `createAssetSchema` validates `filename` length but allows path separators | Low |

## 5. Executive summary

- **Critical remaining:** 4 (#5, #13, #14, #18) plus the deferred auth bypass.
- **High remaining:** 1 (#36).
- **Medium remaining:** 7 (#40, #54, #55, #56, #58, #59, #60).
- **Low remaining:** 9 original + 6 newly observed low/medium items.

### Recommended next sprint order

1. **Security & auth hardening** — address the deferred auth bypass, render-webhook scope (#5), and KEK rotation (#18).
2. **Realtime robustness** — add outer SSE try/catch (#14) and review the shared subscriber map (N2).
3. **Frontend error UX** — notification auth handling (#58), error boundaries (#59), dashboard error state (#60), and API core token refresh (N5).
4. **Data consistency & validation** — `clerkId` non-null (#36), template patch schema (#54), upload size verification (#55/#56), and filename path sanitization (N6).
5. **Metrics & observability** — derive active renders from DB/Redis (#13), metrics registry error handling (#70), and tracing SIGINT flush (#64).
6. **Tech debt** — remaining low-priority cleanup and hardcoded schemas.
