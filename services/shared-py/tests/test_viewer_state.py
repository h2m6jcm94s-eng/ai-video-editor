# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.

import pytest

from shared_py.viewer_state import (
    OperationEffect,
    OperationLedger,
    RegisteredOperation,
    ViewerState,
    ViewerStateSimulator,
    make_default_ledger,
)


class TestViewerState:
    def test_rejects_out_of_range(self):
        with pytest.raises(ValueError):
            ViewerState(attention=1.5)
        with pytest.raises(ValueError):
            ViewerState(arousal=-0.2)


class TestOperationLedger:
    def test_register_and_get(self):
        ledger = OperationLedger()
        op = RegisteredOperation(
            id="test_zoom",
            category="camera",
            effect=OperationEffect(d_attention=0.2),
        )
        ledger.register(op)
        assert ledger.get("test_zoom") is op

    def test_duplicate_id_raises(self):
        ledger = OperationLedger()
        op = RegisteredOperation(id="dup", category="x")
        ledger.register(op)
        with pytest.raises(ValueError):
            ledger.register(op)

    def test_list_by_category(self):
        ledger = make_default_ledger()
        camera_ops = ledger.list_by_category("camera")
        assert any(op.id == "zoom_in" for op in camera_ops)
        assert all(op.category == "camera" for op in camera_ops)


class TestViewerStateSimulator:
    def test_apply_known_op_changes_state(self):
        sim = ViewerStateSimulator()
        ledger = make_default_ledger()
        sim.ledger = ledger
        state = ViewerState(attention=0.5)
        new_state = sim.apply(state, "zoom_in", 0.5)
        assert new_state.attention > state.attention

    def test_apply_unknown_op_returns_same_state(self):
        sim = ViewerStateSimulator()
        state = ViewerState(attention=0.5)
        assert sim.apply(state, "does_not_exist", 1.0) == state

    def test_simulate_trajectory(self):
        sim = ViewerStateSimulator()
        sim.ledger = make_default_ledger()
        trajectory = sim.simulate(ViewerState(), [("zoom_in", 0.5), ("fade", 0.4)])
        assert len(trajectory) == 3
        # fade should lower arousal relative to zoomed state.
        assert trajectory[2].arousal < trajectory[1].arousal

    def test_clamping(self):
        sim = ViewerStateSimulator()
        ledger = OperationLedger()
        ledger.register(
            RegisteredOperation(
                id="spike",
                category="effect",
                effect=OperationEffect(d_attention=1.0, d_arousal=1.0),
            )
        )
        sim.ledger = ledger
        state = ViewerState(attention=0.9, arousal=0.9)
        new_state = sim.apply(state, "spike", 0.1)
        assert new_state.attention == 1.0
        assert new_state.arousal == 1.0
