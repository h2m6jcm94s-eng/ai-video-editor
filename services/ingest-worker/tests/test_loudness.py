# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Unit tests for EBU R128 loudness measurement."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ingest_worker import loudness

SR = 22_050


def _make_tone(path: Path, freq: float = 1000.0, duration_s: float = 1.0, amp: float = 0.5):
    t = np.linspace(0, duration_s, int(SR * duration_s))
    y = amp * np.sin(2 * np.pi * freq * t).astype(np.float32)
    sf.write(path, y, SR)
    return str(path)


def test_loudness_measurement_cached(tmp_path: Path):
    path = _make_tone(tmp_path / "tone.wav")
    cache_dir = tmp_path / "loudness"

    m1 = loudness.analyze_loudness(path, cache_dir=cache_dir)
    m2 = loudness.analyze_loudness(path, cache_dir=cache_dir)

    assert m1 == m2
    assert (cache_dir / loudness._song_hash(path) / "loudness.json").exists()


def test_loudness_returns_finite_values(tmp_path: Path):
    path = _make_tone(tmp_path / "tone.wav")
    m = loudness.analyze_loudness(path)

    assert np.isfinite(m.input_i)
    assert np.isfinite(m.input_tp)
    assert np.isfinite(m.input_lra)
    assert m.target_i == -14.0


def test_parse_loudnorm_json_extracts_block():
    sample = (
        "[Parsed_loudnorm_0 @ 000001] \n"
        '{"input_i": "-20.50", "input_tp": "-1.20", "input_lra": "8.00", "input_thresh": "-30.00", "target_offset": "0.50"}\n'
        "size=       0kB time=00:00:01.00"
    )
    data = loudness._parse_loudnorm_json(sample)
    assert data is not None
    assert float(data["input_i"]) == pytest.approx(-20.5, abs=0.01)
