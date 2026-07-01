# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
"""Feature runtime tracer for the anti-decoration gate / demo-grade framework.

Each expensive or demo-critical feature is wrapped with a ``FeatureTracer``
context manager.  The tracer records whether the feature was gated in, whether
it ran its real path or fell back, and a lightweight output signature.  At the
end of a render the registry is drained and attached to the cutlist for
offline diagnosis.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from types import TracebackType
from typing import List, Optional


@dataclass
class FeaturePathReport:
    """A single feature's runtime path report."""

    feature: str
    gated_in: bool = True
    real_path_ran: bool = False
    fallback_reason: Optional[str] = None
    elapsed_ms: float = 0.0
    output_signature: Optional[str] = None


class FeatureTracer:
    """Context manager that records a feature's runtime path.

    Usage (sync)::

        with FeatureTracer("heatmap", gated_in=True) as ft:
            windows = _compute(...)
            ft.signature(f"windows={len(windows)}")
            ft.real()
            return windows

    Usage (async)::

        async with FeatureTracer("behavior_knn") as ft:
            result = await _knn_predict(...)
            ft.signature(f"neighbors={len(result)}")
            ft.real()
            return result

    If the block exits without calling ``real()`` or ``fallback()``, it is
    recorded as a fallback with reason ``"no_path_declared"``.  An exception
    raised inside the block is recorded as a fallback unless the path was
    already committed.
    """

    def __init__(self, feature: str, gated_in: bool = True) -> None:
        self.feature = feature
        self.gated_in = gated_in
        self._start = time.perf_counter()
        self._committed = False
        self._real = False
        self._fallback_reason: Optional[str] = None
        self._signature: Optional[str] = None

    def real(self) -> None:
        """Mark the real path as having run successfully."""
        self._real = True
        self._committed = True
        self._fallback_reason = None

    def fallback(self, reason: str) -> None:
        """Mark this feature as having taken a fallback path."""
        self._real = False
        self._committed = True
        self._fallback_reason = reason

    def signature(self, sig: str) -> None:
        """Attach a lightweight, deterministic output signature."""
        self._signature = sig

    def _report(self) -> FeaturePathReport:
        elapsed_ms = (time.perf_counter() - self._start) * 1000.0
        return FeaturePathReport(
            feature=self.feature,
            gated_in=self.gated_in,
            real_path_ran=self._real,
            fallback_reason=self._fallback_reason,
            elapsed_ms=elapsed_ms,
            output_signature=self._signature,
        )

    def _commit(self, exc_type: Optional[type]) -> FeaturePathReport:
        if not self._committed:
            if exc_type is not None:
                self.fallback("exception_raised")
            else:
                self.fallback("no_path_declared")
        return self._report()

    def __enter__(self) -> FeatureTracer:
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        _append_trace(self._commit(exc_type))

    async def __aenter__(self) -> FeatureTracer:
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        _append_trace(self._commit(exc_type))


# Thread-safe global registry of feature traces.
_TRACER_LOCK = threading.Lock()
TRACER_REGISTRY: List[FeaturePathReport] = []


def _append_trace(report: FeaturePathReport) -> None:
    with _TRACER_LOCK:
        TRACER_REGISTRY.append(report)


def get_and_clear_traces() -> List[FeaturePathReport]:
    """Return all traces collected since the last call and clear the registry."""
    with _TRACER_LOCK:
        traces = list(TRACER_REGISTRY)
        TRACER_REGISTRY.clear()
        return traces
