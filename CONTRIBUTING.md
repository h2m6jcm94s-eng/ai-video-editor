# Contributing to AI Video Editor

Thank you for your interest in contributing! This guide covers everything you need to know to get started.

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Code Style](#code-style)
- [Testing](#testing)
- [Git Workflow](#git-workflow)
- [Commit Conventions](#commit-conventions)
- [Pull Request Process](#pull-request-process)
- [Code Review Etiquette](#code-review-etiquette)
- [Adding a New Worker](#adding-a-new-worker)
- [Adding a New Effect](#adding-a-new-effect)
- [Pre-Commit Hooks](#pre-commit-hooks)
- [Release Process](#release-process)

---

## Development Setup

### Prerequisites

See the [Development Guide](./docs/DEVELOPMENT.md) for detailed setup instructions. Quick version:

```bash
# 1. Clone and install
git clone <repo-url>
cd ai_video_editor
pnpm install

# 2. Start infrastructure
docker compose -f infra/docker/docker-compose.yml up -d

# 3. Set up environment
cp apps/api/.env.example apps/api/.env
# Edit with your Clerk keys

# 4. Run migrations
pnpm --filter @ai-video-editor/api db:migrate

# 5. Start dev
pnpm dev
```

### Verify Your Setup

```bash
# All checks should pass
pnpm typecheck           # TypeScript type checking
pnpm --filter @ai-video-editor/api test:coverage  # API tests with coverage
.venv\Scripts\python -m pytest tests/               # Python tests
```

---

## Project Structure

This is a **monorepo** using pnpm workspaces for JavaScript and uv workspaces for Python.

### Monorepo Layout

```
ai_video_editor/
├── apps/                 # Deployable applications
│   ├── api/             # Fastify 4 backend
│   └── web/             # Next.js 15 frontend
├── packages/            # Shared libraries
│   ├── shared-types/    # Zod schemas, enums, effects
│   └── eslint-config/   # Shared lint rules
├── services/            # Python workers (uv workspace)
│   ├── ingest-worker/
│   ├── style-worker/
│   ├── reason-worker/
│   ├── render-worker/
│   ├── upscale-worker/
│   └── shared-py/
├── infra/               # Docker, Temporal, deployment
├── tests/               # Python integration tests
└── docs/                # Documentation
```

### Workspace Commands

```bash
# Run command in a specific package
pnpm --filter @ai-video-editor/api dev
pnpm --filter @ai-video-editor/web test

# Run command in all packages
pnpm -r dev
pnpm -r build
```

---

## Code Style

### TypeScript

- **Formatter**: Prettier (configured in root)
- **Linter**: Biome (replaces ESLint + Prettier for staged files)
- **Types**: Strict mode enabled

Run before committing:
```bash
pnpm format          # Prettier across all files
pnpm lint            # Turbo lint (Biome via lint-staged on commit)
```

### Python

- **Formatter**: Black
- **Linter**: Ruff
- **Type Checker**: mypy

Run before committing:
```bash
ruff check services/
black services/
mypy services/
```

### Naming Conventions

| Context | Convention | Example |
|---|---|---|
| TypeScript files | camelCase | `projectRoutes.ts` |
| TypeScript functions | camelCase | `getProjectById()` |
| TypeScript types | PascalCase | `ProjectStatus` |
| TypeScript constants | UPPER_SNAKE_CASE | `MAX_UPLOAD_SIZE` |
| Python files | snake_case | `cutlist_gen.py` |
| Python functions | snake_case | `generate_cutlist()` |
| Python classes | PascalCase | `CutListGenerator` |
| Database columns | snake_case | `created_at` |
| JSONB fields | camelCase | `cutList`, `totalDurationS` |
| Environment variables | UPPER_SNAKE_CASE | `DATABASE_URL` |

### File Organization

**API routes**: One file per resource, all CRUD + special endpoints in one place.

**API services**: One file per domain (AI, storage, queue, temporal, users).

**Web components**: Co-locate by feature:
```
components/editor/
├── EditorLayout.tsx
├── panels/
│   ├── MediaPanel.tsx
│   ├── PreviewPanel.tsx
│   └── TimelinePanel.tsx
└── canvas/
    ├── OverlayCanvas.tsx
    └── TextOverlay.tsx
```

---

## Testing

### Test Requirements

Every PR must include tests for new functionality. No exceptions.

**API changes**: Add tests in `apps/api/src/test/`
**Web components**: Add tests in `apps/web/src/**/*.test.tsx`
**Python workers**: Add tests in `tests/` or worker `test/` directories

### Coverage Policy

New code must not decrease overall coverage below thresholds:

| Metric | Threshold |
|---|---|
| Statements | 70% |
| Branches | 55% |
| Functions | 60% |
| Lines | 70% |

Aim for 90%+ on code you write.

### Writing Good Tests

1. **Test behavior, not implementation** — Assert on HTTP status and response shape, not internal function calls
2. **Test error paths** — Every route needs 404, 403, and validation tests
3. **Use descriptive names** — `it("returns 404 when project does not exist")` not `it("handles missing project")`
4. **Keep tests independent** — Clear mocks in `beforeEach`, don't rely on test order
5. **Use factory functions** — Create reusable mock data objects

See [`docs/TESTING.md`](./docs/TESTING.md) for detailed patterns.

---

## Git Workflow

### Issue-First Development

Every change starts with a GitHub issue:

1. Open an issue describing the bug, feature, or refactor
2. Wait for maintainer triage (labels assigned)
3. Create a branch referencing the issue
4. Open a PR that closes the issue

### Branch Naming

```
feat/123-add-rate-limiting
fix/456-memory-leak-in-render
chore/789-update-dependencies
docs/101-improve-readme
test/202-add-auth-tests
refactor/303-extract-validation
```

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat` — New feature
- `fix` — Bug fix
- `docs` — Documentation only
- `style` — Code style changes (formatting, semicolons)
- `refactor` — Code refactoring
- `test` — Adding or updating tests
- `chore` — Build process, dependencies, tooling
- `perf` — Performance improvement

**Examples:**
```
feat(api): add rate limiting to render endpoint

Implements @fastify/rate-limit with per-endpoint configuration.
Renders limited to 3/min, transcribe to 5/min, prompt to 10/min.

Closes #123
```

```
fix(render): resolve memory leak in FFmpeg pipeline

The concat filter was not being properly released, causing
memory to grow unbounded during long renders.

Fixes #456
```

```
test(api): add auth middleware coverage

Adds tests for 401, user resolution, upsert flow, and Clerk
failure fallback. Coverage improved from 60% to 96%.

Closes #202
```

---

## Pull Request Process

### PR Checklist

Before requesting review, ensure:

- [ ] Issue exists and is referenced in PR description (`Closes #123`)
- [ ] Branch is up to date with `main`
- [ ] All tests pass locally
- [ ] New code has tests
- [ ] Coverage does not decrease
- [ ] TypeScript types are correct (`pnpm typecheck`)
- [ ] Code is formatted (`pnpm format`)
- [ ] No lint errors (`pnpm lint`)
- [ ] Python tests pass (if applicable)
- [ ] Documentation updated (if applicable)

### PR Description Template

```markdown
## Summary
Brief description of what this PR does.

## Changes
- Change 1
- Change 2

## Testing
- How you tested this
- Test commands run

## Screenshots (if UI changes)

## Related Issues
Closes #123
```

### Review Criteria

Maintainers review for:

1. **Correctness** — Does the code do what it claims?
2. **Tests** — Are there adequate tests? Do they test behavior, not implementation?
3. **Style** — Does it follow project conventions?
4. **Documentation** — Are docs updated if behavior changes?
5. **Performance** — Any obvious performance issues?
6. **Security** — Any security concerns (input validation, auth checks)?

### Merge Policy

- Squash merge into `main`
- All CI checks must pass
- At least one maintainer approval required
- PR description becomes the squash commit message

---

## Code Review Etiquette

### For Authors

- **Keep PRs small** — Under 400 lines changed when possible
- **Respond to feedback** — Don't resolve comments without addressing them
- **Explain non-obvious choices** — Add PR comments on complex logic
- **Be patient** — Reviewers are volunteers with day jobs

### For Reviewers

- **Be constructive** — Suggest improvements, don't just criticize
- **Ask questions** — "Why did you choose X over Y?" is better than "Don't use X"
- **Approve when good enough** — Perfect is the enemy of merged
- **Distinguish blocking vs. non-blocking** — Use "nit:" prefix for minor suggestions

---

## Adding a New Worker

1. Create `services/<name>-worker/` directory
2. Add `pyproject.toml` with `shared-py` workspace dependency:
   ```toml
   [project]
   name = "<name>-worker"
   dependencies = ["shared-py"]
   ```
3. Implement logic in `services/<name>-worker/src/<name>_worker/`
4. Add entry point in `services/<name>-worker/src/<name>_worker/__main__.py`
5. Add Dockerfile in `infra/docker/Dockerfile.<name>`
6. Add Modal deployment in `infra/modal/<name>_modal.py`
7. Register Temporal activity in `infra/temporal/activities.py`
8. Update `services/orchestrator.py`
9. Add tests in `tests/test_<name>.py`
10. Update documentation

---

## Adding a New Effect Type

Effects require changes across three layers:

### 1. Shared Schema

Add to `packages/shared-types/src/effects.ts`:

```typescript
export const myEffectSchema = z.object({
  type: z.literal("my_effect"),
  params: z.object({
    intensity: z.number().min(0).max(1),
    duration: z.number().positive(),
  }),
});
```

### 2. Web Preview

Add React component in `apps/web/src/components/editor/canvas/`:

```typescript
export function MyEffectPreview({ params }: { params: MyEffectParams }) {
  // Render preview using CSS or Canvas
}
```

### 3. Python Render

Add FFmpeg filter chain in `services/render-worker/src/render_worker/compiler.py`:

```python
def apply_my_effect(stream, params):
    intensity = params["intensity"]
    return stream.filter("eq", contrast=1 + intensity)
```

### 4. Tests

- Test schema validation
- Test web preview rendering
- Test FFmpeg output

---

## Pre-Commit Hooks

This project uses Husky v9 with lint-staged. On every commit:

1. `biome check --write` runs on staged files
2. `pnpm typecheck` runs on staged TypeScript files

Skip hooks only in emergencies:
```bash
git commit -m "WIP" --no-verify  # Not recommended
```

---

## Release Process

1. **Version bump** — Update version in `package.json` and `apps/api/package.json`
2. **Changelog** — Add entry to `CHANGELOG.md`
3. **Tag** — Create annotated git tag: `git tag -a v1.2.3 -m "Release v1.2.3"`
4. **Push** — `git push origin v1.2.3`
5. **CI triggers** — GitHub Actions builds Docker images and creates release

### Semantic Versioning

- **MAJOR** — Breaking changes to API or data format
- **MINOR** — New features, backward compatible
- **PATCH** — Bug fixes, backward compatible

---

## Getting Help

- **Documentation**: Check [`docs/`](./docs/) directory
- **Issues**: Open a GitHub issue with the `question` label
- **Discussions**: Use GitHub Discussions for general questions

---

## Code of Conduct

This project adheres to a [Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

---

Thank you for contributing! 🎬
