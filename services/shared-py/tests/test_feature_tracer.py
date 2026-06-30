# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import pytest

from shared_py.feature_tracer import (
    FeatureTracer,
    get_and_clear_traces,
    TRACER_REGISTRY,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Drain the global tracer registry before each test."""
    TRACER_REGISTRY.clear()
    yield
    TRACER_REGISTRY.clear()


class TestFeatureTracerSync:
    def test_real_path_is_recorded(self):
        with FeatureTracer("heatmap") as ft:
            ft.signature("windows=10")
            ft.real()

        traces = get_and_clear_traces()
        assert len(traces) == 1
        assert traces[0].feature == "heatmap"
        assert traces[0].real_path_ran is True
        assert traces[0].fallback_reason is None
        assert traces[0].output_signature == "windows=10"
        assert traces[0].elapsed_ms >= 0.0

    def test_fallback_path_is_recorded(self):
        with FeatureTracer("identity_matte") as ft:
            ft.fallback("model_unavailable")

        traces = get_and_clear_traces()
        assert len(traces) == 1
        assert traces[0].real_path_ran is False
        assert traces[0].fallback_reason == "model_unavailable"

    def test_no_commit_records_fallback(self):
        with FeatureTracer("dialogue"):
            pass

        traces = get_and_clear_traces()
        assert len(traces) == 1
        assert traces[0].real_path_ran is False
        assert traces[0].fallback_reason == "no_path_declared"

    def test_exception_records_fallback(self):
        with pytest.raises(RuntimeError, match="boom"):
            with FeatureTracer("save_the_cat") as ft:
                ft.signature("pre")
                raise RuntimeError("boom")

        traces = get_and_clear_traces()
        assert len(traces) == 1
        assert traces[0].real_path_ran is False
        assert traces[0].fallback_reason == "exception_raised"
        assert traces[0].output_signature == "pre"

    def test_gated_in_false_is_preserved(self):
        with FeatureTracer("iconic_quotes", gated_in=False) as ft:
            ft.fallback("gated_by_signals")

        traces = get_and_clear_traces()
        assert traces[0].gated_in is False

    def test_get_and_clear_empties_registry(self):
        with FeatureTracer("a") as ft:
            ft.real()

        first = get_and_clear_traces()
        second = get_and_clear_traces()
        assert len(first) == 1
        assert len(second) == 0


class TestFeatureTracerAsync:
    @pytest.mark.asyncio
    async def test_async_real_path_is_recorded(self):
        async with FeatureTracer("behavior_knn") as ft:
            ft.signature("neighbors=5")
            ft.real()

        traces = get_and_clear_traces()
        assert len(traces) == 1
        assert traces[0].feature == "behavior_knn"
        assert traces[0].real_path_ran is True

    @pytest.mark.asyncio
    async def test_async_exception_records_fallback(self):
        with pytest.raises(ValueError, match="async boom"):
            async with FeatureTracer("behavior_knn"):
                raise ValueError("async boom")

        traces = get_and_clear_traces()
        assert traces[0].real_path_ran is False
        assert traces[0].fallback_reason == "exception_raised"
