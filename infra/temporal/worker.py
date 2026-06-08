# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal worker that polls and executes video processing activities."""

import asyncio
import os
import sys
import tempfile

# Add services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/ingest-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/style-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/reason-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/render-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/shared-py/src"))

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

from shared_py.models import CutList, BeatGrid, ShotBoundary
from shared_py.storage import download_asset, upload_file
from workflows import VideoRenderWorkflow


def _get_asset_path(asset_id: str, asset_key_map: dict) -> str:
    """Download an asset to a local temp path and return the path."""
    storage_key = asset_key_map.get(asset_id)
    if not storage_key:
        raise ValueError(f"No storage key found for asset {asset_id}")

    ext = os.path.splitext(storage_key)[1] or ".tmp"
    local_path = os.path.join(tempfile.gettempdir(), f"ave_{asset_id}{ext}")
    return download_asset(storage_key, local_path)


# ------------------------------------------------------------------
# Activities
# ------------------------------------------------------------------

@activity.defn
async def probe_inputs(reference_id: str, song_id: str, clip_ids: list, asset_key_map: dict) -> dict:
    """Probe all input assets for metadata."""
    from ingest_worker.probe import probe_video

    ref_path = _get_asset_path(reference_id, asset_key_map)
    ref_meta = probe_video(ref_path)

    song_path = _get_asset_path(song_id, asset_key_map)
    song_meta = probe_video(song_path)

    clip_metas = {}
    for cid in clip_ids:
        try:
            cpath = _get_asset_path(cid, asset_key_map)
            clip_metas[cid] = probe_video(cpath)
        except Exception as e:
            activity.logger.warning(f"Failed to probe clip {cid}: {e}")
            clip_metas[cid] = {"error": str(e)}

    return {
        "status": "probed",
        "reference": ref_meta,
        "song": song_meta,
        "clips": clip_metas,
    }


@activity.defn
async def detect_beats(song_asset_id: str, asset_key_map: dict) -> dict:
    """Detect beat grid from song."""
    from ingest_worker.beat_detect import detect_beats

    song_path = _get_asset_path(song_asset_id, asset_key_map)
    beat_grid = detect_beats(song_path)

    return {
        "bpm": beat_grid.bpm,
        "beats": beat_grid.beats,
        "downbeats": beat_grid.downbeats,
        "beat_positions": beat_grid.beat_positions,
        "segments": [
            {"start": s.start, "end": s.end, "label": s.label}
            for s in beat_grid.segments
        ],
        "status": "ok",
    }


@activity.defn
async def detect_shots(reference_asset_id: str, asset_key_map: dict) -> list:
    """Detect shot boundaries from reference."""
    from ingest_worker.shot_detect import detect_shot_boundaries

    ref_path = _get_asset_path(reference_asset_id, asset_key_map)
    shots = detect_shot_boundaries(ref_path, use_transnet=False)

    return [
        {
            "start_frame": s.start_frame,
            "end_frame": s.end_frame,
            "start_s": s.start_s,
            "end_s": s.end_s,
            "is_gradual": s.is_gradual,
            "confidence": s.confidence,
            "transition_in": getattr(s, "transition_in", "hard_cut"),
        }
        for s in shots
    ]


@activity.defn
async def analyze_reference_style(reference_asset_id: str, tier: str, asset_key_map: dict) -> dict:
    """Extract style features from reference."""
    from style_worker.lut_extract import extract_lut_from_reference
    from style_worker.transition_type import classify_transitions
    from ingest_worker.shot_detect import detect_shot_boundaries

    ref_path = _get_asset_path(reference_asset_id, asset_key_map)

    # Shot boundaries for transition classification
    shots = detect_shot_boundaries(ref_path, use_transnet=False)
    shots = classify_transitions(ref_path, shots)

    # LUT extraction
    output_dir = tempfile.mkdtemp(prefix="ave_style_")
    lut_path, analysis = extract_lut_from_reference(ref_path, output_dir, strength=0.5)

    # Build transition histogram
    transitions = {}
    for s in shots:
        t = getattr(s, "transition_in", "hard_cut")
        transitions[t] = transitions.get(t, 0) + 1

    return {
        "tier": tier,
        "lut_extracted": analysis.lut_extracted,
        "lut_path": lut_path,
        "lut_storage_key": analysis.lut_storage_key if analysis.lut_extracted else None,
        "color_palette": analysis.color_palette,
        "contrast_level": analysis.contrast_level,
        "saturation_level": analysis.saturation_level,
        "brightness_level": analysis.brightness_level,
        "transitions": transitions,
    }


