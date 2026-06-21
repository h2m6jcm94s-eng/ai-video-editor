# AGENTS.md — Orientation for AI Assistants

> This file contains the essential context coding agents need to work effectively in this codebase. Read this first, then check layer-specific `AGENTS.md` files for deeper guidance.

## Table of Contents

- [What This Repo Is](#what-this-repo-is)
- [Monorepo Layout](#monorepo-layout)
- [Cross-Boundary Rules](#cross-boundary-rules)
- [Where to Find Things](#where-to-find-things)
- [Testing Patterns](#testing-patterns)
- [Common Pitfalls](#common-pitfalls)
- [Workflow Norms](#workflow-norms)
- [Before You Make Changes](#before-you-make-changes)
- [Decision Log](#decision-log)

---

## What This Repo Is

An AI-powered video editor monorepo. The product vision: "Claude Code for video editing" — AI generates a working baseline from reference video + song + clips + style tier; power users refine via prompts and manual controls.

### Core User Flow

1. User uploads **reference video** + **song** + **clips**
2. AI analyzes reference (beats, shots, color, text, motion)
3. AI generates **cutlist** (editing timeline)
4. User reviews and optionally prompt-edits the cutlist
5. System renders final video with effects and transitions
6. User downloads the result

---

## Monorepo Layout

```
ai_video_editor/
├── apps/
│   ├── web/           Next.js 15 frontend (Clerk auth, Tailwind, shadcn/ui)
│   │                  └─ AGENTS.md: apps/web/AGENTS.md
│   └── api/           Fastify 4 backend (Temporal, Drizzle, Postgres, Redis)
│                      └─ AGENTS.md: apps/api/AGENTS.md
├── packages/
│   ├── shared-types/  Source of truth for Zod schemas, enums, errors, effects
│   └── eslint-config  Shared lint rules
├── services/          Python workers (render, ingest, style, reason) — uv workspace
│                      └─ AGENTS.md: services/AGENTS.md
├── infra/             Docker, Temporal, deployment configs
│                      └─ AGENTS.md: infra/AGENTS.md
├── tests/             Python integration tests
└── docs/              Architecture, API, development, testing, deployment docs
```

### Package Naming

| Package | Path | Import Prefix |
|---|---|---|
| API | `apps/api` | `@ai-video-editor/api` |
| Web | `apps/web` | `@ai-video-editor/web` |
| Shared Types | `packages/shared-types` | `@ai-video-editor/shared-types` |
| ESLint Config | `packages/eslint-config` | `@ai-video-editor/eslint-config` |

---

## Cross-Boundary Rules

These rules are **non-negotiable**. Violating them will be caught in code review.

### 1. Single Source of Truth

Any schema shared between frontend and backend lives in `packages/shared-types`. Never duplicate enums or validation logic.

**Good:**
```typescript
// packages/shared-types/src/schemas.ts
export const createProjectSchema = z.object({
  name: z.string().min(1).max(200),
  styleTier: z.enum(["cuts_only", "color_grade", "with_text", "with_effects", "full_remix"]),
});

// apps/api/src/routes/projects.ts
import { createProjectSchema } from "@ai-video-editor/shared-types";
app.post("/", { preHandler: validateBody(createProjectSchema) }, ...);

// apps/web/src/components/editor/CreateProjectDialog.tsx
import { createProjectSchema } from "@ai-video-editor/shared-types";
const form = useForm({ resolver: zodResolver(createProjectSchema) });
```

**Bad:**
```typescript
// Duplicating the schema in both API and web
const createProjectSchema = z.object({ ... }); // In API
const createProjectSchema = z.object({ ... }); // In web — DON'T DO THIS
```

### 2. camelCase for CutList JSONB Everywhere

The DB stores snake_case legacy in some rows; new code uses camelCase consistently across frontend types, backend responses, AI prompts, and Python alias_generator.

| Layer | Convention |
|---|---|
| TypeScript types | `totalDurationS`, `clipAssetIds` |
| Backend responses | `totalDurationS`, `clipAssetIds` |
| AI prompts | `totalDurationS`, `clipAssetIds` |
| Python Pydantic | `total_duration_s` (model) → serialized as `totalDurationS` |
| Database columns | `total_duration_s` (legacy), `cutList` (JSONB uses camelCase keys) |

### 3. No Silent `catch {}`

Every catch must log + toast or re-throw.

**Good:**
```typescript
try {
  await riskyOperation();
} catch (err) {
  request.log.error({ err }, "Operation failed");
  return sendError(reply, 500, "Operation failed", "INTERNAL_ERROR");
}
```

**Bad:**
```typescript
try {
  await riskyOperation();
} catch {
  // silently swallowed — NEVER DO THIS
}
```

The `APIError.userMessage` pattern provides human-friendly error text for UI toasts.

### 4. Forms Use react-hook-form + zodResolver + Shared Schemas

No raw `useState` form state in new code.

```typescript
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { createProjectSchema } from "@ai-video-editor/shared-types";

const form = useForm({
  resolver: zodResolver(createProjectSchema),
});
```

### 5. Forbidden Additions

The following are **explicitly banned** in this codebase:

- Redux, Zustand, Jotai, MobX (use vanilla `useState`/`useReducer`)
- CSS Modules, styled-components, Emotion (use Tailwind only)
- Material UI, Ant Design (use shadcn/ui)
- Lodash (use native ES2023)
- Moment.js (use native `Date` or `date-fns` if needed)
- Axios (use native `fetch`)

### 6. Auth Pattern

- **Server Components** use `apiServer` for API calls
- **Client Components** use `useApi()` hook
- **Never** pass Clerk tokens manually
- The auth middleware syncs Clerk users to local DB automatically

### 7. Effect Catalog Requirement

Every new effect needs:
1. Shared schema in `packages/shared-types/src/effects.ts`
2. Web preview component in `apps/web/src/components/editor/canvas/`
3. Python render implementation in `services/render-worker/`
4. Tests for all three layers

### 8. Redis Caching Pattern

List endpoints use `cacheGet`/`cacheSet` with per-user keys and 30s TTL. Invalidate on mutations via `cacheDel`.

```typescript
const cacheKey = `projects:list:${userId}`;
const cached = await cacheGet(cacheKey);
if (cached) return { projects: cached };

const projects = await db.query.projects.findMany({ ... });
await cacheSet(cacheKey, projects);
return { projects };
```

After any mutation:
```typescript
await cacheDel(`projects:list:${userId}`);
```

### 9. Coverage Ratchet

API tests enforce thresholds. Don't let coverage drop:

| Metric | Floor |
|---|---|
| Statements | 70% |
| Branches | 55% |
| Functions | 60% |
| Lines | 70% |

Current coverage: **86.79% statements, 76.67% branches**

---

## Where to Find Things

| What | Where |
|---|---|
| Shared schemas | `packages/shared-types/src/{enums,schemas,errors,effects}.ts` |
| API client (RSC) | `apps/web/src/lib/api/server.ts` |
| API client (client) | `apps/web/src/lib/api/client.ts` |
| API error handling | `apps/web/src/lib/api/error.ts` |
| Backend routes | `apps/api/src/routes/*.ts` |
| Backend validation | `apps/api/src/middleware/validate.ts` |
| Backend auth | `apps/api/src/middleware/auth.ts` |
| Editor state | `apps/web/src/hooks/useEditor.ts` |
| Timeline playback | `apps/web/src/hooks/useTimeline.ts` |
| Upload logic | `apps/web/src/hooks/useUpload.ts` |
| Progress SSE | `apps/web/src/hooks/useProgress.ts` |
| Domain glossary | `CONTEXT.md` |
| Cache helpers | `apps/api/src/lib/cache.ts` |
| Shared Redis client | `apps/api/src/lib/redis.ts` |
| Structured logger (API) | `apps/api/src/lib/logger.ts` |
| Frontend logger | `apps/web/src/lib/logger.ts` |
| Structured logger (Python) | `services/shared-py/src/shared_py/logging_config.py` |
| Python tracing | `services/shared-py/src/shared_py/tracing.py` |
| Pydantic models (Python) | `services/shared-py/src/shared_py/models.py` |
| Observability stack | `infra/observability/docker-compose.yml` |
| Observability docs | `infra/observability/README.md` |
| OpenAPI spec | `apps/api/openapi.yaml` |
| AI providers (Python) | `services/shared-py/src/shared_py/ai_providers/` |
| Ingest workflow | `services/ingest-worker/src/ingest_worker/workflows.py` |
| Ingest activities | `services/ingest-worker/src/ingest_worker/activities.py` |
| Render workflow | `services/render-worker/src/render_worker/workflows.py` |
| Render activities | `services/render-worker/src/render_worker/activities.py` |
| Local Docker setup | `infra/local/docker-compose.yml` |
| CI workflows | `.github/workflows/` |
| Test mocks | `apps/api/src/test/setup.ts` |
| API tests | `apps/api/src/test/*.test.ts` |
| Documentation | `docs/{ARCHITECTURE,API,DEVELOPMENT,TESTING,DEPLOYMENT}.md` |

---

## Testing Patterns

### API Test Structure

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Resource Routes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockResource = { id: "1", userId: "test-user-id", ... };

  it("lists resources", async () => {
    vi.mocked(db.query.resources.findMany).mockResolvedValueOnce([mockResource]);
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/resources" });
    expect(res.statusCode).toBe(200);
    expect(JSON.parse(res.body).resources).toHaveLength(1);
  });

  it("returns 404 when not found", async () => {
    vi.mocked(db.query.resources.findFirst).mockResolvedValueOnce(undefined);
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/resources/999" });
    expect(res.statusCode).toBe(404);
  });

  it("returns 403 for other user's resource", async () => {
    vi.mocked(db.query.resources.findFirst).mockResolvedValueOnce({
      ...mockResource,
      userId: "other-user-id",
    });
    const app = await buildApp();
    const res = await app.inject({ method: "GET", url: "/api/resources/1" });
    expect(res.statusCode).toBe(403);
  });
});
```

### Mocking the Database

The central mock in `setup.ts` provides chainable query mocks:

```typescript
// Mock a query result
vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);

// Mock an insert
vi.mocked(db.insert).mockReturnValueOnce({
  values: vi.fn().mockReturnValueOnce({
    returning: vi.fn().mockResolvedValueOnce([mockProject]),
  }),
} as any);

// Mock an update
vi.mocked(db.update).mockReturnValueOnce({
  set: vi.fn().mockReturnValueOnce({
    where: vi.fn().mockReturnValueOnce({
      returning: vi.fn().mockResolvedValueOnce([updated]),
    }),
  }),
} as any);
```

### Testing AI Service Calls

```typescript
vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({
  json: async () => ({
    content: [{ type: "text", text: JSON.stringify({ diff: [], explanation: "ok" }) }],
  }),
  ok: true,
  status: 200,
} as any));

vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
vi.stubEnv("AI_PROVIDER", "claude");
```

### Environment Cleanup

```typescript
describe("Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.unstubAllEnvs();
  });
});
```

---

## Common Pitfalls

### 1. `vi.mock()` Inside Tests

`vi.mock()` is hoisted — it runs before tests, even if written inside a test block. Use it at the top level of the module.

```typescript
// WRONG
it("test", () => {
  vi.mock("../module", () => ({ ... }));
});

// RIGHT (at top of file)
vi.mock("../module", () => ({ ... }));
```

### 2. Forgetting to Clear Mocks

Mocks persist between tests unless cleared. Always use `beforeEach(vi.clearAllMocks)`.

### 3. Not Awaiting `app.inject()`

`app.inject()` returns a Promise. Always await it.

```typescript
// WRONG
const res = app.inject({ ... });
expect(res.statusCode).toBe(200);

// RIGHT
const res = await app.inject({ ... });
expect(res.statusCode).toBe(200);
```

### 4. Mocking `vi.mocked()` on Non-Mock Functions

Only use `vi.mocked()` on functions that were created with `vi.fn()`. Real functions will throw.

### 5. Not Testing Error Paths

Every route should test at minimum:
- 401 (unauthorized)
- 403 (forbidden / wrong user)
- 404 (not found)
- 422 (validation error)

### 6. Testing Implementation Instead of Behavior

```typescript
// WRONG — tests internal calls
expect(db.query.projects.findMany).toHaveBeenCalledWith(expect.anything());

// RIGHT — tests observable behavior
expect(res.statusCode).toBe(200);
expect(body.projects).toHaveLength(1);
```

### 7. Leaking Environment Variables

```typescript
// WRONG
vi.stubEnv("KEY", "value");
// Leaks to next test

// RIGHT
beforeEach(() => {
  vi.unstubAllEnvs();
});
```

### 8. Not Adding Mocks to setup.ts

When a new DB query method is used in tests, add it to `setup.ts` mocks first. Otherwise tests will fail with "undefined is not a function" because the mock doesn't have that method.

```typescript
// In setup.ts
vi.mock("../db", () => ({
  db: {
    query: {
      newTable: { findFirst: vi.fn(), findMany: vi.fn() }, // Add this
    },
  },
}));
```

---

## Workflow Norms

### Issue-First Development

1. **Every change starts with an issue.** Open a GitHub issue describing the bug/feature/refactor **before writing any code**.
2. **The issue must be extensive.** Do not write one-line issues. Every issue must include:
   - **Problem statement** — what is broken or missing, with concrete reproduction steps for bugs
   - **Root cause analysis** — why it happens (for bugs) or why it's needed (for features)
   - **Proposed solution** — the approach, files to touch, and any architectural decisions
   - **Alternatives considered** — brief note on options evaluated and why the chosen one wins
   - **Verification plan** — how to test: unit tests, integration tests, manual QA steps
   - **Semantic classification** — label as `bug`, `feature`, `refactor`, `perf`, `security`, or `tech-debt`
3. **Semantic test requirement.** Every issue must explicitly state whether the change is:
   - `BREAKING` — changes public API or behavior
   - `NON_BREAKING` — additive or internal-only
   - `FIX` — corrects existing behavior without API change
   - `DOCS_ONLY` — documentation only
4. **Branch naming**: `feat/<issue-number>-short-desc`, `fix/<issue-number>-short-desc`, `chore/<issue-number>-short-desc`
5. **One concern per PR.** A PR should be reviewable in under 15 minutes. If it's longer, split it.
6. **PR description must reference the issue**: `Closes #<issue-number>`
7. **PR body must explain *what* and *why*.** Every PR description must contain:
   - **What changed** — bullet list of files and their changes
   - **Why it changed** — the motivation and trade-offs
   - **How to verify** — exact commands to run, expected outputs
   - **Regression risks** — what could break and how it's guarded against
8. **No spam bots.** We intentionally do NOT use pr-agent, Danger, semantic-pr, or any workflow that posts PR comments or sends email spam. Auto-labels only (path-based + first-time contributor + keyword matching).
9. **Merge ONLY when ALL CI checks pass.** Zero exceptions. A "pre-existing failure" is not an excuse — fix it first, then merge. Use squash merge. Keep commit messages descriptive.
10. **Delete branches after merge.** The repo has `delete_branch_on_merge` enabled, so GitHub auto-deletes head branches on PR merge. Locally, run `pnpm branch:clean` weekly to prune merged tracking refs and identify stale branches (>30 days old).

### Commit Message Format

Follow Conventional Commits:

```
<type>(<scope>): <description>

[optional body]

Closes #<issue-number>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`

Examples:
```
feat(api): add rate limiting to render endpoint

Implements @fastify/rate-limit with per-endpoint configuration.
Renders limited to 3/min, transcribe to 5/min, prompt to 10/min.

Closes #123
```

```
test(api): add auth middleware coverage

Adds tests for 401, user resolution, upsert flow, and Clerk
failure fallback. Coverage improved from 60% to 96%.

Closes #202
```

---

## Before You Make Changes

1. Run `pnpm typecheck` after any TS change
2. Run `pnpm --filter @ai-video-editor/api test` after any backend change
3. Run `pnpm --filter @ai-video-editor/web test` after any frontend change
4. Run `uv run pytest tests/` after any Python change
5. Update this file or the layer-specific `AGENTS.md` if you add a new convention
6. Update relevant docs in `docs/` if behavior changes
7. Prefer minimal changes. The codebase is fragile; small PRs win

---

## Decision Log

| Date | Decision | Context |
|---|---|---|
| 2025-01 | Fastify over Express | Better performance, built-in validation, plugin architecture |
| 2025-01 | Temporal over simple queues | Durable execution for long-running renders, signal support |
| 2025-01 | pnpm workspaces | Content-addressable store, deterministic lockfile |
| 2025-01 | No state management library | Editor state is localized; `useReducer` is sufficient |
| 2025-01 | XOR encryption (demo) | Simple for development; marked for AES-256-GCM in production |
| 2025-01 | R2/MinIO over S3 | No egress fees (R2), self-hosted option (MinIO) |
| 2025-01 | camelCase in JSONB | Consistency across frontend/backend/Python serialization |
| 2025-01 | Issue-first workflow | Forces documentation, enables tracking, improves review quality |
| 2025-01 | Vitest over Jest | Faster, better ESM support, native Vite integration |
| 2025-06 | OpenTelemetry tracing | Distributed tracing across API and Python workers via OTLP |
| 2025-06 | Self-hosted LGTM stack | Grafana + Loki + Tempo + Prometheus for logs, traces, metrics |
| 2025-06 | Frontend structured logger | Batched logger with `/api/log` ingestion and GlitchTip error tracking |
| 2025-06 | Worker logging unification | `configure_logging(service_name=...)` with Temporal correlation ID binding |
| 2025-06 | Generative filler clips | Multi-provider generative client (Gemini/Veo preferred, Seedance/Kling fallbacks) for low-confidence slots |
| 2025-06 | Gemini key format issue | Provided `AQ.*` key returns `ACCESS_TOKEN_TYPE_UNSUPPORTED` with both SDKs; stored in `.env` but provider remains unavailable until key format is clarified |
| 2025-06 | Style worker trigger | Upload flow now starts `AnalyzeStyleWorkflow` on `style` queue for `reference_video` assets; workflow downloads asset via new `download_reference_video` activity |
| 2025-06 | Style analysis persistence | Added `style_analysis` JSONB column to `projects`; `GET /projects/:id/style` queries Temporal style workflow and caches result; render workflow skips re-analysis when cached analysis is passed |

---

## Layer-Specific AGENTS.md Files

For deeper guidance on specific layers, check:

- `apps/web/AGENTS.md` — Frontend conventions, component patterns, Clerk integration
- `apps/api/AGENTS.md` — Backend conventions, route patterns, database patterns
- `packages/AGENTS.md` — Shared types conventions, schema design
- `services/AGENTS.md` — Python worker conventions, AI provider patterns
- `infra/AGENTS.md` — Infrastructure conventions, deployment patterns

---

## Documentation Index

| Document | Purpose |
|---|---|
| `README.md` | Project overview, quick start, links |
| `AGENTS.md` | This file — agent orientation |
| `CONTRIBUTING.md` | Detailed contribution guide |
| `docs/ARCHITECTURE.md` | System architecture, data flows, decisions |
| `docs/API.md` | Complete API endpoint reference |
| `docs/DEVELOPMENT.md` | Local development setup and workflows |
| `docs/TESTING.md` | Testing strategy, patterns, how-to |
| `docs/DEPLOYMENT.md` | Production deployment guide |
| `CONTEXT.md` | Domain glossary and business context |
| `CHANGELOG.md` | Version history |
| `SECURITY.md` | Security policy and reporting |
