# Wave 4 Result: Song-Meaning Aggregation + Cut-on-Hit Snapping

**Date:** 2026-07-02
**Branch:** `main`
**Commit:** TBD
**Scope:** Aggregate `mood_tags.json`, `vocal_emotion.json`, and `music_events.json` into a unified `SongMeaning` artifact, then use the `MusicEventGrid` to snap cuts to kicks, snares, bass drops, vocal onsets, and sweeps.

## What changed

### New model: `SongMeaning`
- Added to `services/shared-py/src/shared_py/models.py`.
- Contains `song_hash`, `genre_tags`, `section_moods`, `vocal_emotion_curve`, and `music_event_grid`.

### New module: `services/ingest-worker/src/ingest_worker/song_meaning.py`
- `aggregate_song_meaning(song_path, beat_grid, cache_dir)` runs or loads all song analyses and writes `<STORAGE_ROOT>/song_meaning/<song_hash>.json`.
- `load_song_meaning()` reads the cache.
- Reuses existing caches for mood, vocal emotion, and music events so repeated calls are cheap.

### Ingest Temporal wiring
- New activity `analyze_song_meaning_activity` in `services/ingest-worker/src/ingest_worker/activities.py`.
- Registered in `services/ingest-worker/src/ingest_worker/__main__.py`.
- `ProbeAssetWorkflow` now triggers `analyze_song_meaning_activity` for `asset_type == "song"` alongside `detect_beats_activity`.

### Reason-worker consumption
- New activity `ensure_song_meaning` in `services/reason-worker/src/ingest_worker/activities.py` reads `songMeaning` from asset metadata or aggregates it on demand.
- Registered in `services/reason-worker/src/reason_worker/__main__.py`.
- `GenerateFromReferenceWorkflow` calls `ensure_song_meaning` after shot boundaries and passes `musicEventGrid` into `generate_cutlist_activity`.

### Cut-on-hit snapping
- `services/reason-worker/src/reason_worker/cutlist_gen.py`:
  - `generate_cutlist()` and `generate_cutlist_programmatic()` accept an optional `music_event_grid`.
  - `_snap_slots_to_shots_and_beats()` adds a top snap tier: music events within `beat_snap_event_radius` (default 0.08 s) win over downbeats, beats, and shot boundaries.
- `services/reason-worker/src/reason_worker/slot_generator.py`:
  - `generate_slots_adaptive()` accepts `music_event_grid`.
  - Kick/snare/bass-drop events are added as high-weight candidates or boost nearby beat candidates.
- `services/shared-py/src/shared_py/config.py` adds `beat_snap_event_radius: float = 0.08`.

### Tests
- `services/ingest-worker/tests/test_song_meaning.py`: 4 tests covering hash stability, cache round-trip, model serialization, and aggregation with mocked sub-analyses.
- `services/reason-worker/tests/test_snap_priority.py`: added event-priority and no-grid fallback cases.
- `services/reason-worker/tests/test_slot_density.py`: added event-candidate boost test.

## Verification

### Unit tests
```text
services/ingest-worker/tests/: 43 passed
services/reason-worker/tests/ (excluding workflow): 147 passed
```

### Cut-on-hit smoke test
Ran `generate_cutlist_programmatic()` on the cached Wave-2 song with the real `MusicEventGrid`:
- 44 total slots
- 39 slots snapped within ±0.08 s of a kick, snare, bass drop, vocal onset, or sweep event

Sample matched cuts:
- slot 176.007 s → kick
- slot 188.662 s → kick
- slot 135.488 s → snare
- slot 39.903 s → bass_drop

### Golden Render
```text
Suite: 25 passed, 0 failed, 0 skipped
```

### Full pytest
```text
4 failed, 695 passed, 30 skipped
```
The 4 failures are the same pre-existing issues from Waves 2–3:
- `tests/test_cutlist_gen.py::TestEffectsAndOverlays::test_highest_energy_slot_gets_vignette`
- `tests/test_cutlist_gen.py::TestShotAndBeatSnapping::test_slot_snaps_to_nearby_shot_boundary`
- `tests/test_cutlist_gen.py::TestSlotContiguityAndDurationCap::test_reference_shorter_than_song_caps_duration`
- `tests/test_integration_pipeline.py::TestEndToEndSmoke::test_full_pipeline_uses_multiple_clips_audio_and_no_bogus_overlays`

No new regressions.

## Known issues / follow-up
- The `ensure_song_meaning` fallback downloads the full song and re-runs all analyses if `songMeaning` is not in metadata. For heavy songs this can take several minutes; the intended flow is for the ingest `ProbeAssetWorkflow` to populate metadata first.
- `music_event_grid` is passed into cutlist generation but is not yet used for clip ranking, transition selection, or audio ducking. Those are candidates for Wave 5.

## Next step
Wave 5: Audio Intelligence Layer — loudness normalization, J-cuts/L-cuts, and stem-aware vocal ducking.
