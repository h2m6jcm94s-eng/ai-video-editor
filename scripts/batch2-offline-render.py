#!/usr/bin/env python3
"""Offline end-to-end render for batch 2 test files.

Runs the full AI video editor pipeline without the API/Temporal stack:
1. Probe reference video
2. Detect beats from song
3. Detect shot boundaries + transition archetypes from reference
4. Compute heatmap windows for each user clip
5. Generate programmatic cutlist
6. Rank clips using heatmap quality
7. Select direction-aware transitions
8. Render final MP4 with FFmpeg

Usage:
    .venv/Scripts/python scripts/batch2-offline-render.py [--duration 30] [--clips-limit 10] [--tier full_remix]
"""

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path

# Windows consoles often default to cp1252; force UTF-8 for progress JSON and filenames.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add worker source paths
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "services" / "ingest-worker" / "src"))
sys.path.insert(0, str(repo_root / "services" / "reason-worker" / "src"))
sys.path.insert(0, str(repo_root / "services" / "render-worker" / "src"))
sys.path.insert(0, str(repo_root / "services" / "shared-py" / "src"))

from ingest_worker.beat_detect import detect_beats, compute_energy_curve
from ingest_worker.heatmap import compute_clip_heatmaps_batch, heatmap_to_metadata
from ingest_worker.shot_detect import detect_shot_boundaries
from ingest_worker.clip_emotion import compute_clip_emotion_profiles
from reason_worker.clip_rank import rank_clips_for_slots
from reason_worker.aspect_detect import detect_aspect_preset, ASPECT_PRESETS
from reason_worker.cutlist_gen import generate_cutlist_programmatic, _behavior_from_style_analysis
from reason_worker.transition_select import select_xfade
from reason_worker.audio_mix import build_audio_tracks
from reason_worker.audio_scoring import ScoringConfig
from reason_worker.save_the_cat import apply_save_the_cat_beats

from shared_py.models import RenderConfig, AdaptiveFeatures, ClipEmotionProfile
from shared_py.feature_tracer import get_and_clear_traces
from shared_py.logging_config import StructuredLogger

logger = StructuredLogger("batch2_offline_render")

BATCH_DIR = repo_root / "test files" / "batch 2"
REFERENCE_NAME = "I CRIED WHILE I MADE THIS VIDEO  CYBERPUNK - Li Ray【AMV】 (1080p, h264, youtube).mp4"
SONG_NAME = "Let You Down - Dawid Podsiadło.flac"
OUTPUT_DIR = repo_root / "test files" / "batch 2" / "output"


def log_progress(stage: str, progress: float, message: str):
    payload = {"event": "progress", "stage": stage, "progress": progress, "message": message}
    print(json.dumps(payload, default=str), flush=True)



