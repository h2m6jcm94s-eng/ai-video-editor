# Contributing to AI Video Editor

## Development Setup

```bash
# Clone and install
git clone <repo>
cd ai_video-editor
make install

# Start local dev
make dev
```

## Project Structure

- **Monorepo**: pnpm workspaces (JS) + uv workspaces (Python)
- **API**: Fastify 4 in `apps/api/`
- **Web**: Next.js 15 in `apps/web/`
- **Workers**: Python services in `services/`
- **Shared**: `@ai-video-editor/shared-types` for TS, `shared-py` for Python

## Code Style

- **TypeScript**: Prettier + ESLint
- **Python**: Black + Ruff + mypy
- Run `make format` before committing

## Testing

```bash
# TypeScript tests
pnpm --filter @ai-video-editor/api test
pnpm --filter @ai-video-editor/web test

# Python tests
.venv/Scripts/python -m pytest tests/
# or on Unix:
python -m pytest tests/
```

## Adding a New Worker

1. Create `services/<name>-worker/`
2. Add `pyproject.toml` with `shared-py` workspace dependency
3. Implement logic in `src/<name>_worker/`
4. Add Modal deployment in `infra/modal/`
5. Add Temporal activity in `infra/temporal/activities.py`
6. Register in `services/orchestrator.py`

## Pull Request Process

1. Branch from `main`
2. Add tests for new functionality
3. Ensure CI passes
4. Request review from maintainers
