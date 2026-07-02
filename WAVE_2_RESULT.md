# Wave 2 Result

## Status

Committed: `3d996d4` (T.9 Wave 2: Whisper lyric transcription, Demucs stem separation, Golden Render v2 criteria)

## What Wave 2 shipped

- `services/ingest-worker/src/ingest_worker/song_lyrics.py` — `faster-whisper` large-v3 lyric transcription with word-level timestamps and probability filtering.
- `services/ingest-worker/src/ingest_worker/stem_separate.py` — Demucs `htdemucs`/`htdemucs_ft` stem separation producing `drums/bass/vocals/other` WAVs.
- Dependency pins for `demucs==4.0.1`, `faster-whisper>=1.0.0`, and `torchaudio==2.6.0+cu124`.
- Offline render pipeline (`scripts/batch2-offline-render.py`) now runs song analysis (lyrics + stems) and writes `song_analysis.json`.
- Golden Render suite additions: required `lyrics_available` and `stems_available` criteria.

## Verification

### Caches produced

- Lyrics: `E:\ai-video-editor-storage\lyrics\591352f472ea0e1388e0d794abaa6d32\lyrics.json`
  - `lyric_word_count`: 196
- Stems: `E:\ai-video-editor-storage\stems\591352f472ea0e1388e0d794abaa6d32\`
  - 4/4 stems present, ~40 MB each

### Unit tests

```text
73 passed in 8.33s
```

### Full pytest (`--ignore=services/reason-worker/tests/test_workflow.py`)

```text
673 passed, 30 skipped, 4 failed
```

The 4 failures are pre-existing and unrelated to Wave 2:

- `tests/test_cutlist_gen.py::TestEffectsAndOverlays::test_highest_energy_slot_gets_vignette`
- `tests/test_cutlist_gen.py::TestShotAndBeatSnapping::test_slot_snaps_to_nearby_shot_boundary`
- `tests/test_cutlist_gen.py::TestSlotContiguityAndDurationCap::test_reference_shorter_than_song_caps_duration`
- `tests/test_integration_pipeline.py::TestEndToEndSmoke::test_full_pipeline_uses_multiple_clips_audio_and_no_bogus_overlays`

### Golden Render

After Wave 2.5 regression fixes (beat_detect unicode-safe decode + structured feature-runtime parsing):

```text
Suite: 25 passed, 0 failed, 0 skipped
Expected checks: 25 checked, 0 required failures, 0 optional failures
```

Run command:

```bash
.venv/Scripts/python tests/golden_render/run.py --feature-emotion-led-cuts
```

## Wave 2.5 follow-up fixes (included before Wave 3 start)

- `services/ingest-worker/src/ingest_worker/beat_detect.py`
  - ASCII-safe temp copy for non-ASCII input filenames.
  - Added `-map 0:a:0` to ignore attached cover-art video streams.
  - Added disk cache at `E:\ai-video-editor-storage\beat\<hash>\beatgrid.json`.
- `scripts/golden-render-suite.py`
  - Falls back to structured `featureRuntimeReport` in `cutlist.json` when the text log summary is missing or incomplete.
  - Reads `real_path_ratio` directly from `cutlist.json`.
  - Reads `slot_window_fallback_count` from `cutlist.json`.
- `services/shared-py/src/shared_py/models.py`
  - Added `slot_window_fallback_count` to `CutList`.
- `scripts/batch2-offline-render.py`
  - Writes `cutlist.slot_window_fallback_count` to `cutlist.json`.

## Blockers cleared for Wave 3

- Wave 2 Golden Render regression fixed.
- `beat_detect.py` Polish-`Ł` decode path hardened.
- Re-render succeeds end-to-end.
