# Testing Guide

> Comprehensive guide to the testing strategy, patterns, and practices in the AI Video Editor project.

## Table of Contents

- [Testing Philosophy](#testing-philosophy)
- [Test Architecture](#test-architecture)
- [Running Tests](#running-tests)
- [Writing API Tests](#writing-api-tests)
- [Writing Web Tests](#writing-web-tests)
- [Writing Python Tests](#writing-python-tests)
- [Coverage Thresholds](#coverage-thresholds)
- [Mocking Patterns](#mocking-patterns)
- [Test Data Factories](#test-data-factories)
- [Common Pitfalls](#common-pitfalls)

---

## Testing Philosophy

### What We Test

| Layer | Test Type | Coverage Goal |
|---|---|---|
| API Routes | Unit tests (Vitest) | 90%+ statements |
| API Services | Unit tests (Vitest) | 85%+ statements |
| API Middleware | Unit tests (Vitest) | 95%+ statements |
| Web Components | Unit tests (Vitest + jsdom) | Smoke tests + critical paths |
| Python Workers | Unit + Integration tests (pytest) | Core logic coverage |
| Integration | E2E tests (Playwright) | Critical user journeys |

### What We Don't Test

- **Schema declarations** — Drizzle schema and Zod type definitions are declarative; testing them provides no value
- **Third-party libraries** — We trust Clerk, Fastify, Drizzle, etc. to work correctly
- **UI styling** — Visual regression is not automated (manual QA for design)
- **Infrastructure** — Docker, Terraform, and deployment configs are validated in CI

### Test Pyramid

```
        /\
       /  \     E2E Tests (Playwright)
      /----\    — Critical user journeys
     /      \   — Sign up, create project, upload, render
    /--------\
   /          \  Integration Tests
  /------------\ — API route integration
 /              \— Python worker pipeline
/----------------\
   Unit Tests     — Service logic, middleware, utilities
```

---

## Test Architecture

### API Tests

**Framework**: Vitest (Node.js environment)
**Location**: `apps/api/src/test/*.test.ts`
**Config**: `apps/api/vitest.config.ts`

```typescript
// vitest.config.ts
export default defineConfig({
  test: {
    environment: "node",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    coverage: {
      provider: "v8",
      thresholds: {
        statements: 70,
        branches: 55,
        functions: 60,
        lines: 70,
      },
    },
  },
});
```

### Web Tests

**Framework**: Vitest + jsdom + @vitejs/plugin-react
**Location**: `apps/web/src/**/*.test.{ts,tsx}`
**Config**: `apps/web/vitest.config.ts`

### Python Tests

**Framework**: pytest
**Location**: `tests/` (repo root)
**Config**: `pyproject.toml` or `pytest.ini`

---

## Running Tests

### API Tests

```bash
# Run all API tests
pnpm --filter @ai-video-editor/api test

# Run with coverage
pnpm --filter @ai-video-editor/api test:coverage

# Run a specific test file
pnpm --filter @ai-video-editor/api vitest run src/test/projects.test.ts

# Run in watch mode
pnpm --filter @ai-video-editor/api vitest

# Debug a specific test
pnpm --filter @ai-video-editor/api vitest run --reporter=verbose src/test/auth.test.ts
```

### Web Tests

```bash
# Run all web tests
pnpm --filter @ai-video-editor/web test

# Run with UI
pnpm --filter @ai-video-editor/web vitest --ui
```

### Python Tests

```bash
# All Python tests
uv run pytest tests/

# With coverage
uv run pytest tests/ --cov=services/shared-py/src --cov-report=html

# Specific test file
uv run pytest tests/test_ingest.py -v

# Run with markers
uv run pytest tests/ -m "not slow"
```

### Full Test Suite

```bash
# Run everything (JavaScript + Python)
pnpm test

# This runs:
# 1. pnpm --filter @ai-video-editor/api test
# 2. pnpm --filter @ai-video-editor/web test
# 3. uv run pytest tests/
```

---

## E2E Testing

E2E tests live in `e2e/` and are driven by Playwright. They cover the full user journey from project creation through rendered output.

### Scenarios

- **Scenario A**: prompt + song only renders a valid 9:16 MP4.
- **Scenario B**: reference-driven render produces a measurably different cut-list than Scenario A.

### Local Runbook

For the full Clerk-free setup used to replicate the `output-A.mp4` / `output-B.mp4` pipeline, see [`docs/runbooks/e2e-clerk-bypass.md`](./runbooks/e2e-clerk-bypass.md).

Quick version:

```bash
# 1. Start infrastructure
pnpm infra:up

# 2. Start workers in separate terminals
uv run python -m ingest_worker
uv run python -m render_worker

# 3. Run E2E in headed mode
pnpm e2e:headed

# Or headless
pnpm e2e
```

### Wedge Verdict

Scenario B compares its cut-list against Scenario A using the wedge helper in `e2e/helpers/wedge.ts`. Possible verdicts:

| Verdict | Meaning |
|---|---|
| `PROVEN` | Reference pipeline produced a measurably different cut-list |
| `NOT_PROVEN` | Differences are within tolerance — product finding, not a test failure |

The E2E suite **passes** even when the wedge is `NOT_PROVEN`, but `v0.4.0` must **not** be tagged until the reference pipeline consistently produces `PROVEN` results.

### E2E Configuration

Playwright config: `e2e/playwright.config.ts`

Key settings:
- `workers: 1` — scenarios run sequentially (shared test user)
- `timeout: 15 * 60 * 1000` — 15 minutes per test
- `fullyParallel: false`
- Loads `.env.local` for `E2E_TEST_USER_EMAIL` / `E2E_TEST_USER_PASSWORD`

### E2E Fixtures

Fixtures live in `e2e/fixtures/`:

| File | Purpose |
|---|---|
| `reference.mp4` | Reference style video |
| `song.mp3` | Song for sync |
| `clip-1.mp4`, `clip-2.mp4`, `clip-3.mp4` | User clips |
| `manifest.json` | Fixture metadata |

---

## Writing API Tests

### Test File Structure

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { buildApp } from "../app";
import { db } from "../db";

describe("Route Name", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Happy path tests
  describe("successful operations", () => {
    it("does the expected thing", async () => {
      // Arrange
      vi.mocked(db.query.x.findFirst).mockResolvedValueOnce(mockData);

      // Act
      const app = await buildApp();
      const res = await app.inject({ method: "GET", url: "/api/endpoint" });

      // Assert
      expect(res.statusCode).toBe(200);
      expect(JSON.parse(res.body)).toEqual(expectedData);
    });
  });

  // Error path tests
  describe("error handling", () => {
    it("returns 404 when not found", async () => {
      vi.mocked(db.query.x.findFirst).mockResolvedValueOnce(undefined);

      const app = await buildApp();
      const res = await app.inject({ method: "GET", url: "/api/endpoint/999" });

      expect(res.statusCode).toBe(404);
      expect(JSON.parse(res.body).code).toBe("NOT_FOUND");
    });

    it("returns 403 for other user's resource", async () => {
      vi.mocked(db.query.x.findFirst).mockResolvedValueOnce({
        ...mockData,
        userId: "other-user-id",
      });

      const app = await buildApp();
      const res = await app.inject({ method: "GET", url: "/api/endpoint/1" });

      expect(res.statusCode).toBe(403);
      expect(JSON.parse(res.body).code).toBe("FORBIDDEN");
    });
  });
});
```

### The `buildApp()` Pattern

Every API test creates a fresh Fastify instance:

```typescript
const app = await buildApp();
const res = await app.inject({
  method: "POST",
  url: "/api/projects",
  payload: { name: "Test" },
});
```

This ensures tests are isolated — no shared server state between tests.

### Mocking Database Queries

The central mock is in `apps/api/src/test/setup.ts`:

```typescript
vi.mock("../db", () => ({
  db: {
    query: {
      projects: { findFirst: vi.fn(), findMany: vi.fn() },
      assets: { findFirst: vi.fn(), findMany: vi.fn() },
      renders: { findFirst: vi.fn(), findMany: vi.fn() },
      templates: { findFirst: vi.fn(), findMany: vi.fn() },
      providerKeys: { findFirst: vi.fn().mockResolvedValue(null), findMany: vi.fn() },
    },
    insert: createChainableInsert(),
    update: createChainableUpdate(),
    delete: createChainableDelete(),
    execute: vi.fn().mockResolvedValue([]),
  },
}));
```

**Mocking a query result:**
```typescript
vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(mockProject);
```

**Mocking an insert:**
```typescript
vi.mocked(db.insert).mockReturnValueOnce({
  values: vi.fn().mockReturnValueOnce({
    returning: vi.fn().mockResolvedValueOnce([mockProject]),
  }),
} as any);
```

**Mocking an update:**
```typescript
vi.mocked(db.update).mockReturnValueOnce({
  set: vi.fn().mockReturnValueOnce({
    where: vi.fn().mockReturnValueOnce({
      returning: vi.fn().mockResolvedValueOnce([updatedProject]),
    }),
  }),
} as any);
```

### Mocking External Services

**Clerk** (already mocked in setup.ts):
```typescript
// Default: signed in as test-user-id
// To test unauthorized, you would need to override the mock
```

**fetch** (for AI service calls):
```typescript
vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({
  json: async () => ({ content: [{ type: "text", text: "{}" }] }),
  ok: true,
  status: 200,
} as any));
```

**Environment variables:**
```typescript
vi.stubEnv("ANTHROPIC_API_KEY", "sk-ant-test");
vi.stubEnv("AI_PROVIDER", "claude");
```

### Testing Auth Flows

```typescript
it("returns 401 when not authenticated", async () => {
  // The setup.ts mock defaults to authenticated.
  // To test 401, mock Clerk to return isSignedIn: false
  // (This requires modifying the Clerk mock in setup.ts)
});

it("returns 403 for other user's project", async () => {
  vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce({
    ...mockProject,
    userId: "other-user-id",
  });

  const app = await buildApp();
  const res = await app.inject({ method: "GET", url: "/api/projects/proj-1" });
  expect(res.statusCode).toBe(403);
});
```

### Testing Rate Limits

Set `NODE_ENV=test` to use higher rate limits:
```typescript
// In test, rate limits are 10000/min so tests don't hit them
```

To test rate limit behavior specifically:
```typescript
// Mock the rate limit plugin or set very low limits in test config
```

### Testing SSE Endpoints

SSE endpoints (like `/api/progress/:jobId/events`) are difficult to test with `app.inject()` because Fastify's inject doesn't fully support streaming `reply.raw`.

**Recommended approach**: Test auth guards only (404, 403). Full stream testing requires integration tests with a real HTTP client.

```typescript
it("returns 404 for missing job", async () => {
  vi.mocked(db.query.renders.findFirst).mockResolvedValueOnce(undefined);

  const app = await buildApp();
  const res = await app.inject({ method: "GET", url: "/api/progress/job-999/events" });
  expect(res.statusCode).toBe(404);
});
```

---

## Writing Web Tests

### Component Testing with jsdom

Current dashboard component tests:

- `apps/web/src/components/dashboard/StatsSection.test.tsx` — stat-card counts and empty state
- `apps/web/src/hooks/useCountUp.test.ts` — animated number hook

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatsSection } from "./StatsSection";

vi.mock("@/hooks/useCountUp", () => ({
  useCountUp: (value: number) => value,
}));

describe("StatsSection", () => {
  it("renders dashboard stat counts", () => {
    const projects = [
      { id: "1", name: "A", status: "complete", renderAssetId: "r1" },
      { id: "2", name: "B", status: "uploading" },
    ];

    render(<StatsSection projects={projects as any} />);

    expect(screen.getByTestId("stat-Total Projects")).toHaveTextContent("2");
    expect(screen.getByTestId("stat-Completed")).toHaveTextContent("1");
  });
});
```

### Mocking the API Client

```typescript
vi.mock("@/lib/api/client", () => ({
  useApi: () => ({
    get: vi.fn().mockResolvedValue({ projects: [] }),
    post: vi.fn(),
  }),
}));
```

### Testing Hooks

```typescript
import { renderHook } from "@testing-library/react";
import { useEditor } from "./useEditor";

describe("useEditor", () => {
  it("initializes with empty state", () => {
    const { result } = renderHook(() => useEditor());
    expect(result.current.state.cutList).toBeNull();
  });
});
```

---

## Writing Python Tests

### Worker Test Structure

```python
import pytest
from ingest_worker.probe import probe_media

def test_probe_video_metadata():
    result = probe_media("tests/fixtures/sample.mp4")
    assert result.duration_sec > 0
    assert result.width == 1920
    assert result.height == 1080
    assert result.fps == 30

def test_probe_invalid_file():
    with pytest.raises(ValueError, match="Unsupported format"):
        probe_media("tests/fixtures/corrupt.mp4")
```

### Mocking AI Providers

```python
from unittest.mock import patch, MagicMock

def test_cutlist_generation_with_mock_ai():
    mock_response = MagicMock()
    mock_response.content = [{"type": "text", "text": '{"slots": []}'}]

    with patch("reason_worker.cutlist_gen.call_claude", return_value=mock_response):
        result = generate_cutlist(prompt="simple test", reference=None)
        assert result.slots == []
```

### Integration Tests

```python
def test_full_pipeline(tmp_path):
    """Test the complete pipeline with small test assets."""
    output = tmp_path / "output.mp4"

    orchestrator.run(
        reference="tests/fixtures/ref_5s.mp4",
        song="tests/fixtures/song_5s.mp3",
        clips=["tests/fixtures/clip1_5s.mp4"],
        output=output,
        tier="cuts_only",
    )

    assert output.exists()
    assert output.stat().st_size > 0
```

---

## Coverage Thresholds

### API Coverage (Enforced in CI)

```typescript
// apps/api/vitest.config.ts
coverage: {
  thresholds: {
    statements: 70,
    branches: 55,
    functions: 60,
    lines: 70,
  },
}
```

These are minimum floors. Aim for 90%+ on new code.

### Coverage Ratchet Policy

1. New code must not drop coverage below thresholds
2. When adding features, add tests that exercise the new code
3. Coverage reports are uploaded to Codecov on every PR
4. PRs with coverage decreases require maintainer approval

### Reading Coverage Reports

After running tests with coverage:

```bash
# HTML report
open apps/api/coverage/index.html

# Terminal summary
pnpm --filter @ai-video-editor/api test:coverage
```

Focus on:
- **Branches** — The hardest to cover and most important metric
- **Uncovered lines** — The report shows exact line numbers

---

## Mocking Patterns

### Central Mock Registry (`setup.ts`)

All API tests share a central mock setup that mocks:

| Mock | Purpose |
|---|---|
| `@clerk/fastify` | Auth — always returns `test-user-id` |
| `../services/users` | User sync — `upsertUser` returns test user |
| `../db` | Database — chainable query mocks |
| `../services/storage` | R2 — returns dummy URLs |
| `fs` | File system — returns fake buffers |
| `os` | OS — returns `/tmp` |
| `ioredis` | Redis — mock client with all methods |
| `../services/queue` | Queue — `enqueueJob` is a no-op |
| `../services/temporal` | Temporal — returns dummy workflow ID |

### When to Add to Central Mocks

Add a new mock to `setup.ts` when:
- Multiple test files need the same mock
- The mock is complex (chainable methods, specific return shapes)
- The mock represents a shared dependency (DB, external service)

Keep mocks in individual test files when:
- Only one test file uses them
- The mock behavior varies significantly between tests
- The mock is simple (single function)

### Pattern: Read-Through Cache Testing

```typescript
// Testing cache hit
vi.mocked(cacheGet).mockResolvedValueOnce([mockTemplate]);
const res = await app.inject({ method: "GET", url: "/api/templates" });
// Verify DB was NOT called

// Testing cache miss
vi.mocked(cacheGet).mockResolvedValueOnce(null);
vi.mocked(db.query.templates.findMany).mockResolvedValueOnce([mockTemplate]);
const res = await app.inject({ method: "GET", url: "/api/templates" });
// Verify DB WAS called and cacheSet was called
```

### Pattern: Testing Temporal Failure

```typescript
vi.mocked(startRenderWorkflow).mockRejectedValueOnce(new Error("Temporal down"));
const res = await app.inject({
  method: "POST",
  url: "/api/renders",
  payload: { projectId: PROJ_ID },
});
expect(res.statusCode).toBe(500);
expect(JSON.parse(res.body).code).toBe("TEMPORAL_ERROR");
```

---

## Test Data Factories

### Reusable Mock Objects

Define mock objects at the top of test files for consistency:

```typescript
const mockProject = {
  id: "proj-1",
  name: "Test Project",
  status: "uploading",
  userId: "test-user-id",
  styleTier: "full_remix",
  mode: "auto",
  referenceAssetId: null,
  songAssetId: null,
  clipAssetIds: [],
  cutList: null,
  renderAssetId: null,
  createdAt: new Date(),
  updatedAt: new Date(),
};

const mockRender = {
  id: "render-1",
  projectId: "proj-1",
  status: "queued",
  stage: "queued",
  progress: 0,
  workflowId: null,
  outputAssetId: null,
  previewAssetId: null,
  errorMessage: null,
  startedAt: new Date(),
  completedAt: null,
  createdAt: new Date(),
};
```

### Factory Functions (for complex objects)

```typescript
function createMockProject(overrides?: Partial<typeof mockProject>) {
  return { ...mockProject, ...overrides };
}

// Usage
vi.mocked(db.query.projects.findFirst).mockResolvedValueOnce(
  createMockProject({ status: "rendering" })
);
```

---

## Common Pitfalls

### 1. Mock Return Value Not Reset Between Tests

```typescript
// WRONG: Mock persists between tests
vi.mocked(db.query.projects.findFirst).mockResolvedValue(mockProject);

// RIGHT: Clear mocks in beforeEach
describe("Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
});
```

### 2. `vi.mocked()` on Non-Mocked Functions

```typescript
// WRONG: cacheGet is not a vi.fn()
vi.mocked(cacheGet).mockResolvedValueOnce([mockTemplate]);
// Error: mockResolvedValueOnce is not a function

// RIGHT: Mock the module in setup.ts or use a different approach
```

### 3. Not Awaiting Async Operations

```typescript
// WRONG: Missing await
const res = app.inject({ method: "GET", url: "/api/projects" });
expect(res.statusCode).toBe(200);

// RIGHT: Always await inject()
const res = await app.inject({ method: "GET", url: "/api/projects" });
expect(res.statusCode).toBe(200);
```

### 4. Testing Implementation Details Instead of Behavior

```typescript
// WRONG: Testing internal function calls
expect(db.query.projects.findMany).toHaveBeenCalledWith({
  where: expect.anything(),
});

// RIGHT: Testing observable behavior
expect(res.statusCode).toBe(200);
expect(body.projects).toHaveLength(1);
```

### 5. Missing `beforeEach` for `vi.stubEnv`

```typescript
// WRONG: Env stubs leak between tests
vi.stubEnv("ANTHROPIC_API_KEY", "test");

// RIGHT: Unstub in beforeEach
describe("Tests", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });
});
```

### 6. Not Testing Error Paths

Every route should have tests for:
- 401 Unauthorized (auth failure)
- 403 Forbidden (wrong user)
- 404 Not Found (missing resource)
- 422 Validation Error (invalid body)
- 500 Internal Error (service failure)

### 7. Over-Mocking

Don't mock the function you're testing. Mock its dependencies.

```typescript
// WRONG: Mocking the function under test
vi.mock("../services/ai", () => ({
  applyPromptEdit: vi.fn(),
}));

// RIGHT: Mock dependencies (fetch, env vars)
vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ... }));
```

---

## CI Testing

Tests run automatically on every PR via GitHub Actions:

| Workflow | Command | Timeout |
|---|---|---|
| `test-api` | `pnpm --filter @ai-video-editor/api test:coverage` | ~45s |
| `test-web` | `pnpm --filter @ai-video-editor/web test` | ~30s |
| `test-py` | `uv run pytest tests/` | ~25s |
| `test-js` | Lint + typecheck + build | ~75s |

All must pass before merge.

The `test-web` job exercises the glassmorphic dashboard components, including `StatsSection` and `useCountUp`.

---

## Related Documentation

- [`DEVELOPMENT.md`](./DEVELOPMENT.md) — Local development setup
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) — System architecture
- [`CONTRIBUTING.md`](../CONTRIBUTING.md) — Contribution guidelines