def main():
    # Import probe here (not at top level) so subprocesses spawned by the
    # heatmap batch worker do not have to import boto3/storage stacks.
    from ingest_worker.probe import probe_video
    from render_worker.compiler import (
    compile_timeline,
    _has_nvenc,
    QUALITY_PROFILES,
    get_slot_window_fallback_count,
    reset_slot_window_fallback_count,
)

    # Keep render temp files on the project drive (E:) so we do not fill the
    # system drive (C:) with intermediate segments.
    import tempfile

    tmp_dir = repo_root / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(tmp_dir)

    parser = argparse.ArgumentParser(description="Batch 2 offline render")
    parser.add_argument("--duration", type=float, default=None, help="Target output duration in seconds (default: full song length)")
    parser.add_argument("--clips-limit", type=int, default=0, help="Limit number of clips (0 = all)")
    parser.add_argument("--tier", type=str, default="full_remix", help="Style tier")
    parser.add_argument("--skip-heatmap", action="store_true", help="Skip heatmap computation (faster, lower quality)")
    parser.add_argument(
        "--heatmap-workers",
        type=int,
        default=1 if platform.system() == "Windows" else min(4, os.cpu_count() or 1),
        help="Number of parallel heatmap workers (default: 1 on Windows, min(4, cpu_count) elsewhere)",
    )
    parser.add_argument("--preview", action="store_true", help="Render 360p 15s preview")
    parser.add_argument(
        "--nvenc",
        action="store_true",
        help="Use NVIDIA NVENC hardware encoding when available (default: auto)",
    )
    parser.add_argument(
        "--no-nvenc",
        action="store_true",
        help="Force software (libx264) encoding even if NVENC is available",
    )
    parser.add_argument("--nvenc-preset", type=str, default="p5", help="NVENC preset (p1 fastest -> p7 best, default: p5)")
    parser.add_argument("--nvenc-cq", type=int, default=19, help="NVENC CQ value (default: 19)")
    parser.add_argument("--hwaccel", action="store_true", help="Enable CUDA hardware decoding (experimental)")
    parser.add_argument(
        "--quality",
        type=str,
        choices=list(QUALITY_PROFILES.keys()),
        default="demo",
        help="Encoding quality profile (default: demo)",
    )
    parser.add_argument(
        "--clip-order",
        type=str,
        choices=["smart", "filename", "upload", "shuffle"],
        default="smart",
        help="Deterministic tie-break when smart ranking is weak (default: smart)",
    )
    parser.add_argument(
        "--clip-order-threshold",
        type=float,
        default=0.15,
        help="Score gap below which the clip-order tie-break is applied (default: 0.15)",
    )
    parser.add_argument(
        "--feature-adaptive-slot-density",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use density-driven slot generation instead of one slot per beat (default: True)",
    )
    parser.add_argument(
        "--feature-adaptive-audio",
        action="store_true",
        help="Use adaptive clip audio inclusion policy (PR-2)",
    )
    parser.add_argument(
        "--feature-iconic-quotes",
        action="store_true",
        help="Detect and surface iconic dialogue quotes (PR-3)",
    )
    parser.add_argument(
        "--feature-emotion-led-cuts",
        action="store_true",
        help="Weight cut placement by emotional peaks (PR-9)",
    )
    parser.add_argument(
        "--feature-save-the-cat",
        action="store_true",
        help="Apply Save-the-Cat 15-beat story structure to slot sections",
    )
    parser.add_argument(
        "--source-ip-hint",
        type=str,
        default=None,
        help="Source IP hint for iconic quote detection (e.g. 'Cyberpunk Edgerunners')",
    )
    parser.add_argument(
        "--clip-audio-strategy",
        type=str,
        choices=["iconic_only", "speech_only", "always"],
        default=None,
        help="Override the clip audio inclusion strategy derived from the reference",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ref_path = BATCH_DIR / REFERENCE_NAME
    song_path = BATCH_DIR / SONG_NAME

    log_progress("startup", 0.0, "Locating media files")
    print(f"Reference: {ref_path.name}")
    print(f"Song: {song_path.name}")

    # 1. Probe reference
    log_progress("probe", 0.05, "Probing reference video")
    ref_info = probe_video(str(ref_path))
    print(f"Reference: {ref_info.duration_sec:.2f}s @ {ref_info.fps:.2f}fps")

    # 2. Detect beats
    log_progress("beat_detect", 0.10, "Detecting beats from song")
    beat_grid = detect_beats(str(song_path))
    print(f"Beats: {len(beat_grid.beats)}, BPM: {beat_grid.bpm:.1f}, Downbeats: {len(beat_grid.downbeats)}")

    # 3. Shot boundaries + transition archetypes
    log_progress("shot_detect", 0.20, "Detecting reference shot boundaries")
    shot_boundaries = detect_shot_boundaries(str(ref_path), fps=ref_info.fps)
    print(f"Shot boundaries: {len(shot_boundaries)}")

    log_progress("transition_archetypes", 0.25, "Deriving transition archetypes from reference cuts")
    # Fallback: alternate common archetypes since no classifier is wired yet.
    archetype_pool = ["hard_cut", "dissolve", "whip", "hard_cut", "fade", "dissolve"]
    archetypes = [archetype_pool[i % len(archetype_pool)] for i in range(len(shot_boundaries))]
    print(f"Transition archetypes: {set(archetypes)}")

    style_analysis = {
        "detected_transitions": archetypes,
        "camera_motions": [],
        "detected_overlays": [],
    }

    # 4. Collect clips
    log_progress("collect_clips", 0.30, "Collecting user clips")
    clip_paths = sorted((BATCH_DIR / "clips").glob("*.mp4"))
    if args.clips_limit > 0:
        clip_paths = clip_paths[:args.clips_limit]
    print(f"Using {len(clip_paths)} clips")

    # 5. Compute heatmaps in parallel with disk caching.
    clip_metadata = {}
    clip_path_map = {}
    cache_dir = OUTPUT_DIR / ".heatmap-cache"
    if args.skip_heatmap:
        log_progress("heatmap", 0.40, "Skipping heatmap computation")
    else:
        log_progress("heatmap", 0.40, f"Computing heatmaps for {len(clip_paths)} clips (cached/parallel)")
        heatmaps = compute_clip_heatmaps_batch(
            [str(cp) for cp in clip_paths],
            audio_path=str(song_path),
            window_s=0.5,
            stride_s=0.25,
            cache_dir=cache_dir,
            max_workers=args.heatmap_workers,
        )
        missing_heatmaps: list[str] = []
        empty_heatmaps: list[str] = []
        for idx, cp in enumerate(clip_paths):
            windows = heatmaps.get(str(cp), [])
            print(f"  [{idx+1}/{len(clip_paths)}] {cp.stem[:40]}... heatmap={len(windows)} windows")
            if windows is None:
                missing_heatmaps.append(cp.name)
            elif len(windows) == 0:
                empty_heatmaps.append(cp.name)

        total_clips = len(clip_paths)
        covered = total_clips - len(missing_heatmaps) - len(empty_heatmaps)
        coverage = covered / total_clips if total_clips > 0 else 1.0
        if missing_heatmaps or empty_heatmaps:
            print(
                f"⚠️  WARNING: heatmap coverage incomplete "
                f"({len(missing_heatmaps)} missing, {len(empty_heatmaps)} empty out of {total_clips}; coverage {coverage:.1%})"
            )
            if missing_heatmaps:
                print(f"   Missing: {', '.join(missing_heatmaps[:5])}{'...' if len(missing_heatmaps) > 5 else ''}")
            if empty_heatmaps:
                print(f"   Empty: {', '.join(empty_heatmaps[:5])}{'...' if len(empty_heatmaps) > 5 else ''}")
        assert coverage >= 0.8, (
            f"Heatmap coverage too low ({coverage:.1%}; {len(missing_heatmaps)} missing + {len(empty_heatmaps)} empty / {total_clips}). "
            f"This will cause clip repeats. Delete {cache_dir} or fix inputs and rerun."
        )

    for idx, cp in enumerate(clip_paths):
        info = probe_video(str(cp))
        meta = {
            "shot_type": "medium",
            "motion_energy": 0.5,
            "aesthetic_score": 0.5,
            "duration_sec": info.duration_sec,
            "filename": cp.name,
            "uploaded_at": 0,
            "heatmap": heatmap_to_metadata(heatmaps.get(str(cp), [])) if not args.skip_heatmap else [],
        }
        clip_id = f"clip_{idx:03d}"
        clip_metadata[clip_id] = meta
        clip_path_map[clip_id] = str(cp)

    # 5b. Compute per-clip emotion profiles when the narrative feature is on.
    if args.feature_emotion_led_cuts:
        log_progress("emotion_profiles", 0.45, "Computing per-clip emotion profiles")
        emotion_profiles = compute_clip_emotion_profiles(clip_path_map)
        for clip_id, profile in emotion_profiles.items():
            clip_metadata[clip_id]["emotion_profile"] = profile.model_dump(by_alias=False, mode="json")
        print(f"Emotion profiles: {len(emotion_profiles)} computed/cached")

    # 6. Generate cutlist
    log_progress("cutlist", 0.60, "Generating programmatic cutlist")
    energy_curve = compute_energy_curve(str(song_path), num_points=64)
    if args.preview:
        target_duration = 15.0
    elif args.duration is not None:
        target_duration = args.duration
    else:
        target_duration = beat_grid.duration_s if getattr(beat_grid, "duration_s", None) else probe_video(str(song_path)).duration_sec
    features = AdaptiveFeatures(
        use_adaptive_slot_density=args.feature_adaptive_slot_density,
        use_adaptive_audio_policy=args.feature_adaptive_audio,
        use_iconic_quote_detection=args.feature_iconic_quotes,
        use_emotion_led_cuts=args.feature_emotion_led_cuts,
    )
    behavior = _behavior_from_style_analysis(style_analysis)
    if args.clip_audio_strategy:
        behavior.clip_audio_inclusion_strategy = args.clip_audio_strategy
        if args.clip_audio_strategy == "speech_only":
            behavior.clip_audio_min_importance = 0.3
        elif args.clip_audio_strategy == "always":
            behavior.clip_audio_min_importance = 0.0
    cutlist = generate_cutlist_programmatic(
        beat_grid=beat_grid,
        shot_boundaries=shot_boundaries,
        energy_curve=energy_curve,
        available_shot_types=["wide", "medium", "close_up"],
        total_duration=target_duration,
        style_analysis=style_analysis,
        style_tier=args.tier,
        song_asset_id="song_001",
        user_clip_count=len(clip_paths),
        behavior=behavior,
        features=features,
    )
    if args.feature_save_the_cat:
        cutlist = apply_save_the_cat_beats(cutlist, target_duration)
        print(f"Cutlist: {len(cutlist.slots)} slots, {len(cutlist.overlays)} overlays (Save-the-Cat applied)")
    else:
        print(f"Cutlist: {len(cutlist.slots)} slots, {len(cutlist.overlays)} overlays")

    # Warn when the clip limit is too low to avoid forced repeats.
    if args.clips_limit > 0 and args.clips_limit < len(cutlist.slots) * 1.2:
        print(
            f"⚠️  WARNING: --clips-limit {args.clips_limit} is below the recommended "
            f"minimum ({int(len(cutlist.slots) * 1.2)}) for {len(cutlist.slots)} slots. "
            "Clips will be repeated and the edit will look like a slideshow."
        )

    # 7. Rank clips
    log_progress("rank_clips", 0.70, "Ranking clips for slots")
    clip_emotion_profiles = {
        clip_id: ClipEmotionProfile(**meta["emotion_profile"])
        for clip_id, meta in clip_metadata.items()
        if meta.get("emotion_profile")
    }
    rankings = rank_clips_for_slots(
        cutlist.slots,
        clip_metadata,
        fallback_policy="best_available",
        force_exhaust=True,
        clip_order_fallback=args.clip_order,
        clip_order_smart_threshold=args.clip_order_threshold,
        clip_emotion_profiles=clip_emotion_profiles if args.feature_emotion_led_cuts else None,
        interleave_glimpses=args.feature_emotion_led_cuts,
    )

    # Apply selected clip IDs and window info
    for slot in cutlist.slots:
        scores = rankings.get(slot.index, [])
        if scores:
            top = scores[0]
            slot.selected_clip_id = top.clip_id
            slot.ranked_clip_ids = [s.clip_id for s in scores[:3]]
            if top.window_start_s is not None:
                slot.source_window_start_s = top.window_start_s
            slot.heatmap_score = top.window_score
            slot.emotion_match_score = top.emotion_match_score

    # 8. Direction-aware transitions
    log_progress("transitions", 0.75, "Selecting direction-aware transitions")
    for i, slot in enumerate(cutlist.slots):
        if i < len(cutlist.slots) - 1:
            next_slot = cutlist.slots[i + 1]
            out_motion = "still"
            in_motion = "still"
            if slot.selected_clip_id and rankings.get(slot.index):
                out_motion = rankings[slot.index][0].dominant_motion or "still"
            if next_slot.selected_clip_id and rankings.get(next_slot.index):
                in_motion = rankings[next_slot.index][0].dominant_motion or "still"
            ref_archetype = archetypes[i % len(archetypes)] if archetypes else "hard_cut"
            slot.transition_out = select_xfade(out_motion, in_motion, ref_archetype)

    # 9. Build adaptive audio mix (music bed + dialogue tracks)
    log_progress("audio_mix", 0.78, "Building adaptive audio mix")
    scoring_cfg = ScoringConfig(
        iconic_phrases=[
            "I want to be a legend",
            "I'm going to take you there",
            "I really want to stay at your house",
        ],
        min_dialogue_score=0.55,
    )
    source_ip_hint = args.source_ip_hint
    if not source_ip_hint and "CYBERPUNK" in REFERENCE_NAME.upper():
        source_ip_hint = "Cyberpunk Edgerunners"
    # Build a content-signals embedding for feature gating. The reference is an
    # AMV with a song, so the trailer-style path should win for iconic quotes
    # and sidechain ducking should stay enabled.
    energy_curve = compute_energy_curve(str(song_path))
    song_energy_mean = (
        sum(energy_curve) / len(energy_curve) if energy_curve else 0.5
    )
    motion_density = min(
        1.0, len(shot_boundaries) / max(1.0, ref_info.duration_sec)
    )
    content_embedding = {
        "song_present": 1.0,
        "song_energy_mean": song_energy_mean,
        "motion_density": motion_density,
        "speech_ratio": 0.0,
        "avg_speech_segment_duration_s": 0.0,
        "song_has_vocals": 1.0,
    }

    cutlist.audio_tracks = build_audio_tracks(
        cutlist,
        beat_grid=beat_grid,
        song_asset_id="song_001",
        clip_paths=clip_path_map,
        scoring_cfg=scoring_cfg,
        behavior=behavior,
        source_ip_hint=source_ip_hint,
        content_embedding=content_embedding,
    )
    print(f"Audio tracks: {len(cutlist.audio_tracks)} ({sum(1 for t in cutlist.audio_tracks if t.role == 'dialogue')} dialogue)")

    # 10. Render
    log_progress("render", 0.80, "Rendering final video")
    output_name = "preview.mp4" if args.preview else "output.mp4"
    output_path = OUTPUT_DIR / output_name

    # Detect output dimensions from reference aspect ratio.
    preset = detect_aspect_preset(ref_info.width, ref_info.height)
    if args.preview:
        # Half-resolution preview.
        width, height = ASPECT_PRESETS.get(preset, (1920, 1080))
        width, height = width // 4, height // 4
    else:
        width, height = ASPECT_PRESETS.get(preset, (1920, 1080))
    # Map quality profile to encoder settings.
    quality = "preview" if args.preview else args.quality
    profile = QUALITY_PROFILES[quality]
    if args.no_nvenc:
        use_nvenc = False
    elif args.nvenc:
        use_nvenc = _has_nvenc()
    else:
        use_nvenc = _has_nvenc() and not args.preview
    if use_nvenc:
        # Map x264 preset names to NVENC p-values (p1 slowest/best, p7 fastest).
        preset_to_nvenc = {
            "ultrafast": "p6",
            "veryfast": "p5",
            "medium": "p4",
            "slow": "p3",
            "veryslow": "p2",
        }
        video_preset = args.nvenc_preset or preset_to_nvenc.get(profile["preset"], "p4")
        video_crf = args.nvenc_cq if args.nvenc_cq and args.nvenc_cq > 0 else profile["crf"]
        video_codec = "h264_nvenc"
    else:
        video_preset = profile["preset"]
        video_crf = profile["crf"]
        video_codec = "libx264"

    config = RenderConfig(
        output_path=str(output_path),
        width=width,
        height=height,
        fps=30.0,
        song_path=str(song_path),
        video_codec=video_codec,
        video_preset=video_preset,
        video_crf=video_crf,
        use_nvenc=use_nvenc,
        nvenc_preset=args.nvenc_preset,
        nvenc_cq=args.nvenc_cq,
        use_hwaccel=args.hwaccel,

    )

    reset_slot_window_fallback_count()
    start_render = time.time()
    result_path = compile_timeline(cutlist, clip_path_map, str(output_path), config, style_tier=args.tier)
    render_time = time.time() - start_render
    fallback_count = get_slot_window_fallback_count()
    print(f"slot_window_fallback_count: {fallback_count}")

    log_progress("complete", 1.0, f"Render complete in {render_time:.1f}s")
    print(f"Output: {result_path}")

    # Collect feature runtime traces and compute the demo grade.
    traces = get_and_clear_traces()
    real_count = sum(1 for t in traces if t.real_path_ran)
    total = len(traces)
    real_path_ratio = real_count / total if total else 0.0
    demo_grade = real_path_ratio >= 0.8

    cutlist.feature_runtime_report = traces
    cutlist.real_path_ratio = real_path_ratio
    cutlist.demo_grade = demo_grade

    # Write cutlist for inspection
    cutlist_path = OUTPUT_DIR / "cutlist.json"
    cutlist_path.write_text(cutlist.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    print(f"Cutlist: {cutlist_path}")

    print("\nFeature runtime summary:")
    for t in sorted(traces, key=lambda x: x.feature):
        path = "real" if t.real_path_ran else f"fallback ({t.fallback_reason or 'unknown'})"
        print(f"  {t.feature}: {path} ({t.elapsed_ms:.1f}ms)")
    print(f"  real_path_ratio: {real_path_ratio:.2f}  demo_grade: {demo_grade}")
    if not demo_grade:
        print("  ⚠️  Demo grade failed — at least one feature ran a fallback path.")


if __name__ == "__main__":
    main()
