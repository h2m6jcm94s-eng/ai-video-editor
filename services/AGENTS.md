# services/AGENTS.md

## Python worker conventions

1. Use `uv` for dependency management. Run `uv sync` before working.
2. Pydantic models go in `services/shared-py/src/shared_py/models.py`.
3. Use `alias_generator=to_camel` on all models that serialize to/from the cut list.
4. Workers communicate via Temporal activities or the Redis job queue.
5. FFmpeg calls must log full command on failure. No silent subprocess errors.
6. **Structured logging**: Never use `print()`. Import `configure_logging` from `shared_py.logging_config` and call it in each worker's `__init__.py`:
   ```python
   from shared_py.logging_config import configure_logging
   configure_logging(service_name="ingest-worker")
   ```
7. **Tracing**: Import `init_tracing` from `shared_py.tracing` and call it before starting work:
   ```python
   from shared_py.tracing import init_tracing
   init_tracing("ingest-worker")
   ```
8. **Correlation IDs**: Use `bind_correlation_id_from_temporal()` when running inside Temporal activities to propagate trace context.
9. **Graceful degradation**: Optional deps (cv2, av, paddleocr, etc.) must have top-level `try/except ImportError` guards. Check `if module is None:` at function entry, log a warning, and return a sensible default.
10. Add tests in each worker's `tests/` directory.
