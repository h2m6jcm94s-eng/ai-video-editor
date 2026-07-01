# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import pytest

from reason_worker.attribution import apply_deltas, behavior_vector_from_cutlist, diff_cutlists
from shared_py.models import BehaviorVector, CutList


def _cutlist(n_slots: int = 4, total_s: float = 20.0) -> CutList:
    slots = []
    duration = total_s / n_slots
    for i in range(n_slots):
        slots.append(
            {
                "index": i,
                "start_s": i * duration,
                "duration_s": duration,
                "beat_index": i,
                "section": "intro",
                "target_shot_type": "wide",
                "subject_hint": "person",
                "motion_hint": "static",
                "energy_level": 0.5,
                "transition_in": "hard_cut",
                "transition_out": "hard_cut",
            }
        )
    return CutList(
        globals={
            "total_duration_s": total_s,
            "tempo_bpm": 120,
            "time_signature": "4/4",
            "aspect_ratio": "9:16",
        },
        slots=slots,
    )


def test_behavior_vector_basic():
    cutlist = _cutlist(n_slots=4, total_s=20.0)
    vector = behavior_vector_from_cutlist(cutlist)
    assert vector["cut_density_per_sec"] == pytest.approx(0.2)
    assert vector["slot_duration_mean_s"] == pytest.approx(5.0)
    assert vector["hard_cut_ratio"] == 1.0


def test_diff_increases_density():
    old = _cutlist(n_slots=4, total_s=20.0)
    new = _cutlist(n_slots=8, total_s=20.0)
    deltas = diff_cutlists(old, new)
    assert deltas["cut_density_per_sec"] == pytest.approx(0.2)
    assert deltas["slot_duration_mean_s"] < 0


def test_diff_dict_input():
    old = _cutlist(n_slots=4, total_s=20.0).model_dump(by_alias=True)
    new = _cutlist(n_slots=8, total_s=20.0).model_dump(by_alias=True)
    deltas = diff_cutlists(old, new)
    assert deltas["cut_density_per_sec"] == pytest.approx(0.2)


def test_apply_deltas():
    base = BehaviorVector(cut_density_per_sec=0.16)
    deltas = {"cut_density_per_sec": 0.1}
    updated = apply_deltas(base, deltas)
    assert updated.cut_density_per_sec == pytest.approx(0.26)
