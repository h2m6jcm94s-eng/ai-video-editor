# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Main orchestration script tying all workers together."""

import os
import sys
import json
import argparse
import tempfile
from pathlib import Path

# Add all services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ingest-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "style-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "reason-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "render-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "upscale-worker", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "shared-py", "src"))

from ingest_worker.probe import probe_video
from ingest_worker.shot_detect import detect_shot_boundaries
from ingest_worker.beat_detect import detect_beats, compute_energy_curve
from style_worker.lut_extract import extract_lut_from_reference
from style_worker.transition_type import classify_transitions
from style_worker.text_extract import extract_text_overlays
from style_worker.camera_motion import analyze_camera_motion
from reason_worker.cutlist_gen import generate_cutlist
from reason_worker.clip_rank import rank_clips_for_slots, select_top_k_per_slot, compute_confidence
from render_worker.compiler import compile_timeline, render_preview
from shared_py.models import CutList, RenderConfig


def run_pipeline(
    reference_path: str,
    song_path: str,
    clip_paths: list,
    output_path: str,
    style_tier: str = "full_style",
    mode: str = "auto",
    temp_dir: str = str(Path(tempfile.gettempdir()) / "ai-video-editor"),
):
    """Run the full AI video editing pipeline."""
    os.makedirs(temp_dir, exist_ok=True)

    print("=" * 60)
    print("AI VIDEO EDITOR - Reference Style Matching")
    print("=" * 60)

    # Phase 1: Ingest
    print("\n[1/7] Probing reference video...")
    ref_info = probe_video(reference_path)
    print(f"  Duration: {ref_info.get('duration_sec', 0):.2f}s")

    print("\n[2/7] Detecting shot boundaries...")
    shots = detect_shot_boundaries(reference_path)
    print(f"  Found {len(shots)} shots")

    print("\n[3/7] Detecting beat grid...")
    beats = detect_beats(song_path)
    print(f"  BPM: {beats.bpm:.1f}, Beats: {len(beats.beats)}")

    energy_curve = compute_energy_curve(song_path)

    # Phase 2: Style extraction
    style_analysis = {}
    lut_path = None

    if style_tier in ("with_color", "full_style"):
        print("\n[4/7] Extracting color grade (LUT)...")
        lut_path, style_analysis = extract_lut_from_reference(
            reference_path, temp_dir
        )
        print(f"  LUT extracted: {lut_path is not None}")

    if style_tier in ("with_text", "full_style"):
        print("\n[5/7] Extracting text overlays...")
        overlays = extract_text_overlays(reference_path)
        print(f"  Found {len(overlays)} text overlays")
        style_analysis["detected_overlays"] = [o.model_dump() for o in overlays]

    if style_tier == "full_style":
        print("\n[6/7] Analyzing camera motion...")
        motions = analyze_camera_motion(reference_path, shots)
        print(f"  Motions: {set(motions)}")
        style_analysis["camera_motions"] = motions

        print("\n  Classifying transitions...")
        shots = classify_transitions(reference_path, shots)

    # Phase 3: Reasoning
    print("\n[7/7] Generating cut-list...")
    # Mock clip metadata for MVP
    clip_metadata = {
        f"clip_{i}": {
            "shot_type": ["wide", "medium", "close_up"][i % 3],
            "duration_sec": 10.0,
            "aesthetic_score": 0.6 + (i % 3) * 0.15,
            "motion_energy": 0.3 + (i % 3) * 0.3,
        }
        for i, _ in enumerate(clip_paths)
    }
    clip_paths_dict = {f"clip_{i}": p for i, p in enumerate(clip_paths)}

    available_shot_types = list(set(m["shot_type"] for m in clip_metadata.values()))

    cutlist = generate_cutlist(
        beats,
        shots,
        style_analysis,
        energy_curve,
        available_shot_types,
        total_duration=min(30.0, ref_info.get("duration_sec", 30.0)),
    )

    # Rank clips
    rankings = rank_clips_for_slots(cutlist.slots, clip_metadata)
    top_k = select_top_k_per_slot(rankings, k=3)
    confidences = compute_confidence(rankings)

    # Assign top-1 to each slot
    for slot in cutlist.slots:
        if slot.index in top_k and top_k[slot.index]:
            slot.selected_clip_id = top_k[slot.index][0]
            slot.confidence = confidences.get(slot.index, 0.5)

    print(f"  Generated {len(cutlist.slots)} slots")

    # Save cutlist
    cutlist_path = os.path.join(temp_dir, "cutlist.json")
    with open(cutlist_path, "w") as f:
        json.dump(cutlist.model_dump(), f, indent=2)
    print(f"  Cut-list saved: {cutlist_path}")

    # Phase 4: Render
    print("\n[RENDER] Compiling final video...")
    config = RenderConfig(
        output_path=output_path,
        width=1280,
        height=720,
        lut_path=lut_path,
        song_path=song_path,
    )

    try:
        result = compile_timeline(cutlist, clip_paths_dict, output_path, config)
        print(f"  Render complete: {result}")
    except Exception as e:
        print(f"  Render failed: {e}")
        raise

    return output_path


def main():
    parser = argparse.ArgumentParser(description="AI Video Editor CLI")
    parser.add_argument("--reference", required=True, help="Reference video path")
    parser.add_argument("--song", required=True, help="Song/audio path")
    parser.add_argument("--clips", required=True, nargs="+", help="User clip paths")
    parser.add_argument("--output", default="output.mp4", help="Output path")
    parser.add_argument("--tier", default="full_style", choices=["cuts_only", "with_color", "with_text", "full_style"])
    parser.add_argument("--mode", default="auto", choices=["auto", "assisted"])
    parser.add_argument("--temp-dir", default=str(Path(tempfile.gettempdir()) / "ai-video-editor"))

    args = parser.parse_args()

    run_pipeline(
        reference_path=args.reference,
        song_path=args.song,
        clip_paths=args.clips,
        output_path=args.output,
        style_tier=args.tier,
        mode=args.mode,
        temp_dir=args.temp_dir,
    )


if __name__ == "__main__":
    main()
