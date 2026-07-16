#!/usr/bin/env python3
"""Regenerate only the batch-2 cutlist (no video compile) to verify lyric-aware karaoke.

Uses the same inputs as scripts/batch2-offline-render.py but skips clip ranking,
heatmap computation, and FFmpeg output. Writes the cutlist to a side directory so
existing output.mp4 remains untouched.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Windows consoles often default to cp1252; force UTF-8 for filenames.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "services" / "ingest-worker" / "src"))
sys.path.insert(0, str(repo_root / "services" / "reason-worker" / "src"))
sys.path.insert(0, str(repo_root / "services" / "render-worker" / "src"))
sys.path.insert(0, str(repo_root / "services" / "shared-py" / "src"))

from ingest_worker.beat_detect import detect_beats, compute_energy_curve
from ingest_worker.shot_detect import detect_shot_boundaries
from ingest_worker.probe import probe_video
from ingest_worker.song_meaning import aggregate_song_meaning
from reason_worker.cutlist_gen import generate_cutlist_programmatic, _behavior_from_style_analysis
from shared_py.models import AdaptiveFeatures

BATCH_DIR = repo_root / "test files" / "batch 2"
REFERENCE_NAME = "I CRIED WHILE I MADE THIS VIDEO  CYBERPUNK - Li Ray【AMV】 (1080p, h264, youtube).mp4"
SONG_NAME = "Let You Down - Dawid Podsiadło.flac"
OUTPUT_DIR = repo_root / "_t13_audit" / "batch2_recut"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ref_path = BATCH_DIR / REFERENCE_NAME
    song_path = BATCH_DIR / SONG_NAME

    print(f"Reference: {ref_path.name}")
    print(f"Song: {song_path.name}")

    ref_info = probe_video(str(ref_path))
    print(f"Reference: {ref_info.duration_sec:.2f}s @ {ref_info.fps:.2f}fps")

    beat_grid = detect_beats(str(song_path))
    print(f"Beats: {len(beat_grid.beats)}, BPM: {beat_grid.bpm:.1f}")

    shot_boundaries = detect_shot_boundaries(str(ref_path), fps=ref_info.fps)
    print(f"Shot boundaries: {len(shot_boundaries)}")

    energy_curve = compute_energy_curve(str(song_path), num_points=64)

    song_meaning = aggregate_song_meaning(str(song_path))
    print(
        f"Song meaning: {len(song_meaning.narrative.sections) if song_meaning.narrative else 0} sections"
    )

    style_analysis = {
        "detected_transitions": ["hard_cut", "dissolve", "whip", "hard_cut", "fade", "dissolve"],
        "camera_motions": [],
        "detected_overlays": [],
        "source_ip_hint": "Cyberpunk Edgerunners",
    }
    behavior = _behavior_from_style_analysis(style_analysis)
    behavior.clip_audio_inclusion_strategy = "iconic_only"

    features = AdaptiveFeatures(
        use_adaptive_slot_density=True,
        use_adaptive_audio_policy=False,
        use_iconic_quote_detection=True,
        use_emotion_led_cuts=True,
        use_wave_10_effects=True,
    )

    total_duration = (
        beat_grid.duration_s
        if getattr(beat_grid, "duration_s", None)
        else probe_video(str(song_path)).duration_sec
    )

    # Disable LLM kinetic-text composition so this script finishes quickly; the
    # lyric-stamp KT1 path (which can set karaoke_reveal) still runs.
    os.environ["KINETIC_TEXT_LLM"] = "0"

    cutlist = generate_cutlist_programmatic(
        beat_grid=beat_grid,
        shot_boundaries=shot_boundaries,
        energy_curve=energy_curve,
        available_shot_types=["wide", "medium", "close_up"],
        total_duration=total_duration,
        style_analysis=style_analysis,
        style_tier="full_remix",
        song_asset_id="song_001",
        user_clip_count=96,
        behavior=behavior,
        features=features,
        song_meaning=song_meaning,
        music_event_grid=song_meaning.music_event_grid if song_meaning else None,
    )

    cutlist_path = OUTPUT_DIR / "cutlist.json"
    cutlist_path.write_text(cutlist.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    print(f"Cutlist written: {cutlist_path}")

    slot_karaoke = sum(
        1 for s in cutlist.slots
        if getattr(s, "kinetic_text_animation", "") == "karaoke_reveal"
    )
    overlay_karaoke = sum(
        1 for o in cutlist.overlays if getattr(o, "animation", "") == "karaoke_reveal"
    )
    print(f"Slots with karaoke_reveal: {slot_karaoke}")
    print(f"Overlays with karaoke_reveal: {overlay_karaoke}")

    summary = {
        "slots": len(cutlist.slots),
        "overlays": len(cutlist.overlays),
        "karaoke_reveal_slots": slot_karaoke,
        "karaoke_reveal_overlays": overlay_karaoke,
        "kinetic_text_animations": sorted(
            {getattr(s, "kinetic_text_animation", "") for s in cutlist.slots if getattr(s, "kinetic_text_animation", "")}
        ),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
