# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Structured JSON logging setup for Python workers."""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit log records as single-line JSON."""

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            obj.update(record.extra)
        # Support correlation ID propagation from upstream services
        if hasattr(record, "correlationId"):
            obj["correlationId"] = record.correlationId
        if hasattr(record, "requestId"):
            obj["requestId"] = record.requestId
        if record.exc_info and record.exc_info[0] is not None:
            obj["error"] = self.formatException(record.exc_info)
        # Source location is useful for production debugging.
        obj.update(
            {
                "module": record.module,
                "funcName": record.funcName,
                "lineno": record.lineno,
            }
        )
        return json.dumps(obj, default=str)


def configure_logging(level: str | None = None, service_name: str | None = None) -> None:
    """Configure root logger for structured JSON output.

    Idempotent: repeated calls are ignored so importing one worker package from
    another does not clobber the existing logging configuration.
    """
    if getattr(configure_logging, "_configured", False):
        return

    log_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    # Close non-stdout/stderr handlers to avoid leaking file descriptors.
    for h in list(root.handlers):
        if getattr(h, "stream", None) not in (sys.stdout, sys.stderr):
            h.close()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level, logging.INFO))
    configure_logging._configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger that supports structured `extra` kwargs."""
    return logging.getLogger(name)


class StructuredLogger:
    """Thin wrapper so callers can do logger.info("msg", key=value)."""

    def __init__(self, name: str, correlation_id: str | None = None) -> None:
        self._logger = logging.getLogger(name)
        self._correlation_id = correlation_id

    def _log(self, method: str, msg: str, **kwargs: Any) -> None:
        extra: dict[str, Any] = {"extra": kwargs} if kwargs else {}
        if self._correlation_id:
            extra["correlationId"] = self._correlation_id
        getattr(self._logger, method)(msg, extra=extra, stacklevel=3)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log("debug", msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log("info", msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log("warning", msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log("error", msg, **kwargs)

    def exception(self, msg: str, **kwargs: Any) -> None:
        extra: dict[str, Any] = {"extra": kwargs} if kwargs else {}
        if self._correlation_id:
            extra["correlationId"] = self._correlation_id
        self._logger.exception(msg, extra=extra, stacklevel=3)

    def bind(self, correlation_id: str | None = None) -> "StructuredLogger":
        """Return a new logger bound to a correlation ID."""
        return StructuredLogger(self._logger.name, correlation_id)


def bind_correlation_id_from_temporal() -> str | None:
    """Extract correlation ID from Temporal activity headers if available."""
    try:
        from temporalio import activity

        headers = activity.info().header
        return headers.get("correlationId") if headers else None
    except Exception:
        return None
