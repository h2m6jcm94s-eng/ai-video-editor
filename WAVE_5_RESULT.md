# Wave 5 Result: Audio Intelligence Layer

**Date:** 2026-07-02
**Branch:** `main`
**Commit:** TBD
**Scope:** Loudness normalization, J-cuts/L-cuts, and stem-aware vocal ducking.

## What changed

### Loudness normalization
- New `services/ingest-worker/src/ingest_worker/loudness.py`:
  - `analyze_loudness(audio_path)` runs FFmpeg `loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json`.
  - Parses measured `input_i`, `input_tp`, `input_lra`, `input_thresh`, `target_offset`.
  - Caches to `<STORAGE_ROOT>/audio_master/<song_hash>/loudness.json`.
- New `LoudnessMeasurement` model in `services/shared-py/src/shared_py/models.py`.
- `SongMeaning` now includes an optional `loudness` field; `aggregate_song_meaning()` runs loudness analysis.
- New ingest activity `analyze_loudness_activity` + workflow trigger for songs.
- Reason workflow passes `loudness` into `generate_cutlist_activity`; `generate_cutlist_programmatic()` stores it on `CutListGlobals` when `features.use_loudness_normalization` is enabled.
- Render compiler applies a true second-pass `loudnorm` filter to the final output audio when a measurement is present.

### J-cuts / L-cuts
- Extended `AudioTrack` with `j_cut_lead_in_s` and `l_cut_tail_s`.
- Added `_apply_jl_cuts()` in `services/reason-worker/src/reason_worker/audio_mix.py`:
  - Extends dialogue tracks by up to 0.25 s before/after the slot video.
  - Clamped by neighboring slots and source clip duration.
- New `build_audio_mix_activity` in `services/reason-worker/src/reason_worker/activities.py` downloads clip assets, calls `build_audio_tracks()` with `features.use_jl_cuts`, and returns an updated cutlist.
- Wired into `GenerateFromReferenceWorkflow` after `rank_clips_activity` when `use_jl_cuts` is enabled.
- The render compiler already honors `AudioTrack.start_s/end_s` and `source_start_s/source_end_s`, so J/L offsets propagate automatically.

### Stem-aware ducking
- Added `_apply_stem_aware_ducking()` in `audio_mix.py`:
  - Disables music ducking for music tracks that overlap a `bass_drop` event.
  - Computes weighted vocal arousal from the `VocalEmotionCurve` and makes ducking 2 dB more aggressive when arousal > 0.65.
- Enabled via `AdaptiveFeatures.use_stem_aware_audio`.

### Feature toggles
- Added to `AdaptiveFeatures`:
  - `use_loudness_normalization`
  - `use_jl_cuts`
  - `use_stem_aware_audio`

### Tests
- `services/ingest-worker/tests/test_loudness.py`: 3 tests (cache, finite values, JSON parsing).
- `services/reason-worker/tests/test_audio_mix.py`: 3 new tests for J/L cuts and stem-aware ducking.

## Verification

### Unit tests
```text
services/ingest-worker/tests/: 46 passed
services/reason-worker/tests/ (excluding workflow): 151 passed
```

### Golden Render
```text
Suite: 25 passed, 0 failed, 0 skipped
```

### Full pytest
```text
4 failed, 701 passed, 30 skipped
```
The 4 failures are the same pre-existing issues from earlier waves:
- `tests/test_cutlist_gen.py::TestEffectsAndOverlays::test_highest_energy_slot_gets_vignette`
- `tests/test_cutlist_gen.py::TestShotAndBeatSnapping::test_slot_snaps_to_nearby_shot_boundary`
- `tests/test_cutlist_gen.py::TestSlotContiguityAndDurationCap::test_reference_shorter_than_song_caps_duration`
- `tests/test_integration_pipeline.py::TestEndToEndSmoke::test_full_pipeline_uses_multiple_clips_audio_and_no_bogus_overlays`

No new regressions.

## Known issues / follow-up
- `build_audio_mix_activity` downloads every clip to detect dialogue; this duplicates the render compiler's download. Future optimization: move dialogue detection into a shared pre-render step or pass local paths from the render worker.
- J/L cuts only apply to detected dialogue tracks; if no dialogue is detected, the cutlist audio is unchanged.
- Loudness normalization is off by default via `use_loudness_normalization`; enabling it changes output levels, so the Golden Render expected signatures would need recalibration if defaulted on.

## Next step
Wave 6: Pro Edit Features (Part 1) — stabilization, auto-reframe, and text-based editing primitives.
