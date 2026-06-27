# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
from unittest.mock import patch
import numpy as np

from reason_worker.clip_rank import (
    rank_clips_for_slots,
    rerank_with_momentum,
    apply_anticipation_offsets,
)
from shared_py.models import Slot, ClipScore


def _make_slot(index: int, start_s: float = 0.0, duration_s: float = 1.0) -> Slot:
    return Slot(
        index=index,
        start_s=start_s,
        duration_s=duration_s,
        beat_index=index,
        section="verse",
        transition_in="hard_cut",
        transition_out="hard_cut",
        target_shot_type="wide",
        subject_hint="person",
        motion_hint="static",
        energy_level=0.5,
    )


def test_rerank_with_momentum_prefers_continuous_motion():
    """After momentum re-ranking, the clip continuing the previous motion wins."""
    slots = [_make_slot(0, start_s=0.0), _make_slot(1, start_s=1.0)]
    clip_metadata = {
        "clip-a": {"shot_type": "wide", "motion_energy": 0.5, "aesthetic_score": 0.5, "duration_sec": 5.0},
        "clip-b": {"shot_type": "wide", "motion_energy": 0.5, "aesthetic_score": 0.5, "duration_sec": 5.0},
    }
    clip_paths = {"clip-a": "/tmp/clip-a.mp4", "clip-b": "/tmp/clip-b.mp4"}

    # Manually construct an initial ranking so window starts are controlled.
    rankings = {
        0: [
            ClipScore(clip_id="clip-a", total_score=1.0, window_start_s=0.0),
            ClipScore(clip_id="clip-b", total_score=0.9, window_start_s=0.0),
        ],
        1: [
            ClipScore(clip_id="clip-a", total_score=1.0, window_start_s=0.0),
            ClipScore(clip_id="clip-b", total_score=0.9, window_start_s=0.0),
        ],
    }

    def _fake_flow(clip_path: str, start_s: float, n_frames: int = 8):
        # Outgoing motion from clip-a at its end (start_s == 1.0) is rightward.
        if "clip-a" in clip_path and start_s >= 0.9:
            return (1.0, 0.0)
        # Incoming motion to clip-b at its start (start_s == 0.0) is rightward.
        if "clip-b" in clip_path and start_s <= 0.1:
            return (1.0, 0.0)
        # Everything else is leftward / mismatched.
        return (-1.0, 0.0)

    with patch("reason_worker.clip_rank.compute_mean_flow_vector", side_effect=_fake_flow):
        new_rankings, chosen = rerank_with_momentum(rankings, slots, clip_metadata, clip_paths)

    assert chosen[0] == "clip-a"
    # Slot 1 should prefer clip-b because its incoming motion matches clip-a's outgoing.
    assert new_rankings[1][0].clip_id == "clip-b"
    assert new_rankings[1][0].total_score > rankings[1][0].total_score


def test_anticipation_offset_set_on_slots():
    """Applying anticipation offsets writes ``anticipation_offset_s`` on slots."""
    slots = [_make_slot(0, start_s=0.0, duration_s=1.0)]
    chosen_clip_ids = {0: "clip-a"}
    fps = 24.0
    curve = np.zeros(60, dtype=np.float32)
    # Peak around frame 19 -> 0.792s, comfortably inside the 1s window.
    curve[12:28] = np.concatenate([np.linspace(0, 1, 8), np.linspace(1, 0, 8)])
    clip_motion_curves = {"clip-a": curve}

    apply_anticipation_offsets(slots, chosen_clip_ids, clip_motion_curves, fps=fps)

    # Peak at 19/24 = 0.792s. Desired start = 0.792 - 0.333 = 0.458s. offset = 0.458s.
    assert 0.2 < slots[0].anticipation_offset_s < 0.7


def test_anticipation_offset_nonzero_for_late_peak():
    slots = [_make_slot(0, start_s=0.0, duration_s=2.0)]
    chosen_clip_ids = {0: "clip-a"}
    fps = 24.0
    curve = np.zeros(60, dtype=np.float32)
    # Peak around frame 30 -> 1.25s.
    curve[20:40] = np.concatenate([np.linspace(0, 1, 10), np.linspace(1, 0, 10)])
    clip_motion_curves = {"clip-a": curve}

    apply_anticipation_offsets(slots, chosen_clip_ids, clip_motion_curves, fps=fps)

    # Peak at 30/24 = 1.25s. Desired start = 1.25 - 0.333 = 0.917s.
    # offset = 0.917 - 0.0 = 0.917s.
    assert 0.7 < slots[0].anticipation_offset_s < 1.1


def test_rank_clips_for_slots_uses_momentum_and_anticipation_when_paths_provided():
    """When clip_paths is supplied, momentum and anticipation are applied."""
    slots = [_make_slot(0, start_s=0.0), _make_slot(1, start_s=1.0)]
    clip_metadata = {
        "clip-a": {"shot_type": "wide", "motion_energy": 0.5, "aesthetic_score": 0.5, "duration_sec": 5.0},
        "clip-b": {"shot_type": "wide", "motion_energy": 0.5, "aesthetic_score": 0.5, "duration_sec": 5.0},
    }
    clip_paths = {"clip-a": "/tmp/clip-a.mp4", "clip-b": "/tmp/clip-b.mp4"}

    with patch("reason_worker.clip_rank.compute_mean_flow_vector", return_value=(0.0, 0.0)), \
         patch("reason_worker.clip_rank.precompute_clip_motion_curve", return_value=np.zeros(24, dtype=np.float32)):
        rankings = rank_clips_for_slots(
            slots,
            clip_metadata,
            clip_paths=clip_paths,
            use_momentum=True,
            use_anticipation=True,
        )

    assert rankings
    # No exception means integration succeeded.
