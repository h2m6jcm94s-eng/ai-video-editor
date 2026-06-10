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
        if record.exc_info:
            obj["error"] = self.formatException(record.exc_info)
        return json.dumps(obj, default=str)


def configure_logging(level: str | None = None, service_name: str | None = None) -> None:
    """Configure root logger for structured JSON output."""
    log_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level, logging.INFO))
    if service_name:
        root.name = service_name


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
        getattr(self._logger, method)(msg, extra=extra)

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
        self._logger.exception(msg, extra=extra)

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
