# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import Slot

from render_worker.compiler import SlotAudioMix, _build_audio_filter_v2


def test_audio_filter_v2_applies_master_compressor_and_limiter():
    slots = [
        Slot(
            index=0,
            start_s=0.0,
            duration_s=10.0,
            beat_index=0,
            section="verse",
            target_shot_type="medium",
            subject_hint="subject",
            motion_hint="static",
            energy_level=0.5,
        )
    ]
    mix_decisions = [SlotAudioMix(song_level_db=-6.0, clip_audio_enabled=False)]

    graph = _build_audio_filter_v2(
        slots=slots,
        song_input_idx=0,
        dialogue_specs=[],
        mix_decisions=mix_decisions,
        temp_dir=str(Path(__file__).parent),
    )

    assert "acompressor" in graph
    assert "alimiter" in graph
    assert "[a_out]" in graph
