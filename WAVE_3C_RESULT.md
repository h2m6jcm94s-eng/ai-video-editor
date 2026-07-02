# Wave 3C Result: Per-Stem Music Event Detection

**Date:** 2026-07-02
**Branch:** `main`
**Commit:** TBD
**Scope:** Detect per-stem music events (kick, snare, hihat, bass drop, vocal onset, sweep, phrase boundary) from Demucs stems produced in Wave 2.

## What changed

### New module: `services/ingest-worker/src/ingest_worker/stem_events.py`
- Loads Demucs stems (`drums.wav`, `bass.wav`, `vocals.wav`, `other.wav`) at 22.05 kHz mono.
- **Drum events**: `librosa.onset_detect` on the drums stem, then classifies each onset by spectral peak into `kick` (40–80 Hz), `snare` (150–350 Hz or centroid < 2500 Hz), or `hihat` (≥ 6000 Hz or centroid ≥ 2500 Hz). Overlapping detections within ±30 ms are deduplicated, keeping the higher-intensity event.
- **Bass drops**: onset-strength peak picking on the bass stem with a 0.5 s minimum interval.
- **Vocal onsets**: merges `librosa.onset_detect` on the vocals stem with Whisper word-level start times; deduplicates within ±100 ms. Phrase boundaries are marked at word starts that follow a > 500 ms silence gap from the previous word end.
- **Sweep peaks**: smooths the spectral centroid curve of the `other` stem, finds positive-slope peaks above a 1.5-std / 5%-of-max threshold.
- Caches results to `<STORAGE_ROOT>/song_meaning/<stem_hash>/music_events.json`.

### New model: `MusicEventGrid`
- Added to `services/shared-py/src/shared_py/models.py`.
- Fields: `kick_times`, `snare_times`, `hihat_times`, `bass_drop_times`, `vocal_onset_times`, `phrase_boundary_times`, `sweep_peak_times`.
- Includes `events_in_window(t, window_s)` helper that returns prioritized events for cut-on-hit snapping.

### Temporal wiring
- Added `detect_music_events_activity` in `services/ingest-worker/src/ingest_worker/activities.py`.
- Registered the activity (plus the Wave 3A/3B activities) in `services/ingest-worker/src/ingest_worker/__main__.py`.

### Tests
- New test suite: `services/ingest-worker/tests/test_stem_events.py`.
- 7 unit tests covering drum classification, drum event detection, bass drops, vocal onsets, sweep detection, caching, and event-window priority.

## Verification

### Unit tests
```text
services/ingest-worker/tests/test_stem_events.py: 7 passed
services/ingest-worker/tests/: 39 passed
```

### Golden Render
```text
Suite: 25 passed, 0 failed, 0 skipped
```

### Real-song smoke test
Ran `detect_music_events()` on the cached Demucs stems for the Wave 2 song and produced:
- 79 kicks
- 180 snares
- 212 hihats
- 162 bass drops
- 399 vocal onsets
- 146 sweep peaks

The output was cached to `E:\ai-video-editor-storage\song_meaning\<stem_hash>\music_events.json`.

### Full pytest
```text
4 failed, 688 passed, 30 skipped
```
The 4 failures are the same pre-existing issues noted in Wave 3B:
- `tests/test_cutlist_gen.py::TestEffectsAndOverlays::test_highest_energy_slot_gets_vignette`
- `tests/test_cutlist_gen.py::TestShotAndBeatSnapping::test_slot_snaps_to_nearby_shot_boundary`
- `tests/test_cutlist_gen.py::TestSlotContiguityAndDurationCap::test_reference_shorter_than_song_caps_duration`
- `tests/test_integration_pipeline.py::TestEndToEndSmoke::test_full_pipeline_uses_multiple_clips_audio_and_no_bogus_overlays`

No new regressions.

## Known issues / follow-up
- `librosa` emits a benign `n_fft=2048 is too large` warning on very short synthetic test signals and on the tail of real stems; detection still works.
- The Wav2Vec2 batch GPU warning from Wave 3B remains; optimization is tracked for later.
- `transformers` remains at the working version `4.51.3`; do not re-pin to `4.44.2` (source-build failure on Windows + Python 3.13).

## Next step
Wave 4: aggregate `mood_tags.json`, `vocal_emotion.json`, and `music_events.json` into a single `song_meaning/<song_hash>.json`, and feed event grids into the reason worker's cut-on-hit snapping logic.
