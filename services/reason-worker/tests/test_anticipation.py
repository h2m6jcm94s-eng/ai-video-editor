# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
import subprocess

import pytest

from reason_worker.anticipation import apply_vocal_anticipation, compute_motion_curve
from shared_py.models import MusicEventGrid, Slot


@pytest.fixture
def motion_clip(tmp_path):
    """Generate a 2s 24fps test clip with a hard cut from black to white at 1.0s."""
    out = tmp_path / "motion.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", "color=c=black:s=64x64:d=1.0",
        "-f", "lavfi",
        "-i", "color=c=white:s=64x64:d=1.0",
        "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0",
        "-pix_fmt", "yuv420p",
        "-r", "24",
        str(out),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return str(out)


@pytest.mark.ffmpeg
def test_compute_motion_curve_finds_peak(motion_clip):
    curve = compute_motion_curve(motion_clip, start_s=0.0, duration_s=2.0, fps=24.0)
    assert len(curve) > 0
    peak_t, peak_e = max(curve, key=lambda x: x[1])
    # The hard cut from black to white is at 1.0s, so the largest frame
    # difference is just before/after it.
    assert 0.9 <= peak_t <= 1.1
    assert peak_e > 0


def test_vocal_anticipation_sets_offset():
    slot = Slot(
        index=0,
        start_s=2.0,
        duration_s=1.0,
        beat_index=0,
        section="verse",
        target_shot_type="wide",
        subject_hint="subject",
        motion_hint="dynamic",
        energy_level=0.5,
    )
    curve = [(0.0, 0.1), (0.2, 0.9), (0.5, 0.2)]
    events = MusicEventGrid(song_hash="x", vocal_onset_times=[2.15])
    apply_vocal_anticipation(slot, curve, events, fps=24.0)
    # Peak at rel 0.2, vocal at 2.15, slot starts at 2.0 -> offset = 2.15 - 2.2 = -0.05
    assert abs(slot.anticipation_offset_s - (-0.05)) < 0.01


def test_vocal_anticipation_skips_when_no_vocal_nearby():
    slot = Slot(
        index=0,
        start_s=2.0,
        duration_s=1.0,
        beat_index=0,
        section="verse",
        target_shot_type="wide",
        subject_hint="subject",
        motion_hint="dynamic",
        energy_level=0.5,
    )
    curve = [(0.0, 0.1), (0.2, 0.9)]
    events = MusicEventGrid(song_hash="x", vocal_onset_times=[5.0])
    apply_vocal_anticipation(slot, curve, events, fps=24.0)
    assert slot.anticipation_offset_s == 0.0
