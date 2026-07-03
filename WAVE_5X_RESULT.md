# Wave 5X Result: Song Narrative & Clip Semantic Signals

**Date:** 2026-07-03
**Branch:** `main`
**Scope:** Gemma-driven song narrative, DINO-v2 clip embeddings, SigLIP-2 cross-modal fallback, and per-clip emotion profiles.

## What changed

### Song Narrative (Wave 5X.1)
- New `services/reason-worker/src/reason_worker/song_narrative.py`:
  - `label_song_section(...)` prompts a local Gemma (`gemma4:12b`) model to tag each song section with `lyric_sentiment`, `story_role`, `emotional_intensity`, `arc_beat_hint`, and a short `rationale`.
  - `analyze_song_narrative(...)` walks the `SongMoodProfile` sections and returns a `SongNarrative` object.
  - JSON parse failures are handled with a retry + skip strategy so one malformed label does not break the whole song.
- Integrated into `aggregate_song_meaning` in `services/ingest-worker/src/ingest_worker/song_meaning.py`.
- `SongMeaning` version bumped; it now carries `narrative: Optional[SongNarrative]`.

### DINO-v2 Clip Embeddings (Wave 5X.2)
- New `services/ingest-worker/src/ingest_worker/clip_semantic.py`:
  - Uses `facebook/dinov2-base` to produce 768-dim embeddings.
  - Samples frames via PyAV (first, last, and four internal samples).
  - Caches a compressed `.npz` with `mean_embedding`, `first_frame_embedding`, `last_frame_embedding`, and `sample_frame_embeddings`.
  - `cosine_first_to_last(...)` supports future match-cut detection.

### SigLIP-2 Cross-Modal Fallback (Wave 5X.3)
- New `services/style-worker/src/style_worker/siglip2.py`:
  - `embed_text(query)` returns normalized text embeddings from `google/siglip2-base-patch16-256`.
  - `embed_video_frames(clip_path)` returns a mean-pooled, normalized video embedding from 8 sampled frames.
  - `cosine_text_to_clip(query, clip_path)` exposes a single-score convenience API.
  - Embeddings are cached under `{STORAGE_ROOT}/siglip2_clip/{clip_id}.npy`.

### Clip Emotion Profile (Wave 5X.4)
- Extended `services/ingest-worker/src/ingest_worker/clip_emotion.py`:
  - Fuses DeepFace face emotion, audio prosody (librosa), dominant color, and optical-flow motion.
  - Emits `motion_vibe` as one of `still`, `slow`, `fluid`, `frantic`.
  - Caches to `{STORAGE_ROOT}/clip_emotion/{clip_id}.json`.

### Ingest wiring
- `services/ingest-worker/src/ingest_worker/activities.py`:
  - Added `compute_clip_semantic_activity` (DINO).
  - Added `compute_siglip2_embedding_activity` (SigLIP-2 video).
  - `analyze_clip_emotion_activity` now uses deterministic local paths keyed by `asset_id`.
- `services/ingest-worker/src/ingest_worker/__main__.py` registers the new activities.

### Schema additions
- `services/shared-py/src/shared_py/models.py`:
  - `SongSectionSemantics`, `SongNarrative`.
  - `SongMeaning.narrative`.
  - `ClipEmotionProfile.motion_vibe`.

### Tests
- `services/reason-worker/tests/test_song_narrative.py`: 3/3 passed.
- `services/ingest-worker/tests/test_clip_semantic.py`: 4/4 passed.
- `services/style-worker/tests/test_siglip2.py`: 4/4 passed.
- `services/ingest-worker/tests/test_clip_emotion.py`: 10/10 passed.

## Verification

### Unit tests (targeted)
```text
services/reason-worker/tests/test_song_narrative.py: 3 passed
services/ingest-worker/tests/test_clip_semantic.py: 4 passed
services/style-worker/tests/test_siglip2.py: 4 passed
services/ingest-worker/tests/test_clip_emotion.py: 10 passed
```

### Batch 2 cache population
```text
clip_semantic: 96/96 clips cached
siglip2_clip:  96/96 clips cached
clip_emotion:  96/96 clips cached
song_meaning:  narrative.json present with 6 labeled sections
```

## Known issues / follow-up
- DINO-v2 currently runs on CPU in this environment; GPU placement is supported but the ingest worker has no batching optimization yet.
- SigLIP-2 uses a slow processor by default; switching to `use_fast=True` may be required after transformers 4.52.
- Clip emotion relies on DeepFace, which is brittle on Windows without a face in the frame; the neutral-profile fallback keeps the pipeline running.
