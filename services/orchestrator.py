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
from render_worker.compiler import compile_timeline
from shared_py.logging_config import StructuredLogger, configure_logging
from shared_py.models import RenderConfig

logger = StructuredLogger("orchestrator")


def run_pipeline(
    reference_path: str,
    song_path: str,
    clip_paths: list,
    output_path: str,
    style_tier: str = "full_remix",
    mode: str = "auto",
    temp_dir: str = str(Path(tempfile.gettempdir()) / "ai-video-editor"),
):
    """Run the full AI video editing pipeline."""
    os.makedirs(temp_dir, exist_ok=True)

    logger.info("Pipeline started", phase="init", style_tier=style_tier, mode=mode)

    # Phase 1: Ingest
    logger.info("Probing reference video", phase="ingest", step=1)
    ref_info = probe_video(reference_path)
    logger.info("Reference probed", duration_sec=round(ref_info.get("duration_sec", 0), 2))

    logger.info("Detecting shot boundaries", phase="ingest", step=2)
    shots = detect_shot_boundaries(reference_path)
    logger.info("Shot boundaries detected", shot_count=len(shots))

    logger.info("Detecting beat grid", phase="ingest", step=3)
    beats = detect_beats(song_path)
    logger.info("Beat grid detected", bpm=round(beats.bpm, 1), beat_count=len(beats.beats))

    energy_curve = compute_energy_curve(song_path)

    # Phase 2: Style extraction
    style_analysis = {}
    lut_path = None

    if style_tier in ("color_grade", "with_text", "with_effects", "full_remix"):
        logger.info("Extracting color grade (LUT)", phase="style", step=4)
        lut_path, style_analysis = extract_lut_from_reference(
            reference_path, temp_dir
        )
        logger.info("LUT extracted", lut_extracted=lut_path is not None)

    if style_tier in ("with_text", "with_effects", "full_remix"):
        logger.info("Extracting text overlays", phase="style", step=5)
        overlays = extract_text_overlays(reference_path)
        logger.info("Text overlays extracted", overlay_count=len(overlays))
        style_analysis["detected_overlays"] = [o.model_dump(by_alias=True) for o in overlays]

    if style_tier in ("with_effects", "full_remix"):
        logger.info("Analyzing camera motion", phase="style", step=6)
        motions = analyze_camera_motion(reference_path, shots)
        logger.info("Camera motion analyzed", motions=list(set(motions)))
        style_analysis["camera_motions"] = motions

        logger.info("Classifying transitions", phase="style")
        shots = classify_transitions(reference_path, shots)

    # Phase 3: Reasoning
    logger.info("Generating cut-list", phase="reasoning", step=7)
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

    logger.info("Cut-list generated", slot_count=len(cutlist.slots))

    # Save cutlist
    cutlist_path = os.path.join(temp_dir, "cutlist.json")
    with open(cutlist_path, "w") as f:
        json.dump(cutlist.model_dump(by_alias=True), f, indent=2)
    logger.info("Cut-list saved", path=cutlist_path)

    # Phase 4: Render
    logger.info("Compiling final video", phase="render")
    config = RenderConfig(
        output_path=output_path,
        width=1280,
        height=720,
        lut_path=lut_path,
        song_path=song_path,
    )

    try:
        result = compile_timeline(cutlist, clip_paths_dict, output_path, config)
        logger.info("Render complete", result=result)
    except Exception as e:
        logger.error("Render failed", error=str(e))
        raise

    return output_path


def main():
    configure_logging()
    parser = argparse.ArgumentParser(description="AI Video Editor CLI")
    parser.add_argument("--reference", required=True, help="Reference video path")
    parser.add_argument("--song", required=True, help="Song/audio path")
    parser.add_argument("--clips", required=True, nargs="+", help="User clip paths")
    parser.add_argument("--output", default="output.mp4", help="Output path")
    parser.add_argument("--tier", default="full_remix", choices=["cuts_only", "color_grade", "with_text", "with_effects", "full_remix"])
    parser.add_argument("--mode", default="auto", choices=["auto", "assisted"])
    parser.add_argument("--temp-dir", default=str(Path(tempfile.gettempdir()) / "ai-video-editor"))

    args = parser.parse_args()

    reference_path = os.path.abspath(args.reference)
    song_path = os.path.abspath(args.song)
    clip_paths = [os.path.abspath(c) for c in args.clips]
    output_path = os.path.abspath(args.output)
    temp_dir = os.path.abspath(args.temp_dir)

    for name, path in [("reference", reference_path), ("song", song_path), *(("clip", c) for c in clip_paths)]:
        if not os.path.exists(path):
            parser.error(f"{name} path does not exist: {path}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)

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
