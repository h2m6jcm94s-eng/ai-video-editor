# Wave 6X Result: Arc Anchoring & Semantic/Emotion Clip Ranking

**Date:** 2026-07-03
**Branch:** `main`
**Scope:** Consume the Wave 5X signals to drive narrative arc anchoring and clip ranking by emotion/semantic match.

## What changed

### Arc Anchoring (Wave 6X.1)
- Rewrote `map_arc_to_song` in `services/reason-worker/src/reason_worker/arc_anchor.py`:
  - Primary path uses `SongMeaning.narrative` sections to place `HOOK`, `WORLD`, `CONFLICT`, `CRISIS`, `VICTORY`, etc.
  - Each `ArcBeatAnchor` now carries a `reason` string (e.g. `section_role=setup`, `lyric_sentiment='apologetic regret and internal struggle'`).
  - RMS energy fallback is preserved when `song_meaning` or `narrative` is unavailable.
- Updated `services/reason-worker/tests/test_arc_anchor.py`: 6/6 passed.

### Semantic & Emotion Ranking (Wave 6X.2)
- Extended `services/reason-worker/src/reason_worker/clip_rank.py`:
  - `_semantic_score` now has a three-tier fallback: Marengo text-to-video → SigLIP-2 text-to-clip → constant default.
  - `_emotion_match_score` computes cosine similarity between a clip's `ClipEmotionProfile` and the slot's `arc_beat_emotion_target`.
  - `_mood_motion_consistency` scores how well a clip's `motion_vibe` matches the song-section mood.
  - `_score_clip` consumes `emotion_profile` and returns richer `ClipScore` fields including `emotion_match_score` and `emotion_profile`.
  - New `RANK` weights: semantic 0.18, emotion match 0.25, mood-motion 0.12, heatmap 0.15, shot type 0.10, aesthetic 0.08, motion energy 0.05, duration 0.07.
- `rank_clips_for_slots` now accepts `clip_paths`, `clip_emotion_profiles`, and `section_moods`.
- `rank_clips_activity` downloads clips to deterministic local paths when `clip_storage_keys` are provided and passes `clip_paths` into the ranker.
- `GenerateFromReferenceWorkflow` now forwards `clip_storage_keys` to `rank_clips_activity` so SigLIP-2 and optical-flow momentum/anticipation can run end-to-end.
- Updated `services/reason-worker/tests/test_semantic_rank.py`: 7/7 passed.

### Golden Render criteria
- `scripts/golden-render-suite.py` adds Phase-2 checks for `--feature-emotion-led-cuts`:
  - `narrative_available`
  - `dino_embeddings_available`
  - `siglip_embeddings_available`
  - `arc_anchors_from_semantic`
  - `emotion_match_per_slot` (existing)

### Tests
- `services/reason-worker/tests/test_arc_anchor.py`: 6/6 passed.
- `services/reason-worker/tests/test_semantic_rank.py`: 7/7 passed.
- Existing ranking/exhaust/momentum tests remain green.

## Verification

### Unit tests (targeted)
```text
services/reason-worker/tests/test_arc_anchor.py: 6 passed
services/reason-worker/tests/test_semantic_rank.py: 7 passed
```

### Full pytest
```text
4 failed, 727 passed, 31 skipped
```
The 4 failures are the same pre-existing issues:
- `tests/test_cutlist_gen.py::TestEffectsAndOverlays::test_highest_energy_slot_gets_vignette`
- `tests/test_cutlist_gen.py::TestShotAndBeatSnapping::test_slot_snaps_to_nearby_shot_boundary`
- `tests/test_cutlist_gen.py::TestSlotContiguityAndDurationCap::test_reference_shorter_than_song_caps_duration`
- `tests/test_integration_pipeline.py::TestEndToEndSmoke::test_full_pipeline_uses_multiple_clips_audio_and_no_bogus_overlays`

### Golden Render (`tests/golden_render/run.py --feature-emotion-led-cuts`)
```text
Suite: 29 passed, 0 failed, 0 skipped
Expected checks: 25 checked, 0 required failures, 0 optional failures
```
New Phase-2 criteria added this wave all passed:
- `narrative_available`
- `dino_embeddings_available`
- `siglip_embeddings_available`
- `arc_anchors_from_semantic`
- `emotion_match_per_slot`

## Known issues / follow-up
- `section_moods` is not yet derived from the song mood profile; `_mood_motion_consistency` falls back to neutral 0.5 when no section mood is supplied.
- The SigLIP-2 fallback is invoked per slot; a future optimization could precompute slot text embeddings once and reuse them across clips.
- `rank_clips_activity` downloads clips synchronously inside the activity; for large libraries this should be parallelized or moved to a pre-stage.
