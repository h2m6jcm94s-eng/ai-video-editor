# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 — see LICENSE in the repo root.
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from shared_py.models import CutList, CutListGlobals, Slot, Overlay, RenderConfig
from render_worker.fcpxml_export import export_cutlist_to_fcpxml


def _cutlist(slots, overlays=None, audio_tracks=None):
    return CutList(
        globals=CutListGlobals(total_duration_s=10.0, tempo_bpm=120.0),
        slots=slots,
        overlays=overlays or [],
        audio_tracks=audio_tracks or [],
    )


def test_export_creates_valid_fcpxml(tmp_path):
    clip_path = tmp_path / "clip.mp4"
    clip_path.write_bytes(b"dummy")
    song_path = tmp_path / "song.mp3"
    song_path.write_bytes(b"dummy")

    slots = [
        Slot(
            index=0,
            start_s=0.0,
            duration_s=2.0,
            beat_index=0,
            section="verse",
            target_shot_type="medium",
            subject_hint="subject",
            motion_hint="static",
            energy_level=0.5,
            selected_clip_id="clip1",
            source_window_start_s=5.0,
            transition_in="hard_cut",
        ),
        Slot(
            index=1,
            start_s=2.0,
            duration_s=2.0,
            beat_index=1,
            section="drop",
            target_shot_type="close_up",
            subject_hint="subject",
            motion_hint="dynamic",
            energy_level=0.9,
            selected_clip_id="clip1",
            transition_in="dissolve",
        ),
    ]
    overlays = [Overlay(text="Hello", start_s=0.0, end_s=1.0)]
    cutlist = _cutlist(slots, overlays=overlays)
    out = tmp_path / "edit.fcpxml"

    export_cutlist_to_fcpxml(
        cutlist,
        str(out),
        {"clip1": str(clip_path)},
        render_config=RenderConfig(output_path=str(out), width=1080, height=1920, fps=30.0),
        song_path=str(song_path),
    )

    assert out.exists()
    root = ET.parse(out).getroot()
    assert root.tag == "fcpxml"
    assert root.get("version") == "1.9"

    # One clip element per slot.
    clips = root.findall(".//clip")
    assert len(clips) == 2
    assert clips[0].get("offset") == "0.000000s"
    assert clips[0].get("start") == "5.000000s"
    assert clips[1].get("offset") == "2.000000s"

    # Dissolve produces a transition element.
    transitions = root.findall(".//transition")
    assert len(transitions) == 1
    assert transitions[0].get("name") == "Cross Dissolve"

    # One title from the overlay.
    titles = root.findall(".//title")
    assert len(titles) == 1
    assert titles[0].get("lane") == "1"

    # Audio music clip from fallback.
    audios = root.findall(".//audio")
    assert len(audios) == 1
    assert audios[0].get("role") == "music"
