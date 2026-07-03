#!/usr/bin/env python3
"""Populate Wave 5X/6X caches for the batch-2 fixture clips.

Writes:
  - E:\\ai-video-editor-storage\\clip_semantic\\<clip_id>.npz  (DINO-v2)
  - E:\\ai-video-editor-storage\\siglip2_clip\\<clip_id>.npy   (SigLIP-2)
  - E:\\ai-video-editor-storage\\clip_emotion\\<clip_id>.json (fused emotion)
  - <clip>.emotion.json sidecar (kept for the existing golden check)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "ingest-worker" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "style-worker" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "shared-py" / "src"))

from ingest_worker.clip_emotion import compute_clip_emotion_profile
from ingest_worker.clip_semantic import embed_clip
from style_worker.siglip2 import embed_video_frames

BATCH_DIR = REPO_ROOT / "test files" / "batch 2"
CLIPS_DIR = BATCH_DIR / "clips"
STORAGE_ROOT = Path(os.environ.get("STORAGE_ROOT", r"E:\ai-video-editor-storage"))


def main() -> None:
    clips = sorted(CLIPS_DIR.glob("*.mp4"))
    if not clips:
        print("No clips found in", CLIPS_DIR)
        sys.exit(1)

    dino_dir = STORAGE_ROOT / "clip_semantic"
    siglip_dir = STORAGE_ROOT / "siglip2_clip"
    emotion_dir = STORAGE_ROOT / "clip_emotion"
    for d in (dino_dir, siglip_dir, emotion_dir):
        d.mkdir(parents=True, exist_ok=True)

    total = len(clips)
    for i, clip_path in enumerate(clips, 1):
        clip_id = clip_path.stem
        print(f"[{i}/{total}] {clip_id}")

        try:
            embed_clip(str(clip_path), clip_id=clip_id)
        except Exception as exc:
            print(f"  DINO failed: {exc}")

        try:
            embed_video_frames(str(clip_path), clip_id=clip_id)
        except Exception as exc:
            print(f"  SigLIP failed: {exc}")

        try:
            storage_path = str(emotion_dir / f"{clip_id}.json")
            profile = compute_clip_emotion_profile(str(clip_path), cache_path=storage_path)
            # Keep the sidecar cache expected by golden-render-suite.py.
            sidecar_path = str(clip_path) + ".emotion.json"
            with open(sidecar_path, "w", encoding="utf-8") as f:
                json.dump(json.loads(profile.model_dump_json()), f)
        except Exception as exc:
            print(f"  Emotion failed: {exc}")

    print("Done.")


if __name__ == "__main__":
    main()
