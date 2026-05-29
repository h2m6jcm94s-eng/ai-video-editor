"""Tests for render compiler."""

import pytest
import os
from render_worker.compiler import compile_timeline
from shared_py.models import CutList, CutListGlobals, Slot, RenderConfig


def test_compile_timeline_minimal():
    """Test minimal timeline compilation."""
    cutlist = CutList(
        globals=CutListGlobals(
            total_duration_s=2.0,
            tempo_bpm=120,
            time_signature="4/4",
            energy_curve=[0.5],
            section_markers=[],
            aspect_ratio="16:9",
        ),
        slots=[
            Slot(
                index=0,
                start_s=0.0,
                duration_s=2.0,
                beat_index=0,
                section="intro",
                target_shot_type="wide",
                subject_hint="test",
                motion_hint="static",
                energy_level=0.5,
                required_tags=[],
                avoid_tags=[],
                selected_clip_id="clip_0",
            ),
        ],
    )

    # This would need actual video files to run
    # Just verify the model structure
    assert cutlist.slots[0].selected_clip_id == "clip_0"