@activity.defn
async def embed_user_clips(clip_asset_ids: list, asset_key_map: dict) -> dict:
    """Generate embeddings for user clips."""
    # TODO: wire to Qdrant / SigLIP-2 when available
    return {"embedded": len(clip_asset_ids), "status": "skipped"}


@activity.defn
async def generate_cutlist_claude(beats: dict, shots: list, style: dict, tier: str, energy_curve: list) -> dict:
    """Generate cut-list using AI provider."""
    from reason_worker.cutlist_gen import generate_cutlist
    from shared_py.models import BeatGrid, BeatSegment, ShotBoundary, SectionMarker

    # Reconstruct BeatGrid from dict
    beat_grid = BeatGrid(
        bpm=beats.get("bpm", 120),
        beats=beats.get("beats", []),
        downbeats=beats.get("downbeats", []),
        beat_positions=beats.get("beat_positions", []),
        segments=[
            BeatSegment(start=s["start"], end=s["end"], label=s["label"])
            for s in beats.get("segments", [])
        ],
    )

    # Reconstruct ShotBoundaries
    shot_boundaries = [
        ShotBoundary(
            start_frame=s.get("start_frame", 0),
            end_frame=s.get("end_frame", 0),
            start_s=s.get("start_s", 0.0),
            end_s=s.get("end_s", 0.0),
            is_gradual=s.get("is_gradual", False),
            confidence=s.get("confidence", 0.8),
        )
        for s in shots
    ]

    # Determine available shot types from detected shots
    available_shot_types = ["wide", "medium", "close_up"]

    cutlist = generate_cutlist(
        beat_grid=beat_grid,
        shot_boundaries=shot_boundaries,
        style_analysis=style,
        energy_curve=energy_curve or [],
        available_shot_types=available_shot_types,
        total_duration=30.0,
    )

    return cutlist.model_dump(by_alias=True)


@activity.defn
async def rank_clips_per_slot(cutlist: dict, clip_ids: list, clip_metadata: dict, embeddings: dict = None) -> dict:
    """Rank clips for each slot."""
    from reason_worker.clip_rank import rank_clips_for_slots, select_top_k_per_slot
    from shared_py.models import Slot, ClipScore

    slots = [Slot(**s) for s in cutlist.get("slots", [])]
    rankings = rank_clips_for_slots(slots, clip_metadata or {}, embeddings)
    top_k = select_top_k_per_slot(rankings, k=3)

    return {
        "rankings": {
            str(k): [s.model_dump(by_alias=True) for s in v]
            for k, v in rankings.items()
        },
        "top_k": top_k,
    }


@activity.defn
async def render_720p(cutlist: dict, clip_ids: list, clip_key_map: dict, lut_path: str = None, song_asset_id: str = None, song_key_map: dict = None) -> str:
    """Render 720p master."""
    from render_worker.compiler import compile_timeline
    from shared_py.models import CutList, RenderConfig

    # Download clips
    clip_paths = {}
    for cid in clip_ids:
        if cid in clip_key_map:
            local = _get_asset_path(cid, clip_key_map)
            clip_paths[cid] = local

    # Download song if provided
    song_path = None
    if song_asset_id and song_key_map:
        song_path = _get_asset_path(song_asset_id, song_key_map)

    output_path = os.path.join(tempfile.gettempdir(), f"ave_render_{cutlist.get('globals', {}).get('projectId', 'out')}.mp4")

    config = RenderConfig(
        output_path=output_path,
        width=1280,
        height=720,
        fps=30,
        song_path=song_path,
        lut_path=lut_path,
    )

    cutlist_obj = CutList(**cutlist)
    result = compile_timeline(cutlist_obj, clip_paths, output_path, config)
    return result


@activity.defn
async def upload_to_r2(output_path: str, project_id: str) -> str:
    """Upload rendered video to R2."""
    storage_key = f"projects/{project_id}/renders/{os.path.basename(output_path)}"
    upload_file(output_path, storage_key, content_type="video/mp4")
    return storage_key


@activity.defn
async def notify_user(user_id: str, project_id: str) -> None:
    """Send completion notification."""
    # TODO: wire to push notification / email service
    pass


# ------------------------------------------------------------------
# Worker setup
# ------------------------------------------------------------------

async def main():
    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))

    worker = Worker(
        client,
        task_queue="video-render-queue",
        workflows=[VideoRenderWorkflow],
        activities=[
            probe_inputs,
            detect_beats,
            detect_shots,
            analyze_reference_style,
            embed_user_clips,
            generate_cutlist_claude,
            rank_clips_per_slot,
            render_720p,
            upload_to_r2,
            notify_user,
        ],
    )

    print("Temporal worker started, polling task queue...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
