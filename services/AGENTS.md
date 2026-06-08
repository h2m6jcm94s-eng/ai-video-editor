# services/AGENTS.md

## Python worker conventions

1. Use `uv` for dependency management. Run `uv sync` before working.
2. Pydantic models go in `services/shared-py/src/shared_py/models.py`.
3. Use `alias_generator=to_camel` on all models that serialize to/from the cut list.
4. Workers communicate via Temporal activities or the Redis job queue.
5. FFmpeg calls must log full command on failure. No silent subprocess errors.
6. Add tests in each worker's `tests/` directory.
