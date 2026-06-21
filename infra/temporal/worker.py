# Copyright (c) 2025 Devayan Dewri. All rights reserved.
# Licensed under the Elastic License 2.0 - see LICENSE in the repo root.
# Commercial SaaS use is prohibited without written permission.
"""Temporal worker that polls and executes video processing activities."""

import asyncio
import os
import sys
import tempfile
import uuid

# Add services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/ingest-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/style-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/reason-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/render-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/segment-worker/src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/shared-py/src"))

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.worker import Worker

from shared_py.models import CutList, BeatGrid, ShotBoundary
from shared_py.storage import download_asset, upload_file
from workflows import VideoRenderWorkflow, ProbeAssetWorkflow


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
    """Generate Marengo 3.0 embeddings for user clips."""
    from reason_worker.marengo_client import MarengoClient

    client = MarengoClient()
    if not client.available():
        return {
            "embedded": 0,
            "status": "skipped",
            "reason": "marengo_unavailable",
        }

    embeddings = {}
    for cid in clip_asset_ids:
        try:
            path = _get_asset_path(cid, asset_key_map)
            emb = client.embed_video_file(path)
            if emb is not None:
                embeddings[cid] = emb.tolist()
        except Exception as e:
            activity.logger.warning(f"Failed to embed clip {cid}: {e}")

    return {
        "embedded": len(embeddings),
        "status": "ready" if embeddings else "skipped",
        "embeddings": embeddings,
    }


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
async def generate_filler_clip(
    slot: dict,
    style_analysis: dict = None,
    transition_context: str = None,
    project_id: str = "",
    aspect_ratio: str = "16:9",
) -> dict:
    """Generate a filler/transition clip for a low-confidence slot."""
    from reason_worker.generative_client import get_generative_provider, download_video_url
    from reason_worker.filler_prompt import build_filler_prompt
    from shared_py.models import Slot

    slot_obj = Slot(**slot)
    prompt = build_filler_prompt(slot_obj, style_analysis, transition_context)

    # Most generative video APIs have a minimum clip length; clamp to a
    # supported range and let the renderer trim if the slot is shorter.
    duration = max(3.0, min(10.0, slot_obj.duration_s))

    provider = get_generative_provider()
    result = provider.generate(prompt, duration, aspect_ratio=aspect_ratio)
    if not result.ok:
        activity.logger.warning(
            f"Filler generation failed for slot {slot_obj.index}: {result.error}"
        )
        return {"status": "failed", "error": result.error}

    local_path = result.local_path
    if not local_path and result.video_url:
        try:
            local_path = download_video_url(result.video_url)
        except Exception as e:
            return {"status": "failed", "error": f"download failed: {e}"}

    if not local_path or not os.path.exists(local_path):
        return {"status": "failed", "error": "no video file returned"}

    asset_id = f"gen_{uuid.uuid4().hex[:12]}"
    storage_key = f"projects/{project_id}/generated/{asset_id}.mp4"
    upload_file(local_path, storage_key, content_type="video/mp4")

    return {
        "status": "succeeded",
        "asset_id": asset_id,
        "storage_key": storage_key,
        "provider": result.provider,
        "prompt": prompt,
    }


@activity.defn
async def rank_clips_per_slot(cutlist: dict, clip_ids: list, clip_metadata: dict, embeddings: dict = None) -> dict:
    """Rank clips for each slot."""
    from reason_worker.clip_rank import rank_clips_for_slots, select_top_k_per_slot
    from reason_worker.marengo_client import MarengoClient
    from shared_py.models import Slot, ClipScore

    slots = [Slot(**s) for s in cutlist.get("slots", [])]

    # Convert list embeddings back to numpy arrays for the ranker.
    np_embeddings = None
    if embeddings:
        np_embeddings = {
            cid: np.array(vec, dtype=np.float32)
            for cid, vec in embeddings.items()
        }

    client = MarengoClient()
    rankings = rank_clips_for_slots(
        slots,
        clip_metadata or {},
        np_embeddings,
        marengo_client=client,
    )
    top_k = select_top_k_per_slot(rankings, k=3)

    return {
        "rankings": {
            str(k): [s.model_dump(by_alias=True) for s in v]
            for k, v in rankings.items()
        },
        "top_k": top_k,
    }


@activity.defn
async def render_720p(
    cutlist: dict,
    clip_ids: list,
    clip_key_map: dict,
    lut_path: str = None,
    song_asset_id: str = None,
    asset_key_map: dict = None,
    mask_asset_ids: list = None,
) -> str:
    """Render 720p master."""
    from render_worker.compiler import compile_timeline
    from shared_py.models import CutList, RenderConfig

    asset_key_map = asset_key_map or {}

    # Download clips
    clip_paths = {}
    for cid in clip_ids:
        if cid in clip_key_map:
            local = _get_asset_path(cid, clip_key_map)
            clip_paths[cid] = local

    # Download song if provided
    song_path = None
    if song_asset_id and song_asset_id in asset_key_map:
        song_path = _get_asset_path(song_asset_id, asset_key_map)

    # Download segmentation masks so the compiler can apply them as mattes
    mask_paths = {}
    for mid in mask_asset_ids or []:
        if mid in asset_key_map:
            mask_paths[mid] = _get_asset_path(mid, asset_key_map)

    output_path = os.path.join(tempfile.gettempdir(), f"ave_render_{cutlist.get('globals', {}).get('projectId', 'out')}.mp4")

    config = RenderConfig(
        output_path=output_path,
        width=1280,
        height=720,
        fps=30,
        song_path=song_path,
        lut_path=lut_path,
        mask_paths=mask_paths,
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


@activity.defn
async def probe_asset(asset_id: str, storage_key: str) -> dict:
    """Probe a single asset and report metadata back to API."""
    from ingest_worker.probe import probe_asset_remote
    return probe_asset_remote(asset_id, storage_key)


# ------------------------------------------------------------------
# Worker setup
# ------------------------------------------------------------------

async def main():
    client = await Client.connect(os.environ.get("TEMPORAL_HOST", "localhost:7233"))

    # Start probe worker on "ingest" queue
    probe_worker = Worker(
        client,
        task_queue="ingest",
        workflows=[ProbeAssetWorkflow],
        activities=[probe_asset],
    )

    # Start render worker on "video-render-queue"
    render_worker = Worker(
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
            generate_filler_clip,
            render_720p,
            upload_to_r2,
            notify_user,
            segment_subject,
        ],
    )

    print("Temporal workers started, polling task queues: ingest, video-render-queue...")
    await asyncio.gather(probe_worker.run(), render_worker.run())

    print("Temporal worker started, polling task queue...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
